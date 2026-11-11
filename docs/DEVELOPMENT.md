# Covernas 开发文档

## 1. 设计目标

- **零依赖后端**：只用 Python 3.8 标准库，无 pip 安装、无 Web 框架，单文件 `server.py`。
- **零构建前端**：原生 JS + CSS，静态文件直接服务，改完刷新即生效。
- **低资源**：目标设备 Amlogic S805 / 4×Cortex-A5 / 1GB DDR3 / 8GB eMMC，内存占用与进程数都要克制（避免为每个请求启动多个子进程）。
- **可运维**：配置全为 JSON 文件、有审计日志、有一键配置备份恢复、有只读账号。

## 2. 目录与运行

```
/opt/box/            代码（web/ 为静态资源）
/etc/box/            配置与数据（JSON）
/mnt/                 数据盘（写操作白名单根目录）
```

`box.service`：`python3 /opt/box/server.py`，监听 `0.0.0.0:9000`，`Restart=always`。

关键常量在 `server.py` 顶部：

| 常量 | 说明 |
|---|---|
| `DATA_DIR` | 配置目录 `/etc/box` |
| `FILE_ROOTS` / `DENY_PREFIX` | 文件浏览允许的根 / 禁止进入的系统目录 |
| `WRITE_ROOTS` | 写操作白名单（`/mnt`），其余只读 |
| `SERVICES` | 服务启停白名单 |
| `APPS` | 桌面内置应用入口 |
| `STORE` | 应用商店清单（apt / docker 两类） |

## 3. 后端结构（server.py）

- **HTTP**：`ThreadingHTTPServer`，每个请求一个线程；`do_GET` / `do_POST` 用 if 链分发。
- **认证**：`/etc/box/users.json` 存多账号（PBKDF2-HMAC-SHA256 120k 次 + 独立 salt）；`SESSIONS` 内存字典存 `{exp, user, role}`，Cookie `box_sess` 有效期 7 天。
- **权限**：POST 通过统一入口记录审计后，若非 `admin` 且路径不在 `("/api/logout", "/api/passwd")`，直接返回 `403 {readonly:true}`。
- **审计**：`audit(event, detail, ip, user)` 追加写 `/etc/box/audit.log`（JSON Lines，2MB 轮转到 `.1`）；`GET /api/audit?limit=&event=&q=` 查询。
- **长任务**：`start_job(name, cmd)` 起后台线程跑 shell，日志写 `/tmp/box-job-<id>.log`，`GET /api/job?id=` 轮询。
- **应用商店**：`store_installed()` 判断安装状态（docker 用一次 `docker ps -a` + 20s 缓存，apt 用一次 `dpkg-query` + 60s 缓存）；`store_install_cmd()` 生成安装/卸载命令；已安装且声明 `app` 的项会合并进 `/api/apps`（桌面磁贴）。
- **配置备份**：`export_config_bytes()` 内存打包 tar.gz（白名单路径），`import_config_bytes()` 校验成员路径后写回并重载 nginx / smb / exportfs / WebDAV。

## 4. 数据文件

| 文件 | 结构 |
|---|---|
| `users.json` | `{"users":[{"name","salt","hash","role","created"}]}`，role ∈ `admin` / `viewer` |
| `ui.json` | `{"theme":"light\|dark\|auto","wall","accent","warn_temp","home_order","video_speed"}` |
| `notes.json` | `[{"id","title","body","updated"}]` |
| `albums.json` | `{"albums":[{"id","name","items":[]}]}` |
| `shares.json` | 分享链接 `[{"token","path","name","created"}]` |
| `backups.json` / `backups-last.json` | 磁盘备份任务与最近一次结果 |
| `net.json` | FTP / WebDAV 配置快照 |
| `audit.log` | 审计 JSON Lines |
| `recovery-key` | 12 位恢复码（重置密码用） |

## 5. API 一览

**认证**
`GET /api/login`（初始化/登录状态）、`GET /api/me`、`GET /api/users`、`GET /api/recovery-info`
`POST /api/setup`、`/api/login`（`username`+`password`）、`/api/logout`、`/api/passwd`、`/api/recover`、`/api/users`（`act=add|del|passwd|role`）

**文件**
`GET /api/files`、`/api/download`、`/api/raw`、`/api/preview`
`POST /api/mkdir`、`/api/delete`、`/api/rename`、`/api/upload`、`/api/files/move`、`/api/file/stat`、`/api/file/chmod`、`/api/file/compress`、`/api/file/extract`、`/api/file/new`、`/api/trash/empty`

