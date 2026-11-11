/* Covernas service worker —— 离线壳 + 静态资源缓存
 * 策略：
 *   - 导航请求（request.mode === "navigate"）: network-first，成功回写 "/" 缓存；失败回退缓存的 "/"
 *   - manifest.webmanifest: network-first（保证装到最新版），离线回退缓存
 *   - /static/* 其他静态资源: cache-first（命中即返回，未命中走网络并回写缓存）
 *   - /api/* 及其他路径: 直接走网络，不缓存、不拦截
 * 注意：/static/* 走 cache-first，改了 app.css / app.js 或图标后必须提升 CACHE_NAME 版本号，
 *       否则已安装的客户端会继续用旧缓存。
 */
var CACHE_NAME = "covernas-v1";
var PRECACHE_URLS = [
  "/",
  "/static/app.css",
  "/static/app.js",
  "/static/favicon.svg",
  "/static/pwa-192.png"
];

// 只缓存同源、状态正常的响应
function isCacheable(response) {
  return !!response && response.ok && response.type === "basic";
}

self.addEventListener("install", function (event) {
  event.waitUntil(
    caches.open(CACHE_NAME).then(function (cache) {
      // 逐个 add：单个资源失败（如 404）不应让整个 install 失败
      return Promise.all(
        PRECACHE_URLS.map(function (url) {
          return cache.add(new Request(url, { cache: "reload" })).catch(function (err) {
            console.debug("[sw] precache skipped:", url, err);
          });
        })
      );
    }).then(function () {
      return self.skipWaiting();
    })
  );
});

self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(
        keys.map(function (key) {
          if (key !== CACHE_NAME && key.indexOf("covernas-") === 0) {
            return caches.delete(key);
          }
          return Promise.resolve(false);
        })
      );
    }).then(function () {
      return self.clients.claim();
    })
  );
});

self.addEventListener("fetch", function (event) {
  var request = event.request;
  if (request.method !== "GET") return;

  var url;
  try {
    url = new URL(request.url);
  } catch (e) {
    return;
  }
  // 跨域资源不接管
  if (url.origin !== self.location.origin) return;

  // API 一律走网络
  if (url.pathname === "/api" || url.pathname.indexOf("/api/") === 0) return;

  // manifest：network-first，保证改名/改色能及时生效
  if (url.pathname === "/static/manifest.webmanifest") {
    event.respondWith(
      fetch(request).then(function (response) {
        if (isCacheable(response)) {
          var copy = response.clone();
          caches.open(CACHE_NAME).then(function (cache) {
            cache.put(request, copy);
          });
        }
        return response;
      }).catch(function () {
        return caches.match(request);
      })
    );
    return;
  }

  // 导航请求：network-first
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).then(function (response) {
        // 只把真正的应用壳（"/" 或 "/index.html"）回写为 "/" 缓存，
        // 避免 /s/<token>、下载页等被误存成首页
        if (isCacheable(response) &&
            (url.pathname === "/" || url.pathname === "/index.html")) {
          var copy = response.clone();
          caches.open(CACHE_NAME).then(function (cache) {
            cache.put("/", copy);
          });
        }
        return response;
      }).catch(function () {
        return caches.match("/").then(function (cached) {
          return cached || caches.match(request);
        });
      })
    );
    return;
  }

  // 静态资源：cache-first
  if (url.pathname.indexOf("/static/") === 0) {
    event.respondWith(
      caches.match(request).then(function (cached) {
        if (cached) return cached;
        return fetch(request).then(function (response) {
          if (isCacheable(response)) {
            var copy = response.clone();
            caches.open(CACHE_NAME).then(function (cache) {
              cache.put(request, copy);
            });
          }
          return response;
        });
      }).catch(function () {
        // 离线且未缓存：交给浏览器，保持原始失败语义
        return new Response("", { status: 504, statusText: "offline" });
      })
    );
    return;
  }

  // 其余（登录页、分享页等）不拦截
});
