/* ================= Box — 前端逻辑 ================= */
(function () {
  'use strict';

  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  var state = { view: 'desktop', path: '/mnt', trash: false, apps: [], files: [] };
  var ICONS = {};

  function icon(name, cls) {
    return '<svg class="i ' + (cls || '') + '"><use href="#i-' + name + '"/></svg>';
  }

  /* 图标兜底：sprite 里没有这个 symbol 时，用首字母渐变块，避免出现空白方块 */
  function iconSafe(name, label, color) {
    if (name && document.getElementById('i-' + name)) return icon(name);
    var txt = String(label || '?').trim().charAt(0).toUpperCase();
    return '<span class="ic-fallback">' + txt + '</span>';
  }

  function fmtBytes(n) {
    n = Number(n) || 0;
    if (n < 1024) return n + ' B';
    var u = ['KB', 'MB', 'GB', 'TB'], i = -1;
    do { n /= 1024; i++; } while (n >= 1024 && i < u.length - 1);
    return n.toFixed(n < 10 ? 1 : 0) + ' ' + u[i];
  }

  function fmtRate(n) { return fmtBytes(n) + '/s'; }

  function fmtUptime(sec) {
    sec = Math.max(0, Number(sec) || 0);
    var d = Math.floor(sec / 86400), h = Math.floor(sec % 86400 / 3600), m = Math.floor(sec % 3600 / 60);
    if (d > 0) return d + ' 天 ' + h + ' 小时';
    if (h > 0) return h + ' 小时 ' + m + ' 分';
    return m + ' 分钟';
  }

  function fmtTime(ts) {
    var d = new Date(ts * 1000);
    var p = function (n) { return n < 10 ? '0' + n : n; };
    return (d.getMonth() + 1) + '-' + p(d.getDate()) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
  }

  function toast(msg, kind) {
    var box = $('#toastBox');
    var el = document.createElement('div');
    el.className = 'toast ' + (kind || 'ok');
    el.innerHTML = icon(kind === 'err' ? 'alert' : 'check') + '<span></span>';
    el.lastChild.textContent = msg;
    box.appendChild(el);
    setTimeout(function () {
      el.style.transition = 'opacity .25s, transform .25s';
      el.style.opacity = '0';
      el.style.transform = 'translateY(6px)';
      setTimeout(function () { el.remove(); }, 260);
    }, 2400);
  }

  function api(path, opts) {
    return fetch(path, opts || { credentials: 'same-origin' }).then(function (r) {
      if (r.status === 401) { location.href = '/'; throw new Error('未登录'); }
      if (r.status === 403) {
        return r.json().then(function (d) {
          toast((d && (d.readonly ? '只读账号无权执行这个操作' : d.err)) || '没有权限', 'err');
          throw new Error('forbidden');
        });
      }
      return r.json();
    });
  }

  function post(path, data) {
    return api(path, {
      method: 'POST',
      body: new URLSearchParams(data || {}),
      credentials: 'same-origin'
    });
  }

  /* ---------------- 导航 ---------------- */
  var TITLES = {
    desktop: '桌面', files: '我的存储', services: '系统服务', storage: '磁盘管理', settings: '设置',
    photos: '相册', media: '媒体播放', music: '音乐', notes: '记事本',
    calc: '计算器', cron: '计划任务', docker: '容器',
    store: '应用商店', share: '网络共享', backup: '磁盘备份',
    site: '部署网站', remote: '远程访问', help: '使用说明',
    tasks: '任务管理器', maintain: '系统维护', shares: '分享链接', device: '我的设备',
    audit: '操作日志'
  };

  var NAV_GROUPS = [
    { title: '常用', items: [
      { v: 'desktop', t: '桌面', i: 'home' },
      { v: 'files', t: '我的存储', i: 'folder' },
      { v: 'photos', t: '相册', i: 'photo' },
      { v: 'media', t: '媒体播放', i: 'play' },
      { v: 'music', t: '音乐', i: 'music' }
    ]},
    { title: '工具', items: [
      { v: 'store', t: '应用商店', i: 'shop' },
      { v: 'docker', t: '容器', i: 'box' },
      { v: 'cron', t: '计划任务', i: 'clock' },
      { v: 'notes', t: '记事本', i: 'file' },
      { v: 'help', t: '使用说明', i: 'book' }
    ]},
    { title: '系统', items: [
      { v: 'services', t: '后端服务', i: 'layers' },
      { v: 'tasks', t: '任务管理器', i: 'layers' },
      { v: 'share', t: '网络共享', i: 'share' },
      { v: 'backup', t: '磁盘备份', i: 'backup' },
      { v: 'site', t: '部署网站', i: 'web' },
      { v: 'remote', t: '远程访问', i: 'wifi' },
      { v: 'shares', t: '分享链接', i: 'share' },
      { v: 'audit', t: '操作日志', i: 'clock' },
      { v: 'storage', t: '磁盘管理', i: 'hdd' },
      { v: 'maintain', t: '系统维护', i: 'cog' },
      { v: 'device', t: '我的设备', i: 'hdd' },
      { v: 'settings', t: '设置', i: 'cog' }
    ]}
  ];

  var BOTTOM = [
    { v: 'desktop', t: '桌面', i: 'home' },
    { v: 'files', t: '文件', i: 'folder' },
    { v: 'photos', t: '相册', i: 'photo' },
    { v: 'store', t: '应用', i: 'shop' },
    { v: 'settings', t: '设置', i: 'cog' }
  ];

  function buildNav() {
    var nav = $('#sideNav');
    nav.innerHTML = '';
    NAV_GROUPS.forEach(function (g) {
      var t = document.createElement('p');
      t.className = 'nav-title';
      t.textContent = g.title;
      nav.appendChild(t);
      g.items.forEach(function (it) {
        var b = document.createElement('button');
        b.className = 'nav-item';
        b.dataset.go = it.v;
        b.innerHTML = icon(it.i) + '<span>' + it.t + '</span>';
        b.addEventListener('click', function () { closeMenu(); go(it.v); });
        nav.appendChild(b);
      });
    });

    var bn = $('#bottomNav');
    bn.innerHTML = '';
    BOTTOM.forEach(function (it) {
      var b = document.createElement('button');
      b.className = 'bn-item';
      b.dataset.go = it.v;
      b.innerHTML = icon(it.i) + '<span>' + it.t + '</span>';
      b.addEventListener('click', function () { go(it.v); });
      bn.appendChild(b);
    });
  }

  function go(view, silent) {
    if (!TITLES[view]) view = 'desktop';
    state.view = view;
    $$('.view').forEach(function (v) { v.classList.toggle('is-active', v.id === 'view-' + view); });
    $('#backBtn').hidden = (view === 'desktop');
    document.body.dataset.view = view;
    $('#pageTitle').textContent = TITLES[view];
    document.title = TITLES[view] + ' · Covernas';
    $$('.nav-item').forEach(function (b) { b.classList.toggle('on', b.dataset.go === view); });
    $$('.bn-item').forEach(function (b) { b.classList.toggle('on', b.dataset.go === view); });
    if (!silent) history.replaceState(null, '', view === 'desktop' ? '#desktop' : '#' + view);
    window.scrollTo({ top: 0 });
    if (view === 'files') loadFiles(state.path);
    if (view === 'services') loadServices();
    if (view === 'storage') loadStorage();
    if (view === 'settings') { fillAbout(); loadSettings(); }
    if (view === 'photos') loadPhotos();
    if (view === 'media') loadMedia();
    if (view === 'music') loadMusic();
    if (view === 'notes') loadNotes();
    if (view === 'cron') loadCron();
    if (view === 'docker') loadDocker();
    if (view === 'calc') initCalc();
    if (view === 'store') loadStore();
    if (view === 'share') loadShare();
    if (view === 'backup') loadBackup();
    if (view === 'site') loadSite();
    if (view === 'remote') loadRemote();
    if (view === 'tasks') loadTasks();
    if (view === 'maintain') loadMaintain();
    if (view === 'shares') loadShares();
    if (view === 'device') loadDevice();
    if (view === 'audit') loadAudit();
  }

  buildNav();

  /* ---------------- 移动端抽屉菜单 ---------------- */
  var sideBar = $('#sideBar'), menuMask = $('#menuMask');
  function closeMenu() {
    sideBar.classList.remove('open');
    if (menuMask) menuMask.hidden = true;
  }
  $('#menuBtn').addEventListener('click', function () {
    var open = sideBar.classList.toggle('open');
    if (menuMask) menuMask.hidden = !open;
  });
  if (menuMask) menuMask.addEventListener('click', closeMenu);
  window.addEventListener('resize', function () { if (window.innerWidth > 880) closeMenu(); });

  $('#backBtn').addEventListener('click', function () { go('desktop'); });

  /* ---------------- 全局搜索 / 命令面板 ---------------- */
  var cmdkState = { items: [], sel: 0, timer: null };

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function fmtFull(ts) {
    var d = new Date((ts || 0) * 1000);
    var p = function (n) { return n < 10 ? '0' + n : n; };
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + ' ' +
      p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds());
  }

  function openCmdk() {
    var box = $('#cmdk');
    if (!box) return;
    box.hidden = false;
    setTimeout(function () { var i = $('#cmdkInput'); if (i) i.focus(); }, 30);
    if (!cmdkState.items.length) renderCmdk({}, '');
  }
  function closeCmdk() { var b = $('#cmdk'); if (b) b.hidden = true; }

  function pageItems(q) {
    var out = [];
    var ql = (q || '').toLowerCase();
    Object.keys(TITLES).forEach(function (v) {
      var t = TITLES[v];
      if (!ql || t.toLowerCase().indexOf(ql) > -1 || v.indexOf(ql) > -1) {
        out.push({ kind: 'page', id: v, title: t, sub: '页面' });
      }
    });
    return out.slice(0, 8);
  }

  function renderCmdk(r, q) {
    var list = $('#cmdkList');
    if (!list) return;
    var items = [];
    pageItems(q).forEach(function (x) { items.push(x); });
    (r.apps || []).forEach(function (a) { items.push({ kind: 'app', id: a.id, title: a.name, sub: a.desc || '应用', path: a.path }); });
    (r.notes || []).forEach(function (n) { items.push({ kind: 'note', id: n.id, title: n.title || '无标题', sub: n.snippet || '笔记' }); });
    (r.files || []).forEach(function (f) {
      var isDir = f.kind === 'dir';
      items.push({ kind: isDir ? 'dir' : 'file', id: f.path, title: f.name,
        sub: (isDir ? '目录 · ' : '') + f.dir + (isDir ? '' : ' · ' + fmtBytes(f.size)) });
    });
    cmdkState.items = items;
    cmdkState.sel = 0;
    list.innerHTML = '';
    if (!items.length) {
      list.innerHTML = '<div class="cmdk-empty">' + (q ? '没找到相关结果' : '输入关键词：文件、笔记、应用、页面都能搜') + '</div>';
      return;
    }
    var groups = {};
    var kinds = { page: ['页面', 'compass'], app: ['应用', 'shop'], note: ['笔记', 'edit'], file: ['文件', 'file'], dir: ['文件', 'folder'] };
    items.forEach(function (it, i) {
      var meta = kinds[it.kind] || ['结果', 'dot'];
      if (!groups[meta[0]]) {
        groups[meta[0]] = document.createElement('div');
        groups[meta[0]].className = 'cmdk-group';
        groups[meta[0]].innerHTML = '<p class="cmdk-gt">' + meta[0] + '</p>';
        list.appendChild(groups[meta[0]]);
      }
      var row = document.createElement('button');
      row.type = 'button';
      row.className = 'cmdk-item' + (i === 0 ? ' on' : '');
      row.dataset.idx = i;
      row.innerHTML = icon(meta[1]) + '<span class="cmdk-t">' + esc(it.title) + '</span>' +
        '<span class="cmdk-sub">' + esc(it.sub || '') + '</span>';
      row.addEventListener('click', function () { pickCmdk(i); });
      groups[meta[0]].appendChild(row);
    });
  }

  function pickCmdk(i) {
    var it = cmdkState.items[i];
    if (!it) return;
    closeCmdk();
    if (it.kind === 'page') { go(it.id); return; }
    if (it.kind === 'note') { go('notes'); return; }
    if (it.kind === 'app') {
      var p = it.path || '';
      if (p.indexOf('#') === 0) {
        var v = p.slice(1).split('?')[0];
        if (v) go(v);
      } else if (p) { window.open(p, '_blank'); }
      return;
    }
    if (it.kind === 'dir') { state.path = it.id; go('files'); return; }
    if (it.kind === 'file') {
      var cut = it.id.lastIndexOf('/');
      state.path = cut > 0 ? it.id.slice(0, cut) : '/mnt';
      go('files');
    }
  }

  function searchCmdk(q) {
    if (!q) { renderCmdk({}, ''); return; }
    api('/api/search?q=' + encodeURIComponent(q)).then(function (r) {
      if (!r.ok) return;
      renderCmdk(r, q);
    }).catch(function () {});
  }

  if ($('#searchBtn')) $('#searchBtn').addEventListener('click', openCmdk);
  if ($('#cmdkClose')) $('#cmdkClose').addEventListener('click', closeCmdk);
  if ($('#cmdk')) {
    $('#cmdk').addEventListener('click', function (e) { if (e.target === this) closeCmdk(); });
  }
  if ($('#cmdkInput')) {
    $('#cmdkInput').addEventListener('input', function () {
      var v = this.value.trim();
      clearTimeout(cmdkState.timer);
      cmdkState.timer = setTimeout(function () { searchCmdk(v); }, 180);
    });
  }
  document.addEventListener('keydown', function (e) {
    var meta = e.ctrlKey || e.metaKey;
    if (meta && (e.key === 'k' || e.key === 'K')) {
      e.preventDefault();
      var box = $('#cmdk');
      if (box && box.hidden) openCmdk(); else closeCmdk();
      return;
    }
    var cm = $('#cmdk');
    if (!cm || cm.hidden) return;
    if (e.key === 'Escape') { e.preventDefault(); closeCmdk(); }
    else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      var n = cmdkState.items.length;
      if (!n) return;
      cmdkState.sel = (cmdkState.sel + (e.key === 'ArrowDown' ? 1 : -1) + n) % n;
      $$('#cmdkList .cmdk-item').forEach(function (el) {
        el.classList.toggle('on', Number(el.dataset.idx) === cmdkState.sel);
      });
      var cur = $('#cmdkList .cmdk-item.on');
      if (cur) cur.scrollIntoView({ block: 'nearest' });
    } else if (e.key === 'Enter') { e.preventDefault(); pickCmdk(cmdkState.sel); }
  });

  /* ---------------- 当前账号 / 账号管理 ---------------- */
  function loadMe() {
    api('/api/me').then(function (r) {
      if (!r.ok) return;
      state.me = r;
      var el = $('#meLine');
      if (el) el.textContent = r.user + (r.role === 'admin' ? ' · 管理员' : ' · 只读');
      if (r.role !== 'admin') document.body.classList.add('is-viewer');
      if (r.role === 'admin' && $('#usersBlock')) {
        $('#usersBlock').hidden = false;
        loadUsers();
      }
    }).catch(function () {});
  }

  function loadUsers() {
    api('/api/users').then(function (r) {
      if (!r.ok) return;
      var box = $('#userList');
      if (!box) return;
      box.innerHTML = '';
      r.users.forEach(function (u) {
        var row = document.createElement('div');
        row.className = 'user-row';
        var isMe = u.name === r.me;
        row.innerHTML = '<span class="user-name">' + esc(u.name) + (isMe ? ' <i class="user-me">(我)</i>' : '') + '</span>' +
          '<span class="tag ' + (u.role === 'admin' ? 'on' : '') + '">' + (u.role === 'admin' ? '管理员' : '只读') + '</span>' +
          '<span class="user-acts">' +
          '<button class="btn-icon" data-act="passwd" title="重置密码">🔑</button>' +
          (u.role === 'admin'
            ? '<button class="btn-icon" data-act="role" data-role="viewer" title="降为只读">↓</button>'
            : '<button class="btn-icon" data-act="role" data-role="admin" title="升为管理员">↑</button>') +
          (isMe ? '' : '<button class="btn-icon danger" data-act="del" title="删除">✕</button>') +
          '</span>';
        row.querySelectorAll('button').forEach(function (b) {
          b.addEventListener('click', function () {
            var act = b.getAttribute('data-act');
            if (act === 'del') {
              if (!confirm('删除账号「' + u.name + '」？该账号会立即失效。')) return;
              post('/api/users', { act: 'del', name: u.name }).then(function (rr) {
                toast(rr.ok ? '已删除' : (rr.err || '删除失败'), rr.ok ? 'ok' : 'err');
                if (rr.ok) loadUsers();
              });
            } else if (act === 'role') {
              var role = b.getAttribute('data-role');
              post('/api/users', { act: 'role', name: u.name, role: role }).then(function (rr) {
                toast(rr.ok ? '角色已更新' : (rr.err || '失败'), rr.ok ? 'ok' : 'err');
                if (rr.ok) loadUsers();
              });
            } else if (act === 'passwd') {
              var np = prompt('给「' + u.name + '」设置新密码（至少 8 位）');
              if (!np) return;
              post('/api/users', { act: 'passwd', name: u.name, password: np }).then(function (rr) {
                toast(rr.ok ? '密码已重置' : (rr.err || '失败'), rr.ok ? 'ok' : 'err');
              });
            }
          });
        });
        box.appendChild(row);
      });
    }).catch(function () {});
  }

  if ($('#userAddForm')) {
    $('#userAddForm').addEventListener('submit', function (e) {
      e.preventDefault();
      var fd = new FormData(this);
      post('/api/users', { act: 'add', name: fd.get('name'), password: fd.get('password'), role: fd.get('role') })
        .then(function (r) {
          if (!r.ok) { toast(r.err || '添加失败', 'err'); return; }
          toast('账号已添加');
          e.target.reset();
          loadUsers();
        });
    });
  }

  /* ---------------- 操作日志 ---------------- */
  function loadAudit() {
    var kw = ($('#auditSearch') || {}).value || '';
    var ev = ($('#auditEvent') || {}).value || '';
    api('/api/audit?limit=300&q=' + encodeURIComponent(kw) + '&event=' + encodeURIComponent(ev))
      .then(function (r) {
        if (!r.ok) return;
        var st = $('#auditStat');
        if (st) st.textContent = '共 ' + r.stat.count + ' 条 · ' + fmtBytes(r.stat.size) + ' · 当前显示最近 ' + r.items.length + ' 条';
        var box = $('#auditList');
        if (!box) return;
        box.innerHTML = '';
        if (!r.items.length) {
          box.innerHTML = '<div class="empty">还没有操作记录<br><span class="muted small">登录、文件、服务、容器等操作会自动记录</span></div>';
          return;
        }
        r.items.forEach(function (it) {
          var row = document.createElement('div');
          var bad = /失败|错误/.test(it.event);
          row.className = 'audit-row' + (bad ? ' is-bad' : '');
          row.innerHTML = '<span class="audit-time">' + fmtFull(it.ts) + '</span>' +
            '<span class="audit-ev">' + esc(it.event) + '</span>' +
            '<span class="audit-detail">' + esc(it.detail || '') + '</span>' +
            '<span class="audit-ip mono">' + esc(it.ip || '') + '</span>';
          box.appendChild(row);
        });
      }).catch(function () {});
  }
  if ($('#auditRefresh')) $('#auditRefresh').addEventListener('click', loadAudit);
  if ($('#auditEvent')) $('#auditEvent').addEventListener('change', loadAudit);
  if ($('#auditSearch')) {
    var auditTimer = null;
    $('#auditSearch').addEventListener('input', function () {
      clearTimeout(auditTimer);
      auditTimer = setTimeout(loadAudit, 250);
    });
  }

  /* ---------------- 配置备份 / 恢复 ---------------- */
  if ($('#cfgExport')) {
    $('#cfgExport').addEventListener('click', function () {
      toast('正在打包面板配置…');
      window.location.href = '/api/config/export';
    });
  }
  if ($('#cfgImportBtn') && $('#cfgFile')) {
    $('#cfgImportBtn').addEventListener('click', function () { $('#cfgFile').click(); });
    $('#cfgFile').addEventListener('change', function () {
      var f = this.files && this.files[0];
      this.value = '';
      if (!f) return;
      if (!confirm('用这个配置包覆盖当前面板配置？将重载 nginx / Samba / WebDAV 等服务。')) return;
      var el = $('#cfgResult');
      if (el) el.textContent = '正在恢复 ' + f.name + ' …';
      var fd = new FormData();
      fd.append('file', f);
      fetch('/api/config/import', { method: 'POST', body: fd, credentials: 'same-origin' })
        .then(function (r) { return r.json(); })
        .then(function (r) {
          if (r.ok) {
            toast('已恢复 ' + r.count + ' 个配置文件');
            if (el) el.textContent = '已恢复 ' + r.count + ' 个：' + r.applied.join('、');
            loadUI();
          } else {
            toast(r.err || '恢复失败', 'err');
            if (el) el.textContent = r.err || '恢复失败';
          }
        }).catch(function () { toast('恢复失败', 'err'); });
    });
  }

  /* ---------------- 首页卡片顺序 ---------------- */
  var CARD_KEYS = ['cpu', 'mem', 'disk', 'temp'];
  var CARD_NAMES = { cpu: '处理器', mem: '内存', disk: '存储', temp: '温度' };

  function applyHomeOrder(ui) {
    var stats = $('.stats');
    if (!stats) return;
    var order = (ui && ui.home_order && ui.home_order.length === 4) ? ui.home_order : CARD_KEYS;
    var cards = {};
    Array.prototype.slice.call(stats.children).forEach(function (el, i) {
      if (CARD_KEYS[i]) cards[CARD_KEYS[i]] = el;
    });
    var seq = [];
    order.forEach(function (k) { if (cards[k] && seq.indexOf(k) < 0) seq.push(k); });
    CARD_KEYS.forEach(function (k) { if (seq.indexOf(k) < 0 && cards[k]) seq.push(k); });
    seq.forEach(function (k) { stats.appendChild(cards[k]); });
  }

  function syncOrderUI(ui) {
    var box = $('#orderList');
    if (!box) return;
    var order = (ui && ui.home_order && ui.home_order.length === 4) ? ui.home_order : CARD_KEYS;
    box.innerHTML = '';
    order.forEach(function (k, i) {
      var row = document.createElement('div');
      row.className = 'order-row';
      row.innerHTML = '<span class="order-name">' + (CARD_NAMES[k] || k) + '</span>' +
        '<span class="order-acts">' +
        '<button type="button" class="btn-icon" data-up="' + i + '" title="上移"' + (i === 0 ? ' disabled' : '') + '>↑</button>' +
        '<button type="button" class="btn-icon" data-down="' + i + '" title="下移"' + (i === order.length - 1 ? ' disabled' : '') + '>↓</button>' +
        '</span>';
      box.appendChild(row);
    });
    Array.prototype.forEach.call(box.querySelectorAll('button'), function (b) {
      b.addEventListener('click', function () {
        var arr = ((state.ui && state.ui.home_order) || CARD_KEYS).slice();
        var up = b.hasAttribute('data-up');
        var idx = parseInt(b.getAttribute(up ? 'data-up' : 'data-down'), 10);
        var to = up ? idx - 1 : idx + 1;
        if (to < 0 || to >= arr.length) return;
        var t = arr[idx]; arr[idx] = arr[to]; arr[to] = t;
        post('/api/ui', { home_order: JSON.stringify(arr) }).then(function (r) {
          if (!r.ok) { toast(r.err || '保存失败', 'err'); return; }
          state.ui = r.ui;
          applyHomeOrder(r.ui);
          syncOrderUI(r.ui);
        });
      });
    });
  }

  /* ---------------- 状态 ---------------- */
  var netPrev = null;
  var MAXP = 40;
  var hist = { cpu: [], mem: [], temp: [] };

  function pushHist(key, v) {
    var a = hist[key];
    a.push(Number(v) || 0);
    if (a.length > MAXP) a.shift();
  }

  function drawSpark(id, arr, lo, hi, color) {
    var svg = document.getElementById(id);
    if (!svg || arr.length < 2) return;
    var W = 240, H = 38, n = arr.length;
    var pts = arr.map(function (v, i) {
      var x = n === 1 ? W : i / (n - 1) * W;
      var t = (v - lo) / (hi - lo);
      t = Math.max(0, Math.min(1, t));
      var y = H - 2 - t * (H - 8);
      return x.toFixed(1) + ',' + y.toFixed(1);
    });
    svg.querySelector('.sp-line').setAttribute('points', pts.join(' '));
    svg.querySelector('.sp-fill').setAttribute('points',
      '0,' + H + ' ' + pts.join(' ') + ' ' + W + ',' + H);
    svg.style.setProperty('--sp-color', color || 'var(--accent)');
  }

  function tempColor(t) {
    if (t >= 75) return 'var(--bad)';
    if (t >= 62) return 'var(--warn)';
    return 'var(--accent)';
  }

  function setStat(key, val, sub) {
    var v = $('#m' + key), s = $('#m' + key + 'Sub');
    if (v) v.textContent = val;
    if (s) s.textContent = sub;
  }

  function greet() {
    var h = new Date().getHours();
    if (h < 6) return '夜深了';
    if (h < 11) return '早上好';
    if (h < 14) return '中午好';
    if (h < 18) return '下午好';
    return '晚上好';
  }

  function poll() {
    api('/api/status').then(function (s) {
      if (!s.ok) return;
      $('#greeting').textContent = greet();
      $('#stCpu').textContent = s.cpu.pct + '%';
      $('#stMem').textContent = s.mem.pct + '%';
      $('#stTemp').textContent = s.temp ? s.temp + '°' : '—';

      var net = s.net || {};
      $('#stNet').textContent = '↓' + fmtBytes(net.rx) + '  ↑' + fmtBytes(net.tx);

      pushHist('cpu', s.cpu.pct);
      pushHist('mem', s.mem.pct);
      pushHist('temp', s.temp || 0);

      setStat('Cpu', s.cpu.pct + '%', '负载 ' + s.cpu.load.join(' ') + ' · ' + s.cpu.cores + ' 核');
      setStat('Mem', s.mem.pct + '%', fmtBytes(s.mem.used) + ' / ' + fmtBytes(s.mem.total));
      setStat('Disk', s.disk.pct + '%', fmtBytes(s.disk.used) + ' / ' + fmtBytes(s.disk.total));
      var tp = s.temp || 0;
      var warnT = (state.ui && state.ui.warn_temp) || 65;
      var tpBad = tp >= warnT, tpWarn = !tpBad && tp >= warnT - 8;
      setStat('Temp', tp ? tp + '°' : '—',
        tp ? (tpBad ? '超过告警阈值 ' + warnT + '°' : (tpWarn ? '温度偏高' : '温度正常')) : '读不到传感器');
      var mT = $('#mTemp'), sT = $('#stTemp');
      if (mT) { mT.classList.toggle('bad', tpBad); mT.classList.toggle('warn', tpWarn); }
      if (sT) { sT.classList.toggle('bad', tpBad); sT.classList.toggle('warn', tpWarn); }

      drawSpark('spCpu', hist.cpu, 0, 100, 'var(--accent)');
      drawSpark('spMem', hist.mem, 0, 100, 'var(--accent)');
      drawSpark('spTemp', hist.temp, 30, 90, tempColor(tp));

      var bar = $('#mDiskBar');
      if (bar) {
        $('#bDisk').style.width = Math.max(0, Math.min(100, s.disk.pct)) + '%';
        bar.classList.toggle('warn', s.disk.pct >= 80 && s.disk.pct < 92);
        bar.classList.toggle('bad', s.disk.pct >= 92);
      }

      $('#sysLine').textContent = [
        '已运行 ' + fmtUptime(s.host.uptime),
        s.host.kernel,
        '负载 ' + s.cpu.load.join(' '),
        '内存 ' + fmtBytes(s.mem.used) + '/' + fmtBytes(s.mem.total)
      ].join(' · ');

      var up = $('#sideUp');
      if (up) up.textContent = '运行 ' + fmtUptime(s.host.uptime) + ' · 负载 ' + s.cpu.load[0];

      state.last = s;
      if (state.view === 'settings') fillAbout();
    }).catch(function () {});
  }

  function tickClock() {
    var d = new Date();
    var p = function (n) { return n < 10 ? '0' + n : n; };
    $('#clock').textContent = p(d.getHours()) + ':' + p(d.getMinutes());
  }

  /* ---------------- 应用 ---------------- */
  /* 颜色工具：把 hex 变亮/变暗，生成渐变 */
  function shade(hex, amt) {
    var n = parseInt((hex || '#0f7b5f').replace('#', ''), 16);
    var r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
    var f = function (v) {
      v = Math.round(v + (amt > 0 ? (255 - v) * amt / 100 : v * amt / 100));
      return Math.max(0, Math.min(255, v));
    };
    return 'rgb(' + f(r) + ',' + f(g) + ',' + f(b) + ')';
  }

  function tileGradient(color) {
    return 'linear-gradient(145deg, ' + shade(color, 22) + ' 0%, ' +
           shade(color, -18) + ' 100%)';
  }

  function renderDesk(apps) {
    var g = $('#deskGrid');
    g.innerHTML = '';
    apps.forEach(function (a, idx) {
      var b = document.createElement('button');
      b.className = 'tile' + (a.online === false ? ' off' : '');
      b.style.animation = 'fadeUp .26s backwards';
      b.style.animationDelay = Math.min(idx * 12, 260) + 'ms';
      b.style.setProperty('--tile-color', a.color);
      b.innerHTML =
        '<span class="tile-ic" style="background:' + tileGradient(a.color) + '">' + iconSafe(a.icon, a.name, a.color) + '</span>' +
        '<span class="tile-name">' + a.name + '</span>';
      b.addEventListener('click', function () {
        if (a.path.indexOf('#') === 0) {
          var v = a.path.slice(1);
          if (v.indexOf('files') === 0) {
            state.trash = v.indexOf('trash=1') > -1;
            state.path = state.trash ? '/mnt/.trash' : '/mnt';
            go('files');
          } else {
            go(v);
          }
        } else {
          window.open(a.path, '_blank');
        }
      });
      g.appendChild(b);
    });
  }

  function loadApps() {
    api('/api/apps').then(function (r) {
      if (!r.ok) return;
      state.apps = r.apps;
      renderDesk(r.apps);
    });
  }

  /* ---------------- 最近文件 ---------------- */
  function loadRecent() {
    api('/api/files?path=/mnt').then(function (r) {
      var box = $('#recentList');
      if (!r.ok) { box.innerHTML = '<span class="muted small">读不到 /mnt</span>'; return; }
      var files = r.items.filter(function (f) { return !f.dir; })
        .sort(function (a, b) { return b.mtime - a.mtime; })
        .slice(0, 6);
      var dirs = r.items.filter(function (f) { return f.dir; })
        .sort(function (a, b) { return b.mtime - a.mtime; })
        .slice(0, 6);
      var show = files.length ? files : dirs;
      if (!show.length) {
        box.innerHTML = '<span class="muted small">/mnt 还是空的，进「我的存储」传点东西进来</span>';
        return;
      }
      box.innerHTML = show.map(function (f, i) {
        return '<div class="recent-item" data-i="' + i + '" data-dir="' + (f.dir ? 1 : 0) + '">' +
          icon(f.dir ? 'folder' : 'file') +
          '<span class="ri-name">' + f.name + '</span>' +
          '<span class="ri-meta">' + (f.dir ? '文件夹' : fmtTime(f.mtime)) + '</span></div>';
      }).join('');
      $$('.recent-item', box).forEach(function (el) {
        el.addEventListener('click', function () {
          var isDir = el.dataset.dir === '1';
          state.path = isDir ? '/mnt/' + el.querySelector('.ri-name').textContent : '/mnt';
          go('files');
        });
      });
    }).catch(function () {});
  }

  $('#recentAll').addEventListener('click', function () {
    state.trash = false;
    state.path = '/mnt';
    go('files');
  });

  $('#appsAll').addEventListener('click', function () {
    var g = $('#deskGrid');
    if (g) g.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });

  $('#heroRefresh').addEventListener('click', function () {
    poll(); loadApps(); loadRecent();
    toast('已刷新');
  });

  /* ---------------- 文件 ---------------- */
  function crumbs(p) {
    var box = $('#crumbs');
    box.innerHTML = '';
    var parts = p.split('/').filter(Boolean);
    var acc = '';
    var rootBtn = document.createElement('button');
    rootBtn.textContent = '/';
    rootBtn.addEventListener('click', function () { state.path = '/'; loadFiles('/'); });
    box.appendChild(rootBtn);

    parts.forEach(function (seg, i) {
      acc += '/' + seg;
      var sep = document.createElement('span');
      sep.className = 'sep';
      sep.textContent = '›';
      box.appendChild(sep);
      var b = document.createElement('button');
      b.textContent = seg;
      if (i === parts.length - 1) b.className = 'cur';
      var target = acc;
      b.addEventListener('click', function () { loadFiles(target); });
      box.appendChild(b);
    });
  }

  function loadFiles(p) {
    $('#fileList').innerHTML = '<div class="empty">加载中…</div>';
    api('/api/files?path=' + encodeURIComponent(p || '/')).then(function (r) {
      if (!r.ok) { $('#fileList').innerHTML = '<div class="empty">' + (r.err || '打不开') + '</div>'; return; }
      state.path = r.path;
      state.files = r.items;
      state.parent = r.parent;
      state.writable = r.writable !== false;
      state.sel = {};
      var fv = $('#fileView');
      if (fv) fv.value = state.fileView;
      crumbs(r.path);
      renderFiles(r.items, r.parent);
    }).catch(function () {
      $('#fileList').innerHTML = '<div class="empty">加载失败</div>';
    });
  }

  /* ---------------- 文件：选择 / 排序 / 剪贴板 ---------------- */
  state.sel = {};
  state.clip = null;
  state.query = '';
  state.sort = 'name';
  state.fileView = localStorage.getItem('covernas.fileview') || 'list';
  state.writable = true;

  function fullPath(name) {
    return state.path.replace(/\/$/, '') + '/' + name;
  }

  function syncFileBar() {
    var ro = state.writable === false;
    ['btnUpload', 'btnNewFile', 'btnMkdir'].forEach(function (id) {
      var b = document.getElementById(id);
      if (b) b.disabled = ro;
    });
    var paste = $('#btnPaste');
    if (paste) paste.disabled = ro || !state.clip;
    $$('#selBar [data-sel]').forEach(function (b) {
      if (b.dataset.sel === 'cut' || b.dataset.sel === 'del') b.hidden = ro;
    });
    var hint = $('#roHint');
    if (hint) hint.hidden = !ro;
  }

  function selList() { return Object.keys(state.sel); }
  function selCount() { return selList().length; }

  function syncSelBar() {
    var n = selCount();
    var bar = $('#selBar');
    bar.hidden = n === 0;
    if (n) $('#selText').textContent = '已选 ' + n + ' 项';
    $$('.row', $('#fileList')).forEach(function (r) {
      if (r.dataset.path) r.classList.toggle('picked', !!state.sel[r.dataset.path]);
    });
  }

  function toggleSel(p) {
    if (state.sel[p]) delete state.sel[p];
    else state.sel[p] = true;
    syncSelBar();
  }

  function clearSel() {
    state.sel = {};
    syncSelBar();
  }

  function sortItems(items) {
    var s = state.sort;
    var arr = items.slice();
    arr.sort(function (a, b) {
      if (a.dir !== b.dir) return a.dir ? -1 : 1;
      if (s === 'time') return b.mtime - a.mtime;
      if (s === 'size') return (b.size || 0) - (a.size || 0);
      if (s === 'type') {
        var ea = (a.name.split('.').pop() || '').toLowerCase();
        var eb = (b.name.split('.').pop() || '').toLowerCase();
        return ea.localeCompare(eb) || a.name.localeCompare(b.name);
      }
      return a.name.localeCompare(b.name, 'zh');
    });
    return arr;
  }

  function renderFiles(items, parent) {
    var box = $('#fileList');
    var view = state.fileView;
    box.className = 'list fv fv-' + view;
    box.innerHTML = '';
    var ro = state.writable === false;

    if (parent) {
      var up = document.createElement('div');
      up.className = 'row row-up fv-item';
      up.innerHTML = '<span class="row-ic">' + icon('back') + '</span>' +
        '<div class="row-main"><div class="row-name">上一级</div></div>';
      up.addEventListener('click', function () { clearSel(); loadFiles(parent); });
      box.appendChild(up);
    }

    var q = state.query.trim().toLowerCase();
    var list = sortItems(items).filter(function (f) {
      return !q || f.name.toLowerCase().indexOf(q) > -1;
    });

    if (!list.length) {
      box.innerHTML += '<div class="empty">' + (q ? '没有匹配「' + q + '」的文件' : '这个目录是空的') + '</div>';
      syncSelBar();
      syncFileBar();
      return;
    }

    var isImg = function (name) { return /\.(jpe?g|png|gif|webp|bmp|svg|avif)$/i.test(name); };

    list.forEach(function (f) {
      var full = fullPath(f.name);
      var row = document.createElement('div');
      row.className = 'row fv-item' + (state.sel[full] ? ' picked' : '');
      row.dataset.path = full;

      var sub = (f.dir ? '文件夹' : f.size_h + ' · ' + extOf(f.name)) + ' · ' + fmtTime(f.mtime);
      if (ro) sub = '受保护只读 · ' + sub;
      var acts = ro
        ? '<div class="row-act"><span class="lock" title="系统目录，受保护只读">' + icon('lock') + '</span></div>'
        : '<div class="row-act">' +
            '<button data-act="pv" title="预览">' + icon('eye') + '</button>' +
            '<button data-act="rn" title="重命名">' + icon('edit') + '</button>' +
            (f.dir ? '' : '<button data-act="dl" title="下载">' + icon('download') + '</button>') +
            '<button data-act="more" title="更多">' + icon('dot') + '</button>' +
            '<button data-act="del" class="danger" title="删除">' + icon('trash') + '</button>' +
          '</div>';

      if (view === 'icons' || view === 'gallery') {
        var thumb;
        if (view === 'gallery' && !f.dir && isImg(f.name)) {
          thumb = '<img class="fv-thumb" loading="lazy" src="/api/raw?path=' + encodeURIComponent(full) + '" alt="">';
        } else {
          thumb = '<span class="row-ic' + (f.dir ? ' dir' : '') + '">' + icon(f.dir ? 'folder' : 'file') + '</span>';
        }
        row.classList.add('fv-tile');
        row.innerHTML =
          (ro ? '' : '<span class="cb" data-act="sel">' + (state.sel[full] ? '✓' : '') + '</span>') +
          thumb +
          '<div class="fv-meta"><div class="row-name" title="' + f.name + '">' + f.name + '</div>' +
          (view === 'icons' ? '' : '<div class="row-sub">' + sub + '</div>') +
          '</div>' + acts;
      } else {
        row.innerHTML =
          (ro ? '' : '<span class="cb" data-act="sel">' + (state.sel[full] ? '✓' : '') + '</span>') +
          '<span class="row-ic' + (f.dir ? ' dir' : '') + '">' + icon(f.dir ? 'folder' : 'file') + '</span>' +
          '<div class="row-main">' +
            '<div class="row-name">' + f.name + '</div>' +
            (view === 'cols' ? '' : '<div class="row-sub">' + sub + '</div>') +
          '</div>' +
          acts;
      }

      row.addEventListener('click', function (e) {
        if (e.target.closest('[data-act]')) return;
        if (!ro && selCount()) { toggleSel(full); return; }
        if (f.dir) { clearSel(); loadFiles(full); }
        else preview(full, f.name);
      });

      $$('[data-act]', row).forEach(function (btn) {
        btn.addEventListener('click', function (e) {
          e.stopPropagation();
          var act = btn.dataset.act;
          if (act === 'sel') return toggleSel(full);
          if (act === 'dl') return void (location.href = '/api/download?path=' + encodeURIComponent(full));
          if (act === 'pv') return preview(full, f.name);
          if (act === 'rn') {
            var nv = prompt('重命名为：', f.name);
            if (!nv || nv === f.name) return;
            post('/api/rename', { path: full, name: nv }).then(function (r) {
              if (r.ok) { toast('已重命名'); loadFiles(state.path); }
              else toast(r.err || '失败', 'err');
            });
            return;
          }
          if (act === 'more') return fileMoreMenu(f);
          if (act === 'del') {
            if (!confirm('删除「' + f.name + '」？会移到回收站。')) return;
            post('/api/delete', { path: full }).then(function (r) {
              if (r.ok) { toast('已移到回收站'); delete state.sel[full]; loadFiles(state.path); }
              else toast(r.err || '删除失败', 'err');
            });
          }
        });
      });

      box.appendChild(row);
    });

    syncSelBar();
    syncFileBar();
  }

  function fileMoreMenu(f) {
    var full = fullPath(f.name);
    var items = ['属性', '复制路径'];
    if (f.dir) {
      items.push('压缩为 zip', '压缩为 tar.gz', '分享链接');
    } else {
      var low = f.name.toLowerCase();
      if (/.(zip|tar.gz|tgz|tar|tar.bz2)$/.test(low)) items.push('解压');
      else items.push('压缩为 zip', '压缩为 tar.gz');
      items.push('分享链接');
    }
    var pick = prompt('对「' + f.name + '」执行（输入序号）：\n' +
      items.map(function (x, i) { return (i + 1) + '. ' + x; }).join('\n'), '1');
    if (!pick) return;
    var act = items[parseInt(pick, 10) - 1];
    if (!act) return;
    if (act === '属性') return fileStat(full);
    if (act === '复制路径') {
      navigator.clipboard.writeText(full).then(function () { toast('路径已复制'); }, function () {
        prompt('路径：', full);
      });
      return;
    }
    if (act === '解压') return fileExtract(full);
    if (act === '压缩为 zip') return fileCompress([full], 'zip');
    if (act === '压缩为 tar.gz') return fileCompress([full], 'tar');
    if (act === '分享链接') return fileShare(full);
  }

  function fileStat(full) {
    post('/api/file/stat', { path: full }).then(function (r) {
      if (!r.ok) { toast(r.err || '读取失败', 'err'); return; }
      var i = r.info;
      var lines = [
        '名称：' + i.name,
        '路径：' + i.path,
        '类型：' + (i.dir ? '文件夹' : '文件'),
        '大小：' + i.size_h + (i.dir ? ('（' + i.count + ' 项）') : ''),
        '权限：' + i.mode,
        '属主：' + i.owner + ':' + i.group,
        '修改：' + fmtTime(i.mtime)
      ];
      var nm = prompt(lines.join('\n') + '\n\n输入新权限可修改（如 755），留空关闭：', i.mode);
      if (!nm) return;
      post('/api/file/chmod', { path: full, mode: nm }).then(function (r2) {
        if (r2.ok) toast('权限已改为 ' + nm);
        else toast(r2.err || '修改失败', 'err');
      });
    });
  }

  function fileCompress(paths, fmt) {
    var nm = prompt('压缩包名称（不含扩展名）：', '归档');
    if (!nm) return;
    post('/api/file/compress', { path: paths, format: fmt, name: nm }).then(function (r) {
      if (r.job) watchJob(r.job, '压缩');
      else toast(r.err || '失败', 'err');
    });
  }

  function fileExtract(full) {
    if (!confirm('解压「' + full.split('/').pop() + '」到当前目录？')) return;
    post('/api/file/extract', { path: full }).then(function (r) {
      if (r.job) watchJob(r.job, '解压');
      else toast(r.err || '失败', 'err');
    });
  }

  function fileShare(full) {
    post('/api/shares', { act: 'create', path: full }).then(function (r) {
      if (!r.ok) { toast(r.err || '失败', 'err'); return; }
      var url = location.origin + '/s/' + r.token;
      navigator.clipboard.writeText(url).then(function () { toast('分享链接已生成并复制'); }, function () {
        prompt('分享链接（复制它）：', url);
      });
    });
  }

  function extOf(name) {
    var i = name.lastIndexOf('.');
    return i > 0 ? name.slice(i + 1).toUpperCase() : '文件';
  }

  /* ---------------- 预览 ---------------- */
  function preview(path, name) {
    api('/api/preview?path=' + encodeURIComponent(path)).then(function (r) {
      var m = $('#previewModal');
      $('#previewTitle').textContent = name;
      var body = $('#previewBody');
      if (!r.ok) { body.innerHTML = '<div class="empty">' + (r.err || '无法预览') + '</div>'; }
      else if (r.kind === 'image') { body.innerHTML = '<img src="' + r.url + '" alt="">'; }
      else { body.innerHTML = '<pre class="preview-text"></pre>'; body.querySelector('pre').textContent = r.text; }
      m.hidden = false;
    }).catch(function () { toast('预览失败', 'err'); });
  }

  $('#previewClose').addEventListener('click', function () { $('#previewModal').hidden = true; });
  $('#previewModal').addEventListener('click', function (e) {
    if (e.target === this) this.hidden = true;
  });

  function showLog(title, text) {
    $('#previewTitle').textContent = title;
    var body = $('#previewBody');
    body.innerHTML = '<pre class="preview-text"></pre>';
    body.querySelector('pre').textContent = text || '（无输出）';
    $('#previewModal').hidden = false;
  }

  $('#fileSearch').addEventListener('input', function () {
    state.query = this.value;
    renderFiles(state.files, state.parent);
  });

  $('#fileSort').addEventListener('change', function () {
    state.sort = this.value;
    renderFiles(state.files, state.parent);
  });

  $('#fileView').addEventListener('change', function () {
    state.fileView = this.value;
    localStorage.setItem('covernas.fileview', state.fileView);
    renderFiles(state.files, state.parent);
  });

  $('#btnNewFile').addEventListener('click', function () {
    var name = prompt('新建文件名称（含扩展名）');
    if (!name) return;
    post('/api/file/new', { path: state.path, name: name }).then(function (r) {
      if (r.ok) { toast('已创建'); loadFiles(state.path); }
      else toast(r.err || '失败', 'err');
    });
  });

  /* ---------------- 选择栏 / 剪贴板 ---------------- */
  $$('[data-sel]').forEach(function (b) {
    b.addEventListener('click', function () {
      var act = b.dataset.sel;
      var items = selList();
      if (act === 'clear') return clearSel();
      if (!items.length) return;
      if (act === 'del') {
        if (!confirm('删除选中的 ' + items.length + ' 项？会移到回收站。')) return;
        var done = 0, fail = 0;
        items.forEach(function (p) {
          post('/api/delete', { path: p }).then(function (r) {
            r.ok ? done++ : fail++;
            if (done + fail === items.length) {
              toast('已删除 ' + done + ' 项' + (fail ? '，失败 ' + fail : ''), fail ? 'err' : 'ok');
              clearSel();
              loadFiles(state.path);
            }
          });
        });
        return;
      }
      state.clip = { mode: act === 'copy' ? 'copy' : 'move', items: items };
      $('#clipBar').hidden = false;
      $('#clipText').textContent = (act === 'copy' ? '已复制 ' : '已剪切 ') + items.length + ' 项，去目标目录点粘贴';
      clearSel();
    });
  });

  $('#btnPaste').addEventListener('click', function () {
    if (!state.clip) return;
    var fd = new URLSearchParams();
    fd.append('dst', state.path);
    fd.append('mode', state.clip.mode);
    state.clip.items.forEach(function (p) { fd.append('src', p); });
    fetch('/api/files/move', { method: 'POST', body: fd, credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (r) {
        if (r.ok) {
          toast((state.clip.mode === 'copy' ? '已复制 ' : '已移动 ') + r.done.length + ' 项');
          state.clip = null;
          $('#clipBar').hidden = true;
          loadFiles(state.path);
        } else toast(r.err || '失败', 'err');
      });
  });

  $('#btnClipCancel').addEventListener('click', function () {
    state.clip = null;
    $('#clipBar').hidden = true;
  });


  $('#btnRefresh').addEventListener('click', function () { loadFiles(state.path); });

  $('#btnMkdir').addEventListener('click', function () {
    var name = prompt('新建文件夹名称');
    if (!name) return;
    post('/api/mkdir', { path: state.path, name: name }).then(function (r) {
      if (r.ok) { toast('已创建'); loadFiles(state.path); }
      else toast(r.err || '失败', 'err');
    });
  });

  $('#btnUpload').addEventListener('click', function () { $('#fileInput').click(); });

  $('#fileInput').addEventListener('change', function () {
    var files = this.files;
    if (!files || !files.length) return;
    upload(files);
    this.value = '';
  });

  function upload(files) {
    var fd = new FormData();
    fd.append('path', state.path);
    for (var i = 0; i < files.length; i++) fd.append('files', files[i]);
    var total = 0;
    for (var t = 0; t < files.length; t++) total += files[t].size || 0;
    var bar = $('#upBar');
    if (!bar) {
      bar = document.createElement('div');
      bar.id = 'upBar';
      bar.className = 'up-bar';
      bar.innerHTML = '<div class="up-txt"><span id="upName">准备上传…</span><b id="upPct">0%</b></div>' +
        '<div class="up-track"><i id="upFill" style="width:0"></i></div>';
      document.body.appendChild(bar);
    }
    bar.hidden = false;
    $('#upName').textContent = '正在上传 ' + files.length + ' 个文件（' + fmtBytes(total) + '）';
    $('#upPct').textContent = '0%';
    $('#upFill').style.width = '0%';

    var xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/upload');
    xhr.withCredentials = true;
    xhr.upload.onprogress = function (e) {
      if (!e.lengthComputable) return;
      var pct = Math.min(100, Math.round(e.loaded * 100 / e.total));
      $('#upPct').textContent = pct + '%';
      $('#upFill').style.width = pct + '%';
    };
    xhr.onload = function () {
      bar.hidden = true;
      var r = {};
      try { r = JSON.parse(xhr.responseText || '{}'); } catch (e) {}
      if (r.ok) { toast('已上传 ' + r.saved.length + ' 个文件'); loadFiles(state.path); }
      else toast(r.err || '上传失败', 'err');
    };
    xhr.onerror = function () { bar.hidden = true; toast('上传失败', 'err'); };
    xhr.send(fd);
  }

  // 拖拽上传
  var pane = $('#view-files .pane');
  ['dragenter', 'dragover'].forEach(function (ev) {
    pane.addEventListener(ev, function (e) { e.preventDefault(); pane.classList.add('dragging'); });
  });
  ['dragleave', 'drop'].forEach(function (ev) {
    pane.addEventListener(ev, function (e) {
      e.preventDefault();
      if (ev === 'dragleave' && e.relatedTarget && pane.contains(e.relatedTarget)) return;
      pane.classList.remove('dragging');
    });
  });
  pane.addEventListener('drop', function (e) {
    if (e.dataTransfer.files.length) upload(e.dataTransfer.files);
  });

  /* ---------------- 服务 ---------------- */
  function loadServices() {
    api('/api/services').then(function (r) {
      if (!r.ok) return;
      var on = r.services.filter(function (s) { return s.state === 'active'; }).length;
      $('#svcCount').textContent = on + ' / ' + r.services.length + ' 运行中';
      var box = $('#svcList');
      box.innerHTML = '';
      r.services.forEach(function (s) {
        var active = s.state === 'active';
        var row = document.createElement('div');
        row.className = 'row';
        row.innerHTML =
          '<span class="row-ic">' + icon('layers') + '</span>' +
          '<div class="row-main">' +
            '<div class="row-name">' + s.name + ' <span class="tag ' + (active ? 'on' : '') + '">' +
            (active ? '运行中' : s.state) + '</span></div>' +
            '<div class="row-sub">' + s.desc + ' · ' + s.unit + '</div>' +
          '</div>' +
          '<div class="ops">' +
            '<button class="btn btn-sm ' + (active ? 'btn-ghost' : '') + '" data-op="toggle">' +
            (active ? '停止' : '启动') + '</button>' +
            '<button class="btn btn-sm btn-ghost" data-op="restart" ' + (active ? '' : 'disabled') + '>重启</button>' +
            '<button class="btn btn-sm btn-ghost" data-op="log">日志</button>' +
          '</div>';
        box.appendChild(row);
      });

      $$('.row', box).forEach(function (row, i) {
        var s = r.services[i];
        $$('[data-op]', row).forEach(function (b) {
          b.addEventListener('click', function () {
            var op = b.dataset.op;
            if (op === 'log') {
              showLog(s.name + ' 的日志', '读取中…');
              api('/api/logs?unit=' + encodeURIComponent(s.unit)).then(function (res) {
                showLog(s.name + ' 的日志', res.text || '（无输出）');
              });
              return;
            }
            b.disabled = true;
            var action = op === 'restart' ? 'restart' : (s.state === 'active' ? 'stop' : 'start');
            post('/api/service', { unit: s.unit, op: action }).then(function (res) {
              toast(s.unit + (res.state === 'active' ? ' 运行中' : ' 已停止'), res.state === 'active' ? 'ok' : 'err');
              loadServices();
            }).catch(function () { toast('操作失败', 'err'); b.disabled = false; });
          });
        });
      });
    });
  }

  /* ---------------- 存储 ---------------- */
  function loadStorage() {
    api('/api/storage').then(function (r) {
      if (!r.ok) return;
      var box = $('#storeList');
      box.innerHTML = '';
      r.mounts.forEach(function (m) {
        var cls = m.pct >= 90 ? 'bad' : (m.pct >= 75 ? 'warn' : '');
        var d = document.createElement('div');
        d.className = 'store-row';
        d.innerHTML =
          '<div class="store-top"><span><code>' + m.dev + '</code> → ' + m.mount + '</span><b>' + m.pct + '%</b></div>' +
          '<div class="bar ' + cls + '"><i style="width:' + m.pct + '%"></i></div>' +
          '<div class="store-sub">已用 ' + fmtBytes(m.used) + ' · 可用 ' + fmtBytes(m.free) + ' · 共 ' + fmtBytes(m.total) + '</div>';
        box.appendChild(d);
      });
      $('#lsblk').textContent = r.lsblk || '（无输出）';
    });
  }

  /* ---------------- 相册 ---------------- */
  var photoList = [], photoIdx = 0, photoAlbums = [], slidesTimer = null;
  state.photoView = localStorage.getItem('covernas.photoview') || 'gallery';

  function renderPhotos() {
    var g = $('#gallery');
    var view = state.photoView;
    g.className = 'gallery pv-' + view;
    if (!photoList.length) return;
    if (view === 'list') {
      g.innerHTML = photoList.map(function (p, i) {
        return '<button class="ph ph-row" data-i="' + i + '">' +
          '<img loading="lazy" src="/api/raw?path=' + encodeURIComponent(p.path) + '" alt="">' +
          '<span class="ph-main"><b>' + p.name + '</b><i>' + p.size_h + ' · ' + fmtTime(p.mtime) + '</i></span>' +
          '</button>';
      }).join('');
    } else {
      g.innerHTML = photoList.map(function (p, i) {
        return '<button class="ph" data-i="' + i + '">' +
          '<img loading="lazy" src="/api/raw?path=' + encodeURIComponent(p.path) + '" alt="">' +
          (view === 'icons' ? '' : '<span>' + p.name + '</span>') +
          '</button>';
      }).join('');
    }
    $$('.ph', g).forEach(function (el) {
      el.addEventListener('click', function () { openLightbox(Number(el.dataset.i)); });
    });
  }

  function fillSelect(sel, items, emptyLabel, current) {
    var opts = ['<option value="">' + emptyLabel + '</option>'];
    items.forEach(function (it) {
      var val = typeof it === 'string' ? it : it.value;
      var label = typeof it === 'string' ? it.replace('/mnt', '') || '/mnt' : it.label;
      opts.push('<option value="' + val + '">' + label + '</option>');
    });
    sel.innerHTML = opts.join('');
    sel.value = current || '';
  }

  function loadPhotos() {
    var alb = $('#photoAlbum').value || '';
    var dir = $('#photoDir').value || '';
    var g = $('#gallery');
    g.innerHTML = '<div class="empty">扫描中…</div>';
    var url = '/api/photos?path=/mnt';
    if (alb) url += '&album=' + encodeURIComponent(alb);
    else if (dir) url += '&dir=' + encodeURIComponent(dir);
    api(url).then(function (r) {
      if (!r.ok) { g.innerHTML = '<div class="empty">读取失败</div>'; return; }
      photoList = r.items || [];
      photoAlbums = r.albums || [];

      var aSel = $('#photoAlbum');
      var curA = aSel.value;
      fillSelect(aSel, photoAlbums.map(function (x) {
        return { value: x.id, label: x.name + ' · ' + x.items.length };
      }), '全部照片', curA);

      var dSel = $('#photoDir');
      var curD = dSel.value;
      fillSelect(dSel, r.dirs || [], '所有目录', curD);

      $('#photoCount').textContent = photoList.length + ' 张';
      var pv = $('#photoView');
      if (pv) pv.value = state.photoView;
      if (!photoList.length) {
        g.innerHTML = '<div class="empty">' + (alb ? '这个相册还是空的' : '这里还没有图片') + '</div>';
        return;
      }
      renderPhotos();
      var deep = (location.hash || '').match(/^#photos:(\d+)/);
      if (deep) openLightbox(Number(deep[1]));
    }).catch(function () { g.innerHTML = '<div class="empty">加载失败</div>'; });
  }

  $('#photoView').addEventListener('change', function () {
    state.photoView = this.value;
    localStorage.setItem('covernas.photoview', state.photoView);
    renderPhotos();
  });

  function openLightbox(i) {
    if (!photoList.length) return;
    photoIdx = (i + photoList.length) % photoList.length;
    var p = photoList[photoIdx];
    $('#lbImg').src = '/api/raw?path=' + encodeURIComponent(p.path);
    $('#lbName').textContent = p.name;
    $('#lbMeta').textContent = p.size_h + ' · ' + fmtTime(p.mtime) +
      ' · ' + (photoIdx + 1) + ' / ' + photoList.length;
    $('#lightbox').hidden = false;
  }

  function closeLightbox() {
    $('#lightbox').hidden = true;
    stopSlides();
  }

  function stepPhoto(d) {
    if (!photoList.length) return;
    openLightbox(photoIdx + d);
  }

  function stopSlides() {
    if (slidesTimer) { clearInterval(slidesTimer); slidesTimer = null; }
    var b = $('#lbSlides');
    if (b) b.classList.remove('on');
  }

  function toggleSlides() {
    if (slidesTimer) { stopSlides(); return; }
    if (!photoList.length) return;
    $('#lbSlides').classList.add('on');
    slidesTimer = setInterval(function () { stepPhoto(1); }, 3000);
    toast('幻灯片开始，每 3 秒一张');
  }

  $('#lbClose').addEventListener('click', closeLightbox);
  $('#lbPrev').addEventListener('click', function (e) { e.stopPropagation(); stepPhoto(-1); });
  $('#lbNext').addEventListener('click', function (e) { e.stopPropagation(); stepPhoto(1); });
  $('#lbSlides').addEventListener('click', toggleSlides);
  $('#lightbox').addEventListener('click', function (e) {
    if (e.target === this) closeLightbox();
  });

  $('#lbDownload').addEventListener('click', function () {
    var p = photoList[photoIdx];
    if (p) location.href = '/api/download?path=' + encodeURIComponent(p.path);
  });

  $('#lbDelete').addEventListener('click', function () {
    var p = photoList[photoIdx];
    if (!p || !confirm('删除「' + p.name + '」？会移到回收站。')) return;
    post('/api/delete', { path: p.path }).then(function (r) {
      if (!r.ok) { toast(r.err || '删除失败', 'err'); return; }
      toast('已移到回收站');
      photoList.splice(photoIdx, 1);
      if (!photoList.length) { closeLightbox(); loadPhotos(); return; }
      openLightbox(Math.min(photoIdx, photoList.length - 1));
    });
  });

  $('#lbAdd').addEventListener('click', function () {
    var p = photoList[photoIdx];
    if (!p) return;
    if (!photoAlbums.length) {
      var nm = prompt('还没有相册，先起个名字：', '我的相册');
      if (!nm) return;
      post('/api/albums', { act: 'create', name: nm }).then(function (r) {
        if (!r.ok) { toast(r.err || '失败', 'err'); return; }
        var id = r.id;
        post('/api/albums', { act: 'add', id: id, path: p.path }).then(function () {
          toast('已加入「' + nm + '」'); loadPhotos();
        });
      });
      return;
    }
    var names = photoAlbums.map(function (a, i) { return (i + 1) + '. ' + a.name; }).join('\n');
    var pick = prompt('加入哪个相册？（输入序号）\n' + names, '1');
    var idx = parseInt(pick, 10);
    if (!idx || !photoAlbums[idx - 1]) return;
    var alb = photoAlbums[idx - 1];
    post('/api/albums', { act: 'add', id: alb.id, path: p.path }).then(function (r) {
      if (r.ok) { toast('已加入「' + alb.name + '」'); loadPhotos(); }
    });
  });

  $('#albumNew').addEventListener('click', function () {
    var nm = prompt('新相册名称：', '我的相册');
    if (!nm) return;
    post('/api/albums', { act: 'create', name: nm }).then(function (r) {
      if (r.ok) { toast('相册已创建'); loadPhotos(); }
      else toast(r.err || '失败', 'err');
    });
  });

  $('#photoDir').addEventListener('change', function () {
    $('#photoAlbum').value = '';
    loadPhotos();
  });
  $('#photoAlbum').addEventListener('change', loadPhotos);
  $('#photoRefresh').addEventListener('click', loadPhotos);
  $('#photoSlides').addEventListener('click', function () {
    if (!photoList.length) { toast('先选一个目录', 'err'); return; }
    openLightbox(0);
    toggleSlides();
  });

  /* ---------------- 媒体 / 音乐 ---------------- */
  var videos = [], vidIdx = -1;
  var tracks = [], trackIdx = -1, loopMode = 0, shuffleOn = false;

  function fmtDur(sec) {
    sec = Math.max(0, Math.floor(sec || 0));
    var m = Math.floor(sec / 60), s = sec % 60;
    return m + ':' + (s < 10 ? '0' + s : s);
  }

  function mediaRow(item, kind, idx) {
    var row = document.createElement('div');
    row.className = 'row';
    row.innerHTML =
      '<span class="row-ic">' + icon(kind === 'audio' ? 'music' : 'play') + '</span>' +
      '<div class="row-main"><div class="row-name">' + item.name + '</div>' +
      '<div class="row-sub">' + item.size_h + ' · ' + fmtTime(item.mtime) + '</div></div>' +
      '<button class="btn btn-sm">播放</button>';
    row.addEventListener('click', function () {
      if (kind === 'audio') playTrack(idx);
      else playVideo(idx);
    });
    return row;
  }

  /* ---- 视频 ---- */
  function loadMedia() {
    var box = $('#mediaList');
    var dir = $('#mediaDir').value || '';
    box.innerHTML = '<div class="empty">扫描中…</div>';
    api('/api/media?path=/mnt' + (dir ? '&dir=' + encodeURIComponent(dir) : '')).then(function (r) {
      if (!r.ok) return;
      videos = r.video || [];
      var curD = $('#mediaDir').value;
      fillSelect($('#mediaDir'), r.dirs || [], '所有目录', curD);
      $('#mediaCount').textContent = videos.length + ' 个视频';
      box.innerHTML = '';
      if (!videos.length) { box.innerHTML = '<div class="empty">这里还没有视频</div>'; return; }
      videos.forEach(function (v, i) { box.appendChild(mediaRow(v, 'video', i)); });
    }).catch(function () { box.innerHTML = '<div class="empty">加载失败</div>'; });
  }

  function playVideo(i) {
    if (i < 0 || i >= videos.length) return;
    vidIdx = i;
    var v = videos[i];
    var el = $('#videoEl');
    $('#videoBox').hidden = false;
    $('#videoName').textContent = v.name;
    el.src = '/api/raw?path=' + encodeURIComponent(v.path);
    var saved = parseFloat(localStorage.getItem('box.vpos.' + v.path) || '0');
    if (saved > 5) {
      el.addEventListener('loadedmetadata', function once() {
        el.removeEventListener('loadedmetadata', once);
        if (saved < el.duration - 10) {
          el.currentTime = saved;
          toast('从 ' + fmtDur(saved) + ' 继续播放');
        }
      });
    }
    el.playbackRate = Number($('#mediaSpeed').value) || 1;
    el.play().catch(function () {});
    $('#videoBox').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  $('#videoEl').addEventListener('timeupdate', function () {
    if (vidIdx < 0) return;
    var v = videos[vidIdx];
    if (!v) return;
    if (Math.floor(this.currentTime) % 5 === 0) {
      try { localStorage.setItem('box.vpos.' + v.path, String(Math.floor(this.currentTime))); } catch (e) {}
    }
  });

  $('#videoEl').addEventListener('ended', function () {
    if (vidIdx + 1 < videos.length) playVideo(vidIdx + 1);
  });

  $('#videoNext').addEventListener('click', function () {
    if (vidIdx < 0) { toast('先播放一个视频', 'err'); return; }
    if (vidIdx + 1 >= videos.length) { toast('已经是最后一个了'); return; }
    playVideo(vidIdx + 1);
  });

  $('#mediaSpeed').addEventListener('change', function () {
    $('#videoEl').playbackRate = Number(this.value) || 1;
    toast('播放速度 ' + this.value + '×');
  });

  $('#mediaDir').addEventListener('change', loadMedia);
  $('#mediaRefresh').addEventListener('click', loadMedia);

  /* ---- 音乐 ---- */
  function loadMusic() {
    var box = $('#musicList');
    var dir = $('#musicDir').value || '';
    box.innerHTML = '<div class="empty">扫描中…</div>';
    api('/api/media?path=/mnt' + (dir ? '&dir=' + encodeURIComponent(dir) : '')).then(function (r) {
      if (!r.ok) return;
      tracks = r.audio || [];
      var curD = $('#musicDir').value;
      fillSelect($('#musicDir'), r.dirs || [], '所有目录', curD);
      $('#musicCount').textContent = tracks.length + ' 首' + (curD ? '' : ' · 全部目录');
      box.innerHTML = '';
      if (!tracks.length) { box.innerHTML = '<div class="empty">这里还没有音频</div>'; return; }
      tracks.forEach(function (t, i) {
        var row = document.createElement('div');
        row.className = 'row';
        row.innerHTML =
          '<span class="row-ic">' + icon('music') + '</span>' +
          '<div class="row-main"><div class="row-name">' + t.name + '</div>' +
          '<div class="row-sub">' + t.size_h + ' · ' + fmtTime(t.mtime) + '</div></div>' +
          '<button class="btn btn-sm">播放</button>';
        row.addEventListener('click', function () { playTrack(i); });
        box.appendChild(row);
      });
      highlightTrack();
    }).catch(function () { box.innerHTML = '<div class="empty">加载失败</div>'; });
  }

  function highlightTrack() {
    $$('#musicList .row').forEach(function (r, i) {
      r.classList.toggle('playing', i === trackIdx);
    });
  }

  function playTrack(i) {
    if (i < 0 || i >= tracks.length) return;
    trackIdx = i;
    var t = tracks[i];
    var el = $('#audioEl');
    el.src = '/api/raw?path=' + encodeURIComponent(t.path);
    el.play().catch(function () {});
    $('#mpTitle').textContent = t.name.replace(/\.[^.]+$/, '');
    $('#mpSub').textContent = (t.path.split('/').slice(-2, -1)[0] || '') + ' · ' + t.size_h;
    $('#mpPlay').innerHTML = icon('pause');
    highlightTrack();
  }

  function togglePlay() {
    var el = $('#audioEl');
    if (!el.src) { if (tracks.length) playTrack(0); return; }
    if (el.paused) { el.play().catch(function () {}); $('#mpPlay').innerHTML = icon('pause'); }
    else { el.pause(); $('#mpPlay').innerHTML = icon('play'); }
  }

  function nextTrack(auto) {
    if (!tracks.length) return;
    if (shuffleOn) {
      playTrack(Math.floor(Math.random() * tracks.length));
      return;
    }
    var n = trackIdx + 1;
    if (n >= tracks.length) {
      if (loopMode === 0 && auto) { $('#mpPlay').innerHTML = icon('play'); return; }
      n = 0;
    }
    playTrack(n);
  }

  function prevTrack() {
    if (!tracks.length) return;
    playTrack(trackIdx - 1 < 0 ? tracks.length - 1 : trackIdx - 1);
  }

  $('#mpPlay').addEventListener('click', togglePlay);
  $('#mpNext').addEventListener('click', function () { nextTrack(false); });
  $('#mpPrev').addEventListener('click', prevTrack);

  $('#mpLoop').addEventListener('click', function () {
    loopMode = (loopMode + 1) % 3;
    var el = $('#audioEl');
    el.loop = loopMode === 2;
    this.classList.toggle('on', loopMode > 0);
    this.title = loopMode === 0 ? '顺序播放' : (loopMode === 1 ? '列表循环' : '单曲循环');
    toast(this.title);
  });

  $('#mpShuffle').addEventListener('click', function () {
    shuffleOn = !shuffleOn;
    this.classList.toggle('on', shuffleOn);
    toast(shuffleOn ? '随机播放已开' : '随机播放已关');
  });

  $('#mpVol').addEventListener('input', function () {
    $('#audioEl').volume = Number(this.value) / 100;
  });

  $('#mpSeek').addEventListener('input', function () {
    var el = $('#audioEl');
    if (el.duration) el.currentTime = el.duration * Number(this.value) / 1000;
  });

  $('#audioEl').addEventListener('timeupdate', function () {
    if (!this.duration) return;
    $('#mpSeek').value = Math.round(this.currentTime / this.duration * 1000);
    $('#mpCur').textContent = fmtDur(this.currentTime);
  });

  $('#audioEl').addEventListener('loadedmetadata', function () {
    $('#mpDur').textContent = fmtDur(this.duration);
  });

  $('#audioEl').addEventListener('ended', function () { nextTrack(true); });
  $('#musicDir').addEventListener('change', loadMusic);

  /* 全局快捷键 */
  document.addEventListener('keydown', function (e) {
    var lb = $('#lightbox');
    if (lb && !lb.hidden) {
      if (e.key === 'Escape') closeLightbox();
      if (e.key === 'ArrowLeft') stepPhoto(-1);
      if (e.key === 'ArrowRight') stepPhoto(1);
      return;
    }
    if (e.target.matches('input, textarea, select')) return;
    if (e.key === ' ' && state.view === 'music') { e.preventDefault(); togglePlay(); }
  });

  /* ---------------- 记事本 ---------------- */
  var noteCur = '';

  function loadNotes() {
    api('/api/notes').then(function (r) {
      if (!r.ok) return;
      var box = $('#noteList');
      box.innerHTML = '';
      if (!r.notes.length) {
        box.innerHTML = '<div class="empty">还没有笔记</div>';
        $('#noteTitle').value = '';
        $('#noteBody').value = '';
        noteCur = '';
        return;
      }
      r.notes.forEach(function (n) {
        var row = document.createElement('div');
        row.className = 'row' + (n.id === noteCur ? ' cur' : '');
        row.innerHTML =
          '<span class="row-ic">' + icon('file') + '</span>' +
          '<div class="row-main"><div class="row-name">' + (n.title || '未命名') + '</div>' +
          '<div class="row-sub">' + fmtTime(n.updated) + '</div></div>';
        row.addEventListener('click', function () {
          noteCur = n.id;
          $('#noteTitle').value = n.title || '';
          $('#noteBody').value = n.body || '';
          loadNotes();
        });
        box.appendChild(row);
      });
      if (!noteCur) {
        noteCur = r.notes[0].id;
        $('#noteTitle').value = r.notes[0].title || '';
        $('#noteBody').value = r.notes[0].body || '';
      }
    });
  }

  $('#noteNew').addEventListener('click', function () {
    noteCur = '';
    $('#noteTitle').value = '';
    $('#noteBody').value = '';
    $('#noteTitle').focus();
  });

  $('#noteSave').addEventListener('click', function () {
    post('/api/notes', {
      act: 'save', id: noteCur,
      title: $('#noteTitle').value || '未命名',
      body: $('#noteBody').value
    }).then(function (r) {
      if (r.ok) { noteCur = r.id; toast('已保存'); loadNotes(); }
      else toast(r.err || '保存失败', 'err');
    });
  });

  $('#noteDel').addEventListener('click', function () {
    if (!noteCur || !confirm('删除这条笔记？')) return;
    post('/api/notes', { act: 'delete', id: noteCur }).then(function (r) {
      if (r.ok) { noteCur = ''; toast('已删除'); loadNotes(); }
    });
  });

  /* ---------------- 计算器 ---------------- */
  var calcInited = false, calcExpr = '';

  function initCalc() {
    if (calcInited) return;
    calcInited = true;
    var keys = ['C', '(', ')', '÷', '7', '8', '9', '×', '4', '5', '6', '−', '1', '2', '3', '+', '0', '.', '⌫', '='];
    var box = $('#calcKeys');
    keys.forEach(function (k) {
      var b = document.createElement('button');
      b.className = 'ck' + ('=+-×÷'.indexOf(k) > -1 || k === '=' ? ' op' : '') + (k === '=' ? ' eq' : '');
      b.textContent = k;
      b.addEventListener('click', function () { calcKey(k); });
      box.appendChild(b);
    });
  }

  function calcKey(k) {
    var scr = $('#calcScreen');
    if (k === 'C') { calcExpr = ''; scr.textContent = '0'; return; }
    if (k === '⌫') { calcExpr = calcExpr.slice(0, -1); scr.textContent = calcExpr || '0'; return; }
    if (k === '=') {
      var e = calcExpr.replace(/×/g, '*').replace(/÷/g, '/').replace(/−/g, '-');
      if (!/^[0-9+\-*/.() ]+$/.test(e)) { scr.textContent = '错误'; calcExpr = ''; return; }
      try {
        var v = Function('"use strict";return (' + e + ')')();
        calcExpr = String(Math.round(v * 1e8) / 1e8);
        scr.textContent = calcExpr;
      } catch (err) { scr.textContent = '错误'; calcExpr = ''; }
      return;
    }
    calcExpr += k;
    scr.textContent = calcExpr;
  }

  /* ---------------- 计划任务 ---------------- */
  var cronRows = [];   // {m,h,dom,mon,dow,cmd}

  function parseCron(text) {
    var rows = [];
    (text || '').split('\n').forEach(function (line) {
      var s = line.trim();
      if (!s || s.indexOf('#') === 0 || s.indexOf('=') > -1 && s.indexOf(' ') < 0) return;
      var m = s.match(/^(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(.+)$/);
      if (m) rows.push({ m: m[1], h: m[2], dom: m[3], mon: m[4], dow: m[5], cmd: m[6] });
    });
    return rows;
  }

  function cronText() {
    return cronRows.map(function (r) {
      return [r.m, r.h, r.dom, r.mon, r.dow, r.cmd].join(' ');
    }).join('\n');
  }

  function cronHuman(r) {
    var hm = r.m + ':' + r.h;
    if (r.m === '*' && r.h === '*') return '每分钟';
    if (r.h === '*' ) return '每小时的第 ' + r.m + ' 分';
    if (r.dom === '*' && r.mon === '*' && r.dow === '*') return '每天 ' + hm;
    if (r.dow !== '*') return '每周 ' + r.dow.replace('1', '一').replace('2', '二')
      .replace('3', '三').replace('4', '四').replace('5', '五') + ' ' + hm;
    if (r.dom !== '*') return '每月 ' + r.dom + ' 日 ' + hm;
    return hm;
  }

  function renderCron() {
    var box = $('#cronList');
    box.innerHTML = '';
    $('#cronCount').textContent = cronRows.length ? cronRows.length + ' 个任务' : '没有任务';
    if (!cronRows.length) {
      box.innerHTML = '<div class="empty">还没有计划任务。下面填一条试试，比如每天 3 点把文档同步到备份盘。</div>';
    }
    cronRows.forEach(function (r, i) {
      var row = document.createElement('div');
      row.className = 'row';
      row.innerHTML =
        '<span class="row-ic">' + icon('clock') + '</span>' +
        '<div class="row-main">' +
          '<div class="row-name">' + cronHuman(r) + ' <span class="tag">' +
            [r.m, r.h, r.dom, r.mon, r.dow].join(' ') + '</span></div>' +
          '<div class="row-sub mono">' + r.cmd + '</div>' +
        '</div>' +
        '<div class="row-act"><button class="danger" title="删除">' + icon('trash') + '</button></div>';
      row.querySelector('button').addEventListener('click', function () {
        if (!confirm('删除这条计划任务？')) return;
        cronRows.splice(i, 1);
        pushCron();
      });
      box.appendChild(row);
    });
  }

  function pushCron() {
    post('/api/cron', { text: cronText() }).then(function (r) {
      if (r.ok) { toast('已保存'); renderCron(); $('#cronText').value = cronText(); }
      else toast(r.err || '保存失败', 'err');
    });
  }

  function loadCron() {
    api('/api/cron').then(function (r) {
      if (!r.ok) return;
      $('#cronText').value = r.text || '';
      cronRows = parseCron(r.text);
      renderCron();
    });
  }

  $('#cronForm').addEventListener('submit', function (e) {
    e.preventDefault();
    var fd = new FormData(this);
    var cmd = (fd.get('cmd') || '').trim();
    if (!cmd) { toast('命令不能为空', 'err'); return; }
    cronRows.push({
      m: fd.get('m') || '*', h: fd.get('h') || '*', dom: fd.get('dom') || '*',
      mon: fd.get('mon') || '*', dow: fd.get('dow') || '*', cmd: cmd
    });
    this.reset();
    this.m.value = '0'; this.h.value = '3';
    this.dom.value = '*'; this.mon.value = '*'; this.dow.value = '*';
    pushCron();
  });

  $('#cronPreset').addEventListener('click', function () {
    var f = $('#cronForm');
    var pick = prompt('常用周期：\n1 = 每天 3:00\n2 = 每小时\n3 = 每周一 4:00\n4 = 每 10 分钟', '1');
    if (pick === '1') { f.m.value = '0'; f.h.value = '3'; f.dom.value = '*'; f.mon.value = '*'; f.dow.value = '*'; }
    if (pick === '2') { f.m.value = '0'; f.h.value = '*'; }
    if (pick === '3') { f.m.value = '0'; f.h.value = '4'; f.dow.value = '1'; }
    if (pick === '4') { f.m.value = '*/10'; f.h.value = '*'; }
  });

  $('#cronRawBtn').addEventListener('click', function () {
    var raw = $('#cronRaw');
    raw.hidden = !raw.hidden;
    this.textContent = raw.hidden ? '原始文本' : '图形视图';
    if (!raw.hidden) $('#cronText').value = cronText();
  });

  $('#cronSave').addEventListener('click', function () {
    var raw = $('#cronRaw');
    if (!raw.hidden) { cronRows = parseCron($('#cronText').value); }
    pushCron();
  });

  /* ---------------- Docker ---------------- */
  function loadDocker() {
    var box = $('#dockerList');
    box.innerHTML = '<div class="empty">读取中…</div>';
    api('/api/docker').then(function (r) {
      if (!r.ok) return;
      $('#dockerVer').textContent = r.version || '未安装';
      box.innerHTML = '';
      if (!r.containers.length) { box.innerHTML = '<div class="empty">还没有容器</div>'; return; }
      r.containers.forEach(function (c) {
        var running = c.state === 'running';
        var row = document.createElement('div');
        row.className = 'row';
        row.innerHTML =
          '<span class="row-ic">' + icon('box') + '</span>' +
          '<div class="row-main"><div class="row-name">' + c.name +
            ' <span class="tag ' + (running ? 'on' : '') + '">' + c.state + '</span></div>' +
            '<div class="row-sub">' + c.image + ' · ' + c.status + '</div></div>' +
          '<div class="ops">' +
            '<button class="btn btn-sm ' + (running ? 'btn-ghost' : '') + '" data-op="toggle">' + (running ? '停止' : '启动') + '</button>' +
            '<button class="btn btn-sm btn-ghost" data-op="restart">重启</button>' +
            '<button class="btn btn-sm btn-ghost" data-op="log">日志</button>' +
            '<button class="btn btn-sm btn-danger" data-op="rm">删除</button>' +
          '</div>';

        $$('[data-op]', row).forEach(function (b) {
          b.addEventListener('click', function (e) {
            e.stopPropagation();
            var op = b.dataset.op;
            if (op === 'log') {
              showLog(c.name + ' 日志', '读取中…');
              api('/api/logs?name=' + encodeURIComponent(c.name)).then(function (res) {
                showLog(c.name + ' 日志', res.text || '（无输出）');
              });
              return;
            }
            if (op === 'rm') {
              if (!confirm('删除容器「' + c.name + '」？容器内的数据会丢失。')) return;
              b.disabled = true;
              post('/api/docker/remove', { name: c.name, force: '1' }).then(function (res) {
                toast(res.ok ? '已删除' : (res.err || '删除失败'), res.ok ? 'ok' : 'err');
                loadDocker();
              });
              return;
            }
            b.disabled = true;
            var action = op === 'restart' ? 'restart' : (running ? 'stop' : 'start');
            post('/api/docker', { name: c.name, op: action }).then(function (res) {
              toast(res.ok ? '操作成功' : (res.err || '失败'), res.ok ? 'ok' : 'err');
              loadDocker();
            }).catch(function () { b.disabled = false; });
          });
        });
        box.appendChild(row);
      });
    }).catch(function () { box.innerHTML = '<div class="empty">Docker 不可用</div>'; });
  }

  $('#dockerForm').addEventListener('submit', function (e) {
    e.preventDefault();
    var fd = new FormData(this);
    post('/api/docker/run', {
      image: fd.get('image'), name: fd.get('name'),
      ports: fd.get('ports'), volumes: fd.get('volumes'), envs: fd.get('envs')
    }).then(function (r) {
      if (!r.ok) { toast(r.err || '失败', 'err'); return; }
      toast('正在拉取镜像并启动…');
      var t = setInterval(function () {
        api('/api/job?id=' + encodeURIComponent(r.job)).then(function (j) {
          if (!j.ok || j.running) return;
          clearInterval(t);
          if (j.rc === 0) { toast('容器已启动'); $('#dockerForm').reset(); loadDocker(); }
          else { toast('启动失败', 'err'); showLog('容器启动失败', j.text); }
        }).catch(function () { clearInterval(t); });
      }, 1800);
    });
  });

  /* ---------------- 任务管理器 ---------------- */
  function loadTasks() {
    api('/api/processes').then(function (r) {
      var box = $('#taskList');
      if (!r.ok) { box.innerHTML = '<div class="empty">读取失败</div>'; return; }
      $('#taskCount').textContent = r.items.length + ' 个进程';
      box.innerHTML = '';
      r.items.forEach(function (p) {
        var row = document.createElement('div');
        row.className = 'row';
        row.innerHTML =
          '<span class="row-ic" style="color:' + (p.cpu > 10 ? 'var(--bad)' : (p.cpu > 3 ? 'var(--warn)' : 'var(--txt-3)')) + '">' + icon('box') + '</span>' +
          '<div class="row-main">' +
            '<div class="row-name">' + p.name + ' <span class="tag">' + p.pid + '</span></div>' +
            '<div class="row-sub mono">' + p.cmd + '</div>' +
          '</div>' +
          '<div class="row-meta">' +
            '<span class="rm-cpu">' + p.cpu.toFixed(1) + '%</span>' +
            '<span class="rm-mem">' + fmtBytes(p.rss) + '</span>' +
            '<button class="btn btn-sm btn-danger" title="结束进程">结束</button>' +
          '</div>';
        row.querySelector('button').addEventListener('click', function () {
          if (!confirm('结束进程 ' + p.name + ' (PID ' + p.pid + ')？\n先发送正常退出信号，无效再强杀。')) return;
          post('/api/kill', { pid: p.pid, sig: '15' }).then(function (r) {
            if (r.ok) { toast('已发送结束信号'); loadTasks(); }
            else {
              if (confirm('正常结束失败，要强制结束 (SIGKILL) 吗？')) {
                post('/api/kill', { pid: p.pid, sig: '9' }).then(function (r2) {
                  toast(r2.ok ? '已强制结束' : (r2.err || '失败'), r2.ok ? 'ok' : 'err');
                  loadTasks();
                });
              }
            }
          });
        });
        box.appendChild(row);
      });
    });
  }
  $('#taskRefresh').addEventListener('click', loadTasks);

  /* ---------------- 系统维护 ---------------- */
  function loadMaintain() {}

  $('#smartCheck').addEventListener('click', function () {
    var dev = $('#smartDev').value;
    var el = $('#smartResult');
    el.textContent = '检查中…';
    api('/api/smart?dev=' + encodeURIComponent(dev)).then(function (r) {
      if (!r.ok) { el.textContent = r.err || '检查失败'; return; }
      el.innerHTML = r.health
        ? ('健康状态：<b style="color:' + (r.health === 'PASSED' ? 'var(--accent)' : 'var(--bad)') + '">' + r.health + '</b>')
        : '无法读取 SMART（eMMC 通常不支持），详情见下';
      showLog('磁盘健康 ' + dev, r.text);
    });
  });

  $('#btnClean').addEventListener('click', function () {
    if (!confirm('清理 apt 缓存、旧日志和临时文件？')) return;
    post('/api/maintenance', { act: 'clean' }).then(function (r) {
      if (r.job) watchJob(r.job, '系统清理');
      else toast(r.err || '失败', 'err');
    });
  });

  $('#btnUpdate').addEventListener('click', function () {
    if (!confirm('执行系统更新？会 apt update + upgrade，可能耗时较长。')) return;
    post('/api/maintenance', { act: 'update' }).then(function (r) {
      if (r.job) watchJob(r.job, '系统更新');
      else toast(r.err || '失败', 'err');
    });
  });

  $('#btnDiagnose').addEventListener('click', function () {
    toast('正在收集诊断信息…');
    post('/api/maintenance', { act: 'diagnose' }).then(function (r) {
      showLog('故障诊断', r.ok ? r.text : '诊断失败');
    });
  });

  $('#btnReboot').addEventListener('click', function () {
    if (!confirm('重启设备？所有服务会中断约 1 分钟。')) return;
    post('/api/maintenance', { act: 'reboot' }).then(function () {
      toast('设备正在重启，请稍后手动刷新');
    });
  });

  $('#btnShutdown').addEventListener('click', function () {
    if (!confirm('关机？关机后需要手动拔插电源才能再次开机。')) return;
    if (!confirm('再确认一次：现在关机？')) return;
    post('/api/maintenance', { act: 'shutdown' }).then(function () {
      toast('设备正在关机');
    });
  });

  /* ---------------- 分享链接 ---------------- */
  function loadShares() {
    api('/api/shares').then(function (r) {
      var box = $('#shareLinkList');
      if (!r.ok) return;
      box.innerHTML = '';
      if (!r.items.length) box.innerHTML = '<div class="empty">还没有分享链接</div>';
      r.items.forEach(function (it) {
        var url = location.origin + '/s/' + it.token;
        var row = document.createElement('div');
        row.className = 'row';
        row.innerHTML =
          '<span class="row-ic">' + icon('share') + '</span>' +
          '<div class="row-main">' +
            '<div class="row-name mono">/s/' + it.token + '</div>' +
            '<div class="row-sub">' + it.path + ' · ' + it.downloads + ' 次下载 · ' + fmtTime(it.created) + '</div>' +
          '</div>' +
          '<div class="row-act">' +
            '<button data-a="copy" title="复制链接">' + icon('download') + '</button>' +
            '<button data-a="open" title="打开">' + icon('external') + '</button>' +
            '<button data-a="del" class="danger" title="删除">' + icon('trash') + '</button>' +
          '</div>';
        row.querySelectorAll('[data-a]').forEach(function (b) {
          b.addEventListener('click', function () {
            var a = b.dataset.a;
            if (a === 'copy') {
              navigator.clipboard.writeText(url).then(function () { toast('链接已复制'); }, function () {
                prompt('复制这个链接：', url);
              });
            } else if (a === 'open') { window.open(url, '_blank'); }
            else {
              if (!confirm('删除这条分享链接？')) return;
              post('/api/shares', { act: 'delete', token: it.token }).then(loadShares);
            }
          });
        });
        box.appendChild(row);
      });
    });
  }

  $('#shareLinkForm').addEventListener('submit', function (e) {
    e.preventDefault();
    var fd = new FormData(this);
    post('/api/shares', { act: 'create', path: fd.get('path') }).then(function (r) {
      if (r.ok) {
        var url = location.origin + '/s/' + r.token;
        navigator.clipboard.writeText(url).then(function () { toast('链接已生成并复制'); }, function () {
          prompt('分享链接（复制它）：', url);
        });
        this.reset();
        loadShares();
      } else toast(r.err || '失败', 'err');
    }.bind(this));
  });

  /* ---------------- 我的设备 ---------------- */
  function loadDevice() {
    api('/api/sysinfo').then(function (r) {
      if (!r.ok) { $('#devGrid').innerHTML = '<div class="empty">读取失败</div>'; return; }
      var i = r.info;
      $('#devSub').textContent = i.hostname + ' · ' + i.os + ' · ' + i.arch;
      var rows = [
        ['系统', i.os, ''],
        ['内核', i.kernel, ''],
        ['架构', i.arch, ''],
        ['处理器', i.cpu_model + '（' + i.cpu_cores + ' 核）', ''],
        ['内存', i.mem_used_h + ' / ' + i.mem_total_h, ''],
        ['Swap', i.swap_total_h, ''],
        ['负载', i.load.join(' / '), ''],
        ['温度', i.temp ? (i.temp + '°C') : '—', ''],
        ['已运行', fmtUptime(i.uptime), ''],
        ['IP 地址', i.ip || '—', ''],
        ['磁盘', (i.disks || []).join('、') || '—', ''],
        ['版本', 'Covernas ' + i.box_ver, ''],
        ['开发者', 'XCR', ''],
        ['版权', '© 2026 XCR · 保留所有权利', '']
      ];
      var grid = $('#devGrid');
      grid.innerHTML = '';
      var hw = rows.slice(0, 5), sw = rows.slice(5);
      function renderGroup(title, items) {
        var h = document.createElement('h3');
        h.textContent = title;
        grid.appendChild(h);
        items.forEach(function (x) {
          var row = document.createElement('div');
          row.className = 'dev-row';
          row.innerHTML = '<span class="dev-k">' + x[0] + '</span>' +
                          '<span class="dev-v">' + x[1] + '</span>';
          grid.appendChild(row);
        });
      }
      renderGroup('硬件', hw);
      renderGroup('运行状态', sw.slice(0, 6));
      renderGroup('版权信息', sw.slice(6));
    });
  }

  /* ---------------- 应用商店 ---------------- */
  var storeTab = '全部';

  function loadStore() {
    api('/api/store').then(function (r) {
      if (!r.ok) return;
      state.store = r.items;
      var cats = ['全部'];
      r.items.forEach(function (it) { if (cats.indexOf(it.cat) < 0) cats.push(it.cat); });
      var tabs = $('#storeTabs');
      tabs.innerHTML = '';
      cats.forEach(function (c) {
        var b = document.createElement('button');
        b.className = 'tab' + (c === storeTab ? ' on' : '');
        b.textContent = c;
        b.addEventListener('click', function () { storeTab = c; loadStore(); });
        tabs.appendChild(b);
      });

      var list = r.items.filter(function (it) { return storeTab === '全部' || it.cat === storeTab; });
      var inst = r.items.filter(function (it) { return it.installed; }).length;
      $('#storeCount').textContent = '已装 ' + inst + ' / ' + r.items.length;

      var g = $('#storeGrid');
      g.innerHTML = '';
      list.forEach(function (it) {
        var card = document.createElement('div');
        card.className = 'app-card' + (it.installed ? ' on' : '');
        var canInstall = it.pkg || it.kind === 'docker';
        card.innerHTML =
          '<div class="app-head">' +
            '<span class="app-ic" style="background:' + tileGradient(it.color || '#0f7b5f') + '">' +
              iconSafe(it.icon, it.name, it.color) + '</span>' +
            '<b>' + it.name + '</b>' +
            (it.installed ? '<span class="tag on">已装</span>' : '<span class="tag">未装</span>') + '</div>' +
          '<div class="app-desc">' + it.desc + '</div>' +
          '<div class="app-foot"><span class="muted small">' + it.size + '</span>' +
            (canInstall
              ? '<button class="btn btn-sm ' + (it.installed ? 'btn-ghost' : 'btn-primary') + '">' +
                (it.installed ? '卸载' : '安装') + '</button>'
              : '<span class="muted small">内置</span>') +
          '</div>';
        var btn = card.querySelector('button');
        if (btn) {
          btn.addEventListener('click', function () {
            var act = it.installed ? 'uninstall' : 'install';
            if (act === 'uninstall' && !confirm('卸载「' + it.name + '」？相关服务会停止。' +
            (it.kind === 'docker' ? '\n容器数据卷（/mnt 下的目录）会保留，不会自动删除。' : ''))) return;
            btn.disabled = true;
            btn.textContent = act === 'install' ? '安装中…' : '卸载中…';
            post('/api/store/install', { id: it.id, act: act }).then(function (res) {
              if (!res.ok) { toast(res.err || '失败', 'err'); btn.disabled = false; loadStore(); return; }
              watchJob(res.job, it.name);
            });
          });
        }
        g.appendChild(card);
      });
    });
  }

  /* 轮询后台任务，结束后提示 */
  function watchJob(jid, title) {
    toast(title + '：任务已开始');
    var t = setInterval(function () {
      api('/api/job?id=' + encodeURIComponent(jid)).then(function (r) {
        if (!r.ok) { clearInterval(t); return; }
        if (r.running) return;
        clearInterval(t);
        var ok = r.rc === 0;
        toast(title + (ok ? ' 完成' : ' 失败'), ok ? 'ok' : 'err');
        showLog(title + (ok ? ' 完成' : ' 失败'), r.text);
        if (state.view === 'store') loadStore();
        if (state.view === 'services') loadServices();
      }).catch(function () { clearInterval(t); });
    }, 1500);
  }

  $('#storeRefresh').addEventListener('click', loadStore);

  /* ---------------- 网络共享 ---------------- */
  function loadShare() {
    loadSamba();
    loadNfs();
    loadFtp();
    loadWebdav();
  }

  function loadSamba() {
    api('/api/samba').then(function (r) {
      var box = $('#shareList');
      if (!r.installed) {
        box.innerHTML = '<div class="empty">Samba 还没安装，先去「应用商店」装一下</div>';
        return;
      }
      box.innerHTML = '';
      if (!r.shares.length) box.innerHTML = '<div class="empty">还没有共享目录</div>';
      r.shares.forEach(function (s) {
        var row = document.createElement('div');
        row.className = 'row';
        row.innerHTML =
          '<span class="row-ic dir">' + icon('folder') + '</span>' +
          '<div class="row-main">' +
            '<div class="row-name">' + s.name + ' <span class="tag ' + (s.writable ? 'on' : '') + '">' +
              (s.writable ? '可写' : '只读') + '</span></div>' +
            '<div class="row-sub">' + s.path + (s.guest ? ' · 允许访客' : ' · 需账号') + '</div>' +
          '</div>' +
          '<div class="row-act">' +
            '<button data-act="toggle" title="切换读写">' + icon('edit') + '</button>' +
            '<button data-act="del" class="danger" title="删除">' + icon('trash') + '</button>' +
          '</div>';
        row.querySelectorAll('[data-act]').forEach(function (b) {
          b.addEventListener('click', function () {
            var act = b.dataset.act;
            if (act === 'del' && !confirm('删除共享「' + s.name + '」？目录本身不会删。')) return;
            post('/api/samba', { act: act === 'del' ? 'delete' : 'toggle', name: s.name }).then(function (res) {
              if (res.ok) { toast('已更新'); loadSamba(); }
              else toast(res.err || '失败', 'err');
            });
          });
        });
        box.appendChild(row);
      });

      var ul = $('#smbUserList');
      ul.innerHTML = '';
      if (!(r.users || []).length) ul.innerHTML = '<div class="empty small">还没有 SMB 用户（访客共享不需要账号）</div>';
      (r.users || []).forEach(function (u) {
        var row = document.createElement('div');
        row.className = 'row';
        row.innerHTML =
          '<span class="row-ic">' + icon('file') + '</span>' +
          '<div class="row-main"><div class="row-name mono">' + u + '</div>' +
          '<div class="row-sub">SMB 账号</div></div>' +
          '<div class="row-act"><button class="danger" title="删除">' + icon('trash') + '</button></div>';
        row.querySelector('button').addEventListener('click', function () {
          if (!confirm('删除 SMB 用户「' + u + '」？')) return;
          post('/api/smb/user', { act: 'del', user: u }).then(function (res) {
            if (res.ok) { toast('已删除'); loadSamba(); }
            else toast(res.err || '失败', 'err');
          });
        });
        ul.appendChild(row);
      });

      $('#shareHint').innerHTML = 'Mac 访达按 ⌘K 输入 <code>smb://' + location.hostname +
        '</code> 即可连接。' + (r.state === 'active' ? '' : ' 注意：服务当前没在运行。');
    });
  }

  function loadNfs() {
    api('/api/nfs').then(function (r) {
      var box = $('#nfsList');
      if (!r.installed) {
        box.innerHTML = '<div class="empty">NFS 未安装 — 下方填好目录点添加会自动安装</div>';
        return;
      }
      box.innerHTML = '';
      if (!(r.exports || []).length) box.innerHTML = '<div class="empty">还没有导出目录</div>';
      (r.exports || []).forEach(function (e) {
        var row = document.createElement('div');
        row.className = 'row';
        row.innerHTML =
          '<span class="row-ic dir">' + icon('folder') + '</span>' +
          '<div class="row-main"><div class="row-name mono">' + e.path + '</div>' +
          '<div class="row-sub">客户端 ' + e.clients + '</div></div>' +
          '<div class="row-act"><button class="danger" title="删除">' + icon('trash') + '</button></div>';
        row.querySelector('button').addEventListener('click', function () {
          if (!confirm('删除导出「' + e.path + '」？')) return;
          post('/api/nfs', { act: 'delete', path: e.path }).then(function (res) {
            if (res.ok) { toast('已删除'); loadNfs(); }
            else toast(res.err || '失败', 'err');
          });
        });
        box.appendChild(row);
      });
    });
  }

  function loadFtp() {
    api('/api/ftp').then(function (r) {
      var st = $('#ftpState');
      if (!r.installed) {
        st.innerHTML = '未安装 — 填好下方目录点「保存并启动」会自动安装 vsftpd';
        return;
      }
      st.innerHTML = r.state === 'active' ? '运行中 · 端口 21 · 目录 ' + r.root : '已安装但已停止';
      if (r.root) $('#ftpForm').root.value = r.root;
      if (r.user) $('#ftpForm').user.value = r.user;
    });
  }

  function loadWebdav() {
    api('/api/webdav').then(function (r) {
      var st = $('#webdavState');
      if (!r.installed) {
        st.innerHTML = '未安装 — rclone 缺失（这台设备已带 rclone，如异常请到应用商店重装）';
        return;
      }
      st.innerHTML = r.state === 'active'
        ? ('运行中 · http://' + location.hostname + ':' + r.port + ' · 目录 ' + r.path)
        : '已配置但未启动';
      if (r.path) $('#webdavForm').path.value = r.path;
      if (r.user) $('#webdavForm').user.value = r.user;
      if (r.port) $('#webdavForm').port.value = r.port;
    });
  }

  $('#shareTabs').addEventListener('click', function (e) {
    var b = e.target.closest('.tab');
    if (!b) return;
    $$('#shareTabs .tab').forEach(function (x) { x.classList.toggle('on', x === b); });
    $$('.share-tab').forEach(function (t) { t.hidden = t.id !== 'st-' + b.dataset.t; });
  });

  $('#smbUserForm').addEventListener('submit', function (e) {
    e.preventDefault();
    var fd = new FormData(this);
    post('/api/smb/user', { act: 'add', user: fd.get('user'), password: fd.get('password') }).then(function (r) {
      if (r.ok) { toast('用户已添加'); this.reset(); loadSamba(); }
      else toast(r.err || '失败', 'err');
    }.bind(this));
  });

  $('#nfsForm').addEventListener('submit', function (e) {
    e.preventDefault();
    var fd = new FormData(this);
    post('/api/nfs', { act: 'add', path: fd.get('path'), clients: fd.get('clients'), ro: fd.get('ro') ? '1' : '0' }).then(function (r) {
      if (r.ok) { toast('导出已添加'); this.reset(); loadNfs(); }
      else if (r.job) { watchJob(r.job, '安装 NFS'); }
      else toast(r.err || '失败', 'err');
    }.bind(this));
  });

  $('#ftpForm').addEventListener('submit', function (e) {
    e.preventDefault();
    var fd = new FormData(this);
    post('/api/ftp', { act: 'save', root: fd.get('root'), user: fd.get('user'), password: fd.get('password') }).then(function (r) {
      if (r.ok) { toast('FTP 已启动'); loadFtp(); }
      else if (r.job) { watchJob(r.job, '安装 FTP'); }
      else toast(r.err || '失败', 'err');
    });
  });

  $('#webdavForm').addEventListener('submit', function (e) {
    e.preventDefault();
    var fd = new FormData(this);
    post('/api/webdav', { act: 'save', path: fd.get('path'), user: fd.get('user'), password: fd.get('password'), port: fd.get('port') }).then(function (r) {
      if (r.ok) { toast('WebDAV 已启动'); loadWebdav(); }
      else toast(r.err || '失败', 'err');
    });
  });

  $('#shareForm').addEventListener('submit', function (e) {
    e.preventDefault();
    var fd = new FormData(this);
    post('/api/samba', {
      act: 'add', name: fd.get('name'), path: fd.get('path'), comment: fd.get('comment'),
      writable: fd.get('writable') ? '1' : '0', guest: fd.get('guest') ? '1' : '0'
    }).then(function (r) {
      if (r.ok) { toast('共享已创建'); this.reset(); loadShare(); }
      else toast(r.err || '失败', 'err');
    }.bind(this));
  });

  /* ---------------- 磁盘备份 ---------------- */
  function loadBackup() {
    api('/api/backup').then(function (r) {
      var box = $('#backupList');
      box.innerHTML = '';
      $('#backupCount').textContent = r.tasks.length ? r.tasks.length + ' 个任务' : '';
      if (!r.tasks.length) box.innerHTML = '<div class="empty">还没有备份任务</div>';
      r.tasks.forEach(function (t) {
        var last = (r.last || {})[t.id];
        var row = document.createElement('div');
        row.className = 'row';
        row.innerHTML =
          '<span class="row-ic">' + icon('backup') + '</span>' +
          '<div class="row-main">' +
            '<div class="row-name">' + t.name +
              (t.mirror ? ' <span class="tag">镜像</span>' : ' <span class="tag">增量</span>') + '</div>' +
            '<div class="row-sub">' + t.src + ' → ' + t.dst +
              (last ? ' · 上次运行 ' + fmtTime(last.ts) : '') + '</div>' +
          '</div>' +
          '<div class="row-act">' +
            '<button data-act="run" title="立即备份">' + icon('play') + '</button>' +
            '<button data-act="del" class="danger" title="删除任务">' + icon('trash') + '</button>' +
          '</div>';
        row.querySelectorAll('[data-act]').forEach(function (b) {
          b.addEventListener('click', function () {
            if (b.dataset.act === 'run') {
              b.disabled = true;
              post('/api/backup', { act: 'run', id: t.id }).then(function (res) {
                if (res.ok) watchJob(res.job, '备份 ' + t.name);
                else { toast(res.err || '失败', 'err'); b.disabled = false; }
              });
            } else {
              if (!confirm('删除任务「' + t.name + '」？已备份的文件不会删。')) return;
              post('/api/backup', { act: 'delete', id: t.id }).then(loadBackup);
            }
          });
        });
        box.appendChild(row);
      });
    });
  }

  $('#backupForm').addEventListener('submit', function (e) {
    e.preventDefault();
    var fd = new FormData(this);
    post('/api/backup', {
      act: 'save', name: fd.get('name'), src: fd.get('src'), dst: fd.get('dst'),
      mirror: fd.get('mirror') ? '1' : '0'
    }).then(function (r) {
      if (r.ok) { toast('任务已保存'); this.reset(); loadBackup(); }
      else toast(r.err || '失败', 'err');
    }.bind(this));
  });

  /* ---------------- 部署网站 ---------------- */
  function loadSite() {
    api('/api/site').then(function (r) {
      var box = $('#siteList');
      box.innerHTML = '';
      $('#siteState').textContent = r.nginx === 'active' ? 'Nginx 运行中' : 'Nginx 未运行';
      if (!r.sites.length) box.innerHTML = '<div class="empty">还没有站点</div>';
      r.sites.forEach(function (s) {
        var row = document.createElement('div');
        row.className = 'row';
        var url = 'http://' + location.hostname + (s.port ? ':' + s.port : '') + '/';
        row.innerHTML =
          '<span class="row-ic dir">' + icon('web') + '</span>' +
          '<div class="row-main">' +
            '<div class="row-name">' + s.name +
              (s.enabled ? '' : ' <span class="tag">未启用</span>') + '</div>' +
            '<div class="row-sub">' + s.dir + ' · 端口 ' + (s.port || '—') + ' · ' + s.files + ' 个文件</div>' +
          '</div>' +
          '<div class="row-act">' +
            '<button data-act="open" title="打开">' + icon('external') + '</button>' +
            '<button data-act="del" class="danger" title="删除">' + icon('trash') + '</button>' +
          '</div>';
        row.querySelectorAll('[data-act]').forEach(function (b) {
          b.addEventListener('click', function () {
            if (b.dataset.act === 'open') { window.open(url, '_blank'); return; }
            if (!confirm('删除站点「' + s.name + '」？网页文件默认保留。')) return;
            post('/api/site', { act: 'delete', name: s.name, keep_files: '1' }).then(function (res) {
              if (res.ok) { toast('已删除'); loadSite(); } else toast(res.err || '失败', 'err');
            });
          });
        });
        box.appendChild(row);
      });
    });
  }

  $('#siteForm').addEventListener('submit', function (e) {
    e.preventDefault();
    var fd = new FormData(this);
    post('/api/site', { act: 'create', name: fd.get('name'), port: fd.get('port') }).then(function (r) {
      if (r.ok) {
        toast('站点已创建，端口 ' + r.port);
        this.reset();
        loadSite();
      } else toast(r.err || '失败', 'err');
    }.bind(this));
  });

  /* ---------------- 远程访问 ---------------- */
  function loadRemote() {
    api('/api/remote').then(function (r) {
      var box = $('#remoteList');
      box.innerHTML = '';
      var STATE = { active: '运行中', inactive: '已停止', failed: '异常', 'not-installed': '未安装' };
      r.items.forEach(function (it) {
        var card = document.createElement('div');
        card.className = 'rcard';
        card.innerHTML =
          '<div class="rcard-head"><b>' + it.name + '</b>' +
            '<span class="tag ' + (it.state === 'active' ? 'on' : '') + '">' +
            (STATE[it.state] || it.state) + '</span></div>' +
          '<div class="rcard-detail">' + (it.detail || '—') + '</div>' +
          '<div class="rcard-act"></div>';
        var act = card.querySelector('.rcard-act');
        if (!it.installed) {
          if (it.id === 'tailscale') {
            var b = document.createElement('button');
            b.className = 'btn btn-sm btn-primary';
            b.textContent = '安装';
            b.addEventListener('click', function () {
              b.disabled = true;
              post('/api/remote', { act: 'install-ts' }).then(function (res) {
                if (res.ok) watchJob(res.job, '安装 Tailscale');
                else { toast(res.err || '失败', 'err'); b.disabled = false; }
              });
            });
            act.appendChild(b);
          } else {
            act.innerHTML = '<span class="muted small">需要手动安装</span>';
          }
        } else {
          var on = it.state === 'active';
          var t = document.createElement('button');
          t.className = 'btn btn-sm ' + (on ? 'btn-ghost' : 'btn-primary');
          t.textContent = on ? '停止' : '启动';
          t.addEventListener('click', function () {
            t.disabled = true;
            post('/api/remote', { act: on ? 'stop' : 'start', unit: it.unit }).then(function () {
              loadRemote();
            });
          });
          act.appendChild(t);
          if (it.id === 'tailscale' && on) {
            var up = document.createElement('button');
            up.className = 'btn btn-sm';
            up.textContent = '登录网络';
            up.addEventListener('click', function () {
              var key = prompt('Tailscale 授权密钥（可留空，会给出登录链接）', '');
              if (key === null) return;
              post('/api/remote', { act: 'up-ts', authkey: key }).then(function (res) {
                if (res.ok) watchJob(res.job, 'Tailscale 登录');
              });
            });
            act.appendChild(up);
          }
        }
        box.appendChild(card);
      });
      var d = r.ddns || {};
      if (d.domain) $('#ddnsForm').domain.value = d.domain;
      if (d.token) $('#ddnsForm').token.value = d.token;
      $('#ddnsForm').enabled.checked = !!d.enabled;
      $('#remoteIp').textContent = '本机 ' + location.hostname;
    });
  }

  $('#ddnsForm').addEventListener('submit', function (e) {
    e.preventDefault();
    var fd = new FormData(this);
    post('/api/remote', {
      act: 'ddns', domain: fd.get('domain'), token: fd.get('token'),
      enabled: fd.get('enabled') ? '1' : '0'
    }).then(function (r) {
      if (r.ok) toast(r.ddns.enabled ? 'DDNS 已启用' : '已保存');
      else toast(r.err || '失败', 'err');
    });
  });

  /* ---------------- 设置 ---------------- */
  function fillAbout() {
    var s = state.last;
    if (!s) return;
    $('#abiSys').textContent = 'Ubuntu · armv7';
    $('#abiKernel').textContent = s.host.kernel;
    $('#abiUp').textContent = fmtUptime(s.host.uptime);
  }

  $('#pwForm').addEventListener('submit', function (e) {
    e.preventDefault();
    var fd = new FormData(this);
    post('/api/passwd', { old: fd.get('old'), new: fd.get('new') }).then(function (r) {
      if (r.ok) { toast('密码已更新'); $('#pwForm').reset(); }
      else toast(r.err || '失败', 'err');
    });
  });

  $('#logoutBtn').addEventListener('click', function () {
    post('/api/logout').then(function () { location.href = '/'; });
  });

  /* ---------------- 外观（主题色 / 壁纸） ---------------- */
  // 壁纸库由后端 /api/ui 下发（walls 字段），这里只做挑选与应用

  function setWallCss(wall, size) {
    document.body.style.setProperty('--wall', wall);
    document.body.style.setProperty('--wall-size', size || 'cover');
  }

  function pickWallCss(ui) {
    // 返回 {wall, size} 或 null（默认无壁纸）
    if (ui.wall_url && ui.wall === 'custom') {
      return { wall: 'url("' + ui.wall_url + '")', size: 'cover' };
    }
    var walls = ui.walls || [];
    if (!walls.length) return null;
    if (ui.wall === 'random') {
      var w = walls[Math.floor(Math.random() * walls.length)];
      return { wall: w.css, size: w.size || 'cover' };
    }
    if ((ui.wall || '').indexOf('preset:') === 0) {
      for (var i = 0; i < walls.length; i++) {
        if (walls[i].id === ui.wall.slice(7)) return { wall: walls[i].css, size: walls[i].size || 'cover' };
      }
    }
    return null;
  }

  function hexRgb(hex) {
    return [parseInt(hex.slice(1, 3), 16), parseInt(hex.slice(3, 5), 16), parseInt(hex.slice(5, 7), 16)];
  }

  function applyAccent(accent) {
    var hex = (accent || '#0f7b5f').toLowerCase();
    var c = hexRgb(hex);
    var root = document.documentElement.style;
    root.setProperty('--accent', hex);
    root.setProperty('--accent-rgb', c.join(' '));
    root.setProperty('--accent-hi', 'rgb(' + Math.min(255, c[0] + 34) + ',' +
      Math.min(255, c[1] + 34) + ',' + Math.min(255, c[2] + 34) + ')');
    var picker = $('#accentPicker');
    if (picker) picker.value = hex;
    $$('#accentRow .accent-dot[data-accent]').forEach(function (b) {
      b.classList.toggle('on', b.dataset.accent === hex);
    });
  }

  function buildWallGrid(ui) {
    var grid = $('#wallGrid');
    if (!grid) return;
    var cur = ui.wall || 'default';
    var cells = ['<button type="button" class="wall-cell' + (cur === 'default' ? ' on' : '') +
      '" data-wall="default" title="默认（纯色界面）"><span class="wall-none">无</span></button>',
      '<button type="button" class="wall-cell' + (cur === 'random' ? ' on' : '') +
      '" data-wall="random" title="随机（每次刷新换一张）"><span class="wall-rand">?</span></button>'];
    (ui.walls || []).forEach(function (w) {
      var sz = w.size ? ';background-size:' + w.size : '';
      cells.push('<button type="button" class="wall-cell' + (cur === 'preset:' + w.id ? ' on' : '') +
        '" data-wall="preset:' + w.id + '" title="' + w.name + '"' +
        ' style="background:' + w.css + sz + '"></button>');
    });
    if (ui.wall_url && ui.wall === 'custom') {
      cells.push('<button type="button" class="wall-cell on" data-wall="custom" title="自定义上传"' +
        ' style="background:url(\'' + ui.wall_url + '\') center/cover"></button>');
    }
    grid.innerHTML = cells.join('');
  }

  function applyUI(ui) {
    ui = ui || {};
    state.ui = ui;
    var theme = ui.theme || 'light';
    var dark = theme === 'dark' ||
      (theme === 'auto' && window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');

    applyAccent(ui.accent);

    var picked = pickWallCss(ui);
    if (picked) {
      setWallCss(picked.wall, picked.size);
      document.body.classList.add('has-wall');
    } else {
      document.body.classList.remove('has-wall');
    }
    var pv = $('#wallPreview');
    if (pv) {
      if (picked) {
        pv.style.backgroundImage = picked.wall;
        pv.style.backgroundSize = picked.size || 'cover';
        var sp = pv.querySelector('span');
        if (sp) sp.style.display = 'none';
      } else {
        pv.style.backgroundImage = '';
        var sp2 = pv.querySelector('span');
        if (sp2) sp2.style.display = '';
      }
    }
    $$('#themeSeg button').forEach(function (b) {
      b.classList.toggle('on', b.dataset.theme === theme);
    });
    buildWallGrid(ui);
    applyHomeOrder(ui);
    syncOrderUI(ui);
  }

  function loadUI() {
    api('/api/ui').then(function (r) { if (r.ok) applyUI(r.ui); }).catch(function () {});
  }

  function loadSettings() {
    api('/api/ui').then(function (r) { if (r.ok) applyUI(r.ui); });
    api('/api/trash').then(function (r) {
      if (!r.ok) return;
      $('#trashInfo').textContent = r.count ? (r.count + ' 个文件 · ' + r.size_h) : '空的';
      if (r.path) $('#trashPath').textContent = r.path;
    });
    // 手机访问：地址 + 二维码
    var url = location.origin;
    var mu = $('#mobileUrl');
    if (mu) mu.textContent = url;
    var ms = $('#mobileSmb');
    if (ms) ms.textContent = '\\\\' + location.hostname + '（SMB）';
    var qb = $('#qrBox');
    if (qb) {
      qb.innerHTML = '';
      if (typeof QRCode !== 'undefined') {
        new QRCode(qb, {
          text: url, width: 132, height: 132,
          colorDark: '#16221c', colorLight: '#ffffff',
          correctLevel: QRCode.CorrectLevel.M
        });
      } else {
        qb.innerHTML = '<span class="muted small">二维码组件未加载</span>';
      }
    }
  }

  $('#themeSeg').addEventListener('click', function (e) {
    var b = e.target.closest('button');
    if (!b) return;
    post('/api/ui', { theme: b.dataset.theme }).then(function (r) {
      if (r.ok) { applyUI(r.ui); toast('已切换为' + b.textContent); }
    });
  });

  /* 主题色 */
  $('#accentRow').addEventListener('click', function (e) {
    var b = e.target.closest('.accent-dot[data-accent]');
    if (!b) return;
    post('/api/ui', { accent: b.dataset.accent }).then(function (r) {
      if (r.ok) { applyUI(r.ui); toast('主题色已更新'); }
    });
  });
  var accentPicker = $('#accentPicker');
  if (accentPicker) {
    accentPicker.addEventListener('input', function () {
      applyAccent(this.value); // 先本地预览
    });
    accentPicker.addEventListener('change', function () {
      post('/api/ui', { accent: this.value }).then(function (r) {
        if (r.ok) { applyUI(r.ui); toast('主题色已更新'); }
      });
    });
  }

  /* 壁纸挑选 */
  $('#wallGrid').addEventListener('click', function (e) {
    var b = e.target.closest('.wall-cell');
    if (!b) return;
    var w = b.dataset.wall;
    if (w === 'custom') { $('#wallFile').click(); return; }
    post('/api/ui', { wall: w }).then(function (r) {
      if (r.ok) {
        applyUI(r.ui);
        toast(w === 'default' ? '已恢复默认' : (w === 'random' ? '已开启随机壁纸（每次刷新换一张）' : '壁纸已应用'));
      }
    });
  });

  $('#wallShuffleBtn').addEventListener('click', function () {
    if (state.ui && state.ui.wall === 'random' && (state.ui.walls || []).length) {
      var walls = state.ui.walls;
      var w = walls[Math.floor(Math.random() * walls.length)];
      setWallCss(w.css, w.size || 'cover');
      var pv = $('#wallPreview');
      if (pv) { pv.style.backgroundImage = w.css; pv.style.backgroundSize = w.size || 'cover'; }
      toast('换了一张「' + w.name + '」');
    } else {
      toast('先在壁纸里选「随机」才能换', 'err');
    }
  });

  $('#wallUploadBtn').addEventListener('click', function () { $('#wallFile').click(); });

  $('#wallFile').addEventListener('change', function () {
    var f = this.files && this.files[0];
    if (!f) return;
    var fd = new FormData();
    fd.append('file', f);
    toast('上传中…');
    fetch('/api/wallpaper', { method: 'POST', body: fd, credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (r) {
        if (r.ok) { toast('壁纸已更新'); loadSettings(); }
        else toast(r.err || '上传失败', 'err');
      })
      .catch(function () { toast('上传失败', 'err'); });
    this.value = '';
  });

  $('#wallResetBtn').addEventListener('click', function () {
    post('/api/ui', { reset_wall: '1' }).then(function (r) {
      if (r.ok) { applyUI(r.ui); toast('已恢复默认壁纸'); }
    });
  });

  $('#trashEmptyBtn').addEventListener('click', function () {
    if (!confirm('清空回收站？里面的文件会被永久删除。')) return;
    post('/api/trash/empty').then(function (r) {
      toast(r.ok ? ('已删除 ' + r.removed + ' 项') : '操作失败', r.ok ? 'ok' : 'err');
      loadSettings();
    });
  });

  $('#panelLogBtn').addEventListener('click', function () {
    api('/api/logs?unit=box').then(function (r) {
      showLog('面板日志', r.ok ? r.text : '读不到日志');
    });
  });

  $('#panelRestartBtn').addEventListener('click', function () {
    if (!confirm('重启面板？约 3 秒后恢复，服务不受影响。')) return;
    post('/api/restart', { target: 'panel' }).then(function () {
      toast('正在重启面板…');
      setTimeout(function () { location.reload(); }, 4000);
    });
  });

  $('#deviceRebootBtn').addEventListener('click', function () {
    if (!confirm('重启整台设备？所有服务会中断约 1 分钟。')) return;
    if (!confirm('再确认一次：现在就重启设备？')) return;
    post('/api/restart', { target: 'device' }).then(function () {
      toast('设备正在重启，请稍后手动刷新');
    });
  });

  /* ---------------- 启动 ---------------- */
  // 可通过 ?fv=list|icons|cols|gallery 与 ?pv=gallery|icons|list 深链指定排列方式
  var qsFv = (location.search.match(/[?&]fv=(\w+)/) || [])[1];
  if (qsFv && ['list', 'icons', 'cols', 'gallery'].indexOf(qsFv) > -1) {
    state.fileView = qsFv;
    localStorage.setItem('covernas.fileview', qsFv);
  }
  var qsPv = (location.search.match(/[?&]pv=(\w+)/) || [])[1];
  if (qsPv && ['gallery', 'icons', 'list'].indexOf(qsPv) > -1) {
    state.photoView = qsPv;
    localStorage.setItem('covernas.photoview', qsPv);
  }
  var hash = (location.hash || '#desktop').slice(1);
  var base = hash.split(':')[0];
  if (base === 'photos') {
    go('photos', true);
  } else if (hash.indexOf('files') === 0) {
    state.trash = hash.indexOf('trash=1') > -1;
    state.path = state.trash ? '/mnt/.trash' : '/mnt';
    go('files', true);
  } else if (hash === 'search') {
    go('desktop', true);
    openCmdk();
  } else if (TITLES[hash]) {
    go(hash, true);
  } else {
    go('desktop', true);
  }

  loadUI();
  loadMe();
  poll();
  loadApps();
  loadRecent();
  tickClock();
  setInterval(poll, 3000);
  setInterval(tickClock, 15000);
})();