**媒体 / 内容**
`GET /api/photos`、`/api/media`、`/api/albums`、`/api/notes`、`/api/search`
`POST /api/photos`（相册集合操作）、`/api/notes`、`/api/albums`

**系统**
`GET /api/status`、`/api/sysinfo`、`/api/services`、`/api/processes`、`/api/storage`、`/api/smart`、`/api/logs`、`/api/trash`
`POST /api/service`、`/api/service/enable`、`/api/kill`、`/api/maintenance`（clean/update/diagnose/reboot/shutdown）、`/api/restart`（panel/device）、`/api/trash/empty`

**应用 / 容器**
`GET /api/apps`、`/api/store`、`/api/docker`
`POST /api/store/install`（`id`+`act=install|uninstall`）、`/api/docker`（start/stop/restart）、`/api/docker/run`、`/api/docker/remove`

**共享 / 网络**
`GET /api/samba`、`/api/shares`、`/api/site`、`/api/remote`、`/api/backup`
`POST /api/samba`、`/api/smb/user`、`/api/nfs`、`/api/ftp`、`/api/webdav`、`/api/site`、`/api/remote`、`/api/backup`、`/api/shares`

**外观 / 配置**
`GET /api/ui`、`/api/wallpaper`、`/api/audit`、`/api/config/export`
`POST /api/ui`、`/api/wallpaper`、`/api/config/import`

## 6. 前端结构（web/）

- `index.html`：所有视图 `<section class="view" id="view-xxx">`，顶部 `TITLES` 映射页面标题；SVG sprite 定义全部图标（`#i-xxx`）。
- `app.js`：
  - `go(view)` 切视图并按需调用对应 `loadXxx()`；
  - `api()/post()` 封装请求，401 跳登录、403 提示只读；
  - `iconSafe(name,label,color)`：sprite 缺失时用首字母色块兜底；
  - 命令面板（Ctrl/⌘+K）、操作日志、账号管理、首页卡片排序、上传进度等模块。
- `app.css` + `polish.css`：单一强调色 `--accent`（默认 `#0f7b5f`），`[data-theme="dark"]` 覆盖变量；`body.has-wall` 时容器转半透明毛玻璃。

## 7. 本地调试

面板强依赖设备环境（systemd、`/mnt`、`/etc/box`）。在开发机上调试时，复制一份 `server.py` 并替换三个常量即可跑独立实例：

```bash
sed -e 's|DATA_DIR = "/etc/box"|DATA_DIR = "/tmp/box-dev"|' \
    -e 's|LISTEN = ("0.0.0.0", 9000)|LISTEN = ("127.0.0.1", 9103)|' \
    -e 's|TRASH_DIR = "/mnt/.trash"|TRASH_DIR = "/tmp/box-dev/trash"|' \
    -e 's|WEB_DIR = .*|WEB_DIR = "/path/to/covernas/web"|' \
    server.py > /tmp/box-dev-server.py
python3 /tmp/box-dev-server.py
```

截图可以用 headless Chrome（注意 ARM 设备上别开太多并发）：

```bash
chrome --headless=new --no-sandbox --disable-gpu --virtual-time-budget=4000 \
       --window-size=1440,900 --screenshot=/tmp/shot.png "http://127.0.0.1:9103/#desktop"
```

## 8. 低配设备注意事项

- **少开子进程**：ARMv7 上每次 `subprocess` 有几十到几百 ms 开销，列表类接口必须批量查询 + 缓存（`/api/store` 的 dpkg/docker 缓存就是为此加的）。
- **避免全盘扫描**：搜索只在 `/mnt` 下做（深度 4，跳过隐藏/缓存目录）。
- **`/tmp` 可能是 tmpfs**：打包/解压/上传临时文件注意空间，及时清理 `/tmp/box-job-*.log`。
- **Docker**：设备访问 Docker Hub 可能超时，可在 `/etc/docker/daemon.json` 配置 `registry-mirrors`；armv7 镜像可用性需逐个确认。
- **内存**：Jellyfin / code-server 等镜像较大，1GB 内存设备不建议同时跑多个。

## 9. 已知限制

- 前端无构建链，代码量增大后维护成本上升。
- 面板本身不处理 TLS，公网使用需自行反代。
- 应用商店的 Docker 应用只做基础运行参数（端口/卷/环境变量），复杂编排建议直接用 Docker Compose。
- 站点部署基于 nginx 单站点模板，未做多域名/证书自动化。
