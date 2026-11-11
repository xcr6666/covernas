#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Box — 自建家庭服务器面板后端
纯标准库，无第三方依赖，适配 Ubuntu 20.04 / Python 3.8 / armv7 / 1GB 内存
"""

import base64
import cgi
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import tarfile
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

APP_NAME = "Covernas"
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
DATA_DIR = "/etc/box"
AUTH_FILE = os.path.join(DATA_DIR, "auth.json")
TRASH_DIR = "/mnt/.trash"
LISTEN = ("0.0.0.0", 9000)

# 文件管理允许访问的根目录（防止误入系统目录）
FILE_ROOTS = ["/", ]
DENY_PREFIX = ("/proc", "/sys", "/dev", "/boot", "/run", "/var/lib/docker")
# 写操作（新建/上传/重命名/删除/移动）只允许在数据盘进行，系统目录只读保护
WRITE_ROOTS = ["/mnt"]

# 服务白名单：key 传给 systemctl，其余是展示用
SERVICES = {
    "docker":              {"name": "Docker",        "desc": "容器运行时"},
    "transmission-daemon": {"name": "Transmission",  "desc": "BT / PT 下载"},
    "ttyd":                {"name": "网页终端",       "desc": "浏览器里的 shell"},
    "nginx":               {"name": "Nginx",         "desc": "Web 服务"},
    "smbd":                {"name": "Samba 共享",     "desc": "局域网文件共享"},
    "ssh":                 {"name": "SSH",           "desc": "远程命令行"},
}

# 应用入口：path 为相对或绝对地址，port 用于探活
APPS = [
    {"id": "files",    "name": "我的存储", "icon": "folder",  "desc": "浏览、上传、下载", "path": "#files",   "port": 0,    "color": "#4f8cff"},
    {"id": "photos",   "name": "相册",     "icon": "photo",   "desc": "图片墙浏览",       "path": "#photos",  "port": 0,    "color": "#e879f9"},
    {"id": "media",    "name": "媒体播放", "icon": "play",    "desc": "视频在线播放",     "path": "#media",   "port": 0,    "color": "#22d3ee"},
    {"id": "music",    "name": "音乐",     "icon": "music",   "desc": "音频播放器",       "path": "#music",   "port": 0,    "color": "#f5566a"},
    {"id": "notes",    "name": "记事本",   "icon": "file",    "desc": "随手记点东西",     "path": "#notes",   "port": 0,    "color": "#f5a524"},
    {"id": "calc",     "name": "计算器",   "icon": "calc",    "desc": "算个数",           "path": "#calc",    "port": 0,    "color": "#7c6cff"},
    {"id": "cron",     "name": "计划任务", "icon": "clock",   "desc": "定时执行命令",     "path": "#cron",    "port": 0,    "color": "#0f7b5f"},
    {"id": "docker",   "name": "Docker",   "icon": "box",     "desc": "容器管理",         "path": "#docker",  "port": 0,    "color": "#2496ed"},
    {"id": "terminal", "name": "终端",     "icon": "terminal","desc": "网页里的命令行",   "path": "http://{host}:7681", "port": 7681, "color": "#2ecc8f"},
    {"id": "bt",       "name": "BT 下载",  "icon": "download","desc": "Transmission",     "path": "http://{host}:9091", "port": 9091, "color": "#f5a524"},
    {"id": "aria2",    "name": "下载中心", "icon": "bolt",    "desc": "Aria2 图形界面",   "path": "/ariang/",  "port": 6801, "color": "#2ecc8f"},
    {"id": "alist",    "name": "Alist",    "icon": "globe",   "desc": "网盘聚合与挂载",   "path": "http://{host}:5244", "port": 5244, "color": "#4f8cff"},
    {"id": "services", "name": "后端服务", "icon": "layers",  "desc": "启停系统服务",     "path": "#services","port": 0,    "color": "#7c6cff"},
    {"id": "share",    "name": "网络共享", "icon": "share",   "desc": "Samba 目录管理",   "path": "#share",   "port": 445,  "color": "#0f7b5f"},
    {"id": "storage",  "name": "磁盘管理", "icon": "hdd",     "desc": "容量与挂载",       "path": "#storage", "port": 0,    "color": "#22d3ee"},
    {"id": "store",    "name": "应用商店", "icon": "shop",    "desc": "一键装软件",       "path": "#store",   "port": 0,    "color": "#f97316"},
    {"id": "backup",   "name": "磁盘备份", "icon": "backup",  "desc": "定时同步目录",     "path": "#backup",  "port": 0,    "color": "#8b5cf6"},
    {"id": "site",     "name": "部署网站", "icon": "web",     "desc": "一键建站",         "path": "#site",    "port": 0,    "color": "#0891b2"},
    {"id": "remote",   "name": "远程访问", "icon": "wifi",    "desc": "出门也能连回家",   "path": "#remote",  "port": 0,    "color": "#059669"},
    {"id": "help",     "name": "使用说明", "icon": "book",    "desc": "这机器怎么用",     "path": "#help",    "port": 0,    "color": "#9ca3af"},
    {"id": "trash",    "name": "回收站",   "icon": "trash",   "desc": "误删的文件在这",   "path": "#files?trash=1", "port": 0, "color": "#e2574c"},
    {"id": "settings", "name": "设置",     "icon": "cog",     "desc": "密码与系统",       "path": "#settings","port": 0,    "color": "#888780"},
]

SESSIONS = {}
_SESSION_LOCK = threading.Lock()
_STAT_CACHE = {"ts": 0, "cpu": {}, "net": {}}

# 媒体类型
IMG_EXT = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".heic", ".avif")
VIDEO_EXT = (".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v", ".ts", ".flv")
AUDIO_EXT = (".mp3", ".flac", ".m4a", ".aac", ".wav", ".ogg", ".opus", ".wma")
MIME = {
    ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8", ".json": "application/json",
    ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp",
    ".ico": "image/x-icon", ".mp4": "video/mp4", ".webm": "video/webm",
    ".mkv": "video/x-matroska", ".mov": "video/quicktime",
    ".mp3": "audio/mpeg", ".flac": "audio/flac", ".m4a": "audio/mp4",
    ".wav": "audio/wav", ".ogg": "audio/ogg", ".txt": "text/plain; charset=utf-8",
}
NOTES_FILE = os.path.join(DATA_DIR, "notes.json")
UI_FILE = os.path.join(DATA_DIR, "ui.json")
ALBUM_FILE = os.path.join(DATA_DIR, "albums.json")
NET_FILE = os.path.join(DATA_DIR, "net.json")
SHARE_FILE = os.path.join(DATA_DIR, "shares.json")
WALL_DIR = os.path.join(DATA_DIR, "wallpaper")

# 操作审计（JSON Lines，超过 2MB 轮转到 audit.log.1）
AUDIT_FILE = os.path.join(DATA_DIR, "audit.log")
AUDIT_MAX = 2 * 1024 * 1024
# 这些接口由各自分支写更具体的审计，统一入口不再重复记录
AUDIT_DETAILED_POST = {"/api/logout", "/api/passwd", "/api/service", "/api/docker",
                       "/api/delete", "/api/upload", "/api/config/import"}


# ---------------------------------------------------------------- 基础工具
def run(cmd, timeout=8):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, timeout=timeout)
        return (p.stdout or b"").decode("utf-8", "replace").strip()
    except Exception:
        return ""


def read(path, default=""):
    try:
        with open(path, "r") as f:
            return f.read().strip()
    except Exception:
        return default


def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.chmod(DATA_DIR, 0o755)


USERS_FILE = os.path.join(DATA_DIR, "users.json")
ROLES = ("admin", "viewer")


def _hash_pw(pw, salt):
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 120000).hex()


def load_users():
    """多账号存储 {"users":[{name,salt,hash,role,created}]}；首次自动迁移旧 auth.json。"""
    try:
        with open(USERS_FILE) as f:
            d = json.load(f)
        users = d.get("users") if isinstance(d, dict) else None
        if isinstance(users, list) and users:
            return users
    except Exception:
        pass
    try:
        with open(AUTH_FILE) as f:
            a = json.load(f)
        if a.get("salt") and a.get("hash"):
            u = {"name": "admin", "salt": a["salt"], "hash": a["hash"],
                 "role": "admin", "created": int(a.get("updated") or time.time())}
            save_users([u])
            return [u]
    except Exception:
        pass
    return []


def save_users(users):
    ensure_data_dir()
    tmp = USERS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"users": users}, f, ensure_ascii=False)
    os.chmod(tmp, 0o600)
    os.replace(tmp, USERS_FILE)


def find_user(name):
    name = (name or "").strip()
    for u in load_users():
        if u.get("name") == name:
            return u
    return None


def has_password():
    return bool(load_users())


def verify_user(name, pw):
    u = find_user(name)
    if not u or not u.get("hash"):
        return False
    return hmac.compare_digest(_hash_pw(pw, u.get("salt", "")), u.get("hash", ""))


def verify_password(pw):
    return verify_user("admin", pw)


def set_user_password(name, pw):
    users = load_users()
    for u in users:
        if u.get("name") == name:
            u["salt"] = secrets.token_hex(16)
            u["hash"] = _hash_pw(pw, u["salt"])
            u["updated"] = int(time.time())
            save_users(users)
            return True
    return False


def add_user(name, pw, role="viewer"):
    users = load_users()
    if any(u.get("name") == name for u in users):
        raise ValueError("用户名已存在")
    salt = secrets.token_hex(16)
    users.append({"name": name, "salt": salt, "hash": _hash_pw(pw, salt),
                  "role": role if role in ROLES else "viewer",
                  "created": int(time.time())})
    save_users(users)
    return True


def del_user(name):
    users = load_users()
    target = next((u for u in users if u.get("name") == name), None)
    if not target:
        raise ValueError("用户不存在")
    rest = [u for u in users if u.get("name") != name]
    if not rest:
        raise ValueError("至少要保留一个账号")
    if target.get("role") == "admin" and not any(u.get("role") == "admin" for u in rest):
        raise ValueError("至少要保留一个管理员")
    save_users(rest)
    return True


def set_user_role(name, role):
    if role not in ROLES:
        raise ValueError("角色只能是管理员或只读")
    users = load_users()
    target = next((u for u in users if u.get("name") == name), None)
    if not target:
        raise ValueError("用户不存在")
    if target.get("role") == "admin" and role != "admin":
        if not any(u.get("role") == "admin" and u.get("name") != name for u in users):
            raise ValueError("至少要保留一个管理员")
    target["role"] = role
    save_users(users)
    return True


def save_password(pw):
    """设置 admin 密码（首次初始化 / 恢复码重置）。"""
    if find_user("admin"):
        set_user_password("admin", pw)
        return
    add_user("admin", pw, "admin")


def recovery_key():
    kf = os.path.join(DATA_DIR, "recovery-key")
    try:
        with open(kf) as f:
            k = f.read().strip()
    except Exception:
        k = None
    if not k:
        k = secrets.token_hex(6)  # 12 字符
        ensure_data_dir()
        with open(kf, "w") as f:
            f.write(k)
        os.chmod(kf, 0o600)
    return k


def reset_password(newpw):
    save_password(newpw)
    # 重置后轮换恢复码
    kf = os.path.join(DATA_DIR, "recovery-key")
    with open(kf, "w") as f:
        f.write(secrets.token_hex(6))
    os.chmod(kf, 0o600)


def new_session(user="admin", role="admin"):
    tok = secrets.token_urlsafe(24)
    with _SESSION_LOCK:
        SESSIONS[tok] = {"exp": time.time() + 7 * 86400, "user": user, "role": role}
    return tok


def session_info(tok):
    if not tok:
        return None
    with _SESSION_LOCK:
        v = SESSIONS.get(tok)
        if not v:
            return None
        if isinstance(v, dict):
            if v.get("exp", 0) < time.time():
                SESSIONS.pop(tok, None)
                return None
            return v
        if v < time.time():  # 兼容旧格式（纯过期时间戳）
            SESSIONS.pop(tok, None)
            return None
        return {"exp": v, "user": "admin", "role": "admin"}


def session_ok(tok):
    return session_info(tok) is not None


# ---------------------------------------------------------------- 操作审计
def _audit_rotate():
    try:
        if os.path.getsize(AUDIT_FILE) > AUDIT_MAX:
            bak = AUDIT_FILE + ".1"
            try:
                os.remove(bak)
            except OSError:
                pass
            os.rename(AUDIT_FILE, bak)
    except Exception:
        pass


def audit(event, detail="", ip="", user="admin"):
    """写一条操作审计（JSON Lines）。任何异常都静默，绝不影响业务。"""
    try:
        ensure_data_dir()
        _audit_rotate()
        rec = {"ts": int(time.time()), "event": str(event)[:40],
               "detail": str(detail)[:600], "ip": ip, "user": user}
        with open(AUDIT_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def read_audit(limit=200, event="", keyword=""):
    items = []
    try:
        with open(AUDIT_FILE, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if event and rec.get("event") != event:
                    continue
                if keyword and keyword.lower() not in json.dumps(rec, ensure_ascii=False).lower():
                    continue
                items.append(rec)
    except OSError:
        pass
    return items[-limit:][::-1]


def audit_stat():
    out = {"size": 0, "count": 0}
    try:
        out["size"] = os.path.getsize(AUDIT_FILE)
    except OSError:
        return out
    try:
        with open(AUDIT_FILE, encoding="utf-8", errors="replace") as f:
            out["count"] = sum(1 for ln in f if ln.strip())
    except OSError:
        pass
    return out


# ---------------------------------------------------------------- 全局搜索
SEARCH_ROOT = "/mnt"
SEARCH_SKIP_DIRS = {".trash", "__pycache__", ".git", "node_modules", ".thumb", "lost+found"}


def search_files(keyword, limit=60):
    """在数据盘内按名称模糊搜索文件和目录（深度 4，跳过隐藏/缓存目录）。"""
    ql = keyword.lower()
    hits = []
    base = SEARCH_ROOT if os.path.isdir(SEARCH_ROOT) else "/"
    try:
        for root, dirs, files in os.walk(base):
            depth = root[len(base):].count(os.sep)
            dirs[:] = [x for x in dirs if x not in SEARCH_SKIP_DIRS and not x.startswith(".")]
            if depth >= 4:
                dirs[:] = []
            else:
                for d in dirs:
                    if ql not in d.lower():
                        continue
                    fp = os.path.join(root, d)
                    try:
                        mt = int(os.path.getmtime(fp))
                    except OSError:
                        mt = 0
                    hits.append({"name": d, "path": fp, "dir": root, "size": 0,
                                 "mtime": mt, "kind": "dir"})
                    if len(hits) >= limit:
                        return hits
            for name in files:
                if ql not in name.lower():
                    continue
                fp = os.path.join(root, name)
                try:
                    st = os.stat(fp)
                except OSError:
                    continue
                hits.append({"name": name, "path": fp, "dir": root,
                             "size": st.st_size, "mtime": int(st.st_mtime),
                             "kind": "file"})
                if len(hits) >= limit:
                    return hits
    except Exception:
        pass
    return hits


# ---------------------------------------------------------------- 配置备份 / 恢复
CONFIG_SKIP_FILES = {"auth.json", "recovery-key", "audit.log", "audit.log.1", "users.json"}
CONFIG_EXPORT_FILES = [
    ("var/spool/cron/crontabs/root", "/var/spool/cron/crontabs/root"),
    ("etc/samba/smb.conf", "/etc/samba/smb.conf"),
    ("etc/exports", "/etc/exports"),
    ("etc/vsftpd.conf", "/etc/vsftpd.conf"),
    ("etc/systemd/system/box-webdav.service", "/etc/systemd/system/box-webdav.service"),
    ("etc/nginx/sites-available/covernas.conf", "/etc/nginx/sites-available/covernas.conf"),
]


def export_config_bytes():
    """把面板配置打成 tar.gz（内存中完成）。返回 (bytes, 文件数)。"""
    buf = io.BytesIO()
    count = 0
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for root, dirs, files in os.walk(DATA_DIR):
            for name in files:
                full = os.path.join(root, name)
                rel = os.path.relpath(full, DATA_DIR)
                if rel in CONFIG_SKIP_FILES:
                    continue
                if any(part.startswith(".") for part in rel.split("/")):
                    continue  # 跳过 .preview-open 之类的隐藏残留
                try:
                    tar.add(full, arcname="etc/box/" + rel)
                    count += 1
                except Exception:
                    continue
        for arc, full in CONFIG_EXPORT_FILES:
            if os.path.isfile(full):
                try:
                    tar.add(full, arcname=arc)
                    count += 1
                except Exception:
                    continue
        sites = "/etc/nginx/sites-available"
        if os.path.isdir(sites):
            for name in sorted(os.listdir(sites)):
                if name.startswith("box-") and name.endswith(".conf"):
                    try:
                        tar.add(os.path.join(sites, name), arcname="etc/nginx/sites-available/" + name)
                        count += 1
                    except Exception:
                        continue
    return buf.getvalue(), count


def _config_member_allowed(name):
    """只允许恢复白名单路径，拒绝绝对路径/.. 穿越。"""
    if not name or name.startswith("/") or "\\" in name:
        return False
    parts = name.split("/")
    if ".." in parts or "" in parts:
        return False
    if name.startswith("etc/box/"):
        leaf = parts[-1]
        return leaf not in CONFIG_SKIP_FILES
    if name == "var/spool/cron/crontabs/root":
        return True
    if name in ("etc/samba/smb.conf", "etc/exports", "etc/vsftpd.conf",
                "etc/systemd/system/box-webdav.service"):
        return True
    if name.startswith("etc/nginx/sites-available/") or name.startswith("etc/nginx/sites-enabled/"):
        leaf = parts[-1]
        return leaf == "covernas.conf" or (leaf.startswith("box-") and leaf.endswith(".conf"))
    return False


def import_config_bytes(data):
    """从 tar.gz 恢复白名单内的配置，返回已写入的相对路径列表。"""
    applied = []
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for m in tar.getmembers():
            if not m.isreg():
                continue
            name = m.name.replace("\\", "/")
            while name.startswith("./"):
                name = name[2:]
            name = name.lstrip("/")
            if not _config_member_allowed(name):
                continue
            src = tar.extractfile(m)
            if src is None:
                continue
            target = os.path.join("/", name)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as out:
                out.write(src.read())
            applied.append(name)
    if applied:
        try:
            os.chmod(DATA_DIR, 0o755)
        except OSError:
            pass
    for rel in applied:
        if rel.startswith("etc/box/") and rel not in ("etc/box",):
            try:
                os.chmod(os.path.join("/", rel), 0o600)
            except OSError:
                pass
    return applied


# ---------------------------------------------------------------- 系统指标
def _cpu_model():
    try:
        txt = read("/proc/cpuinfo", "")
        for line in txt.split("\n"):
            if ":" in line:
                k, v = line.split(":", 1)
                k = k.strip().lower()
                if k in ("model name", "hardware", "model"):
                    return v.strip()
                if k == "revision" and v.strip():
                    return "Amlogic " + v.strip()
    except Exception:
        pass
    # Amlogic S805 板子没有 model name 字段，按架构兜底
    return "Amlogic S805（四核 A5）"


def cpu_pct():
    def snap():
        parts = read("/proc/stat", "").split("\n")[0].split()
        vals = [int(x) for x in parts[1:]]
        idle = vals[3] + (vals[4] if len(vals) > 4 else 0)
        return sum(vals), idle

    t0, i0 = snap()
    time.sleep(0.15)
    t1, i1 = snap()
    dt, di = t1 - t0, i1 - i0
    if dt <= 0:
        return 0.0
    return max(0.0, min(100.0, (1 - di / dt) * 100))


def meminfo():
    out = {}
    for line in read("/proc/meminfo", "").split("\n"):
        m = re.match(r"^(\w+):\s+(\d+)", line)
        if m:
            out[m.group(1)] = int(m.group(2)) * 1024
    return out


def net_rate():
    now = time.time()
    rx = int(read("/sys/class/net/eth0/statistics/rx_bytes", "0") or 0)
    tx = int(read("/sys/class/net/eth0/statistics/tx_bytes", "0") or 0)
    prev = _STAT_CACHE.get("net") or {}
    rate = {"rx": 0, "tx": 0, "iface": "eth0"}
    if prev.get("ts") and now > prev["ts"]:
        el = now - prev["ts"]
        if el > 0.2:
            rate["rx"] = max(0, int((rx - prev.get("rx", rx)) / el))
            rate["tx"] = max(0, int((tx - prev.get("tx", tx)) / el))
    _STAT_CACHE["net"] = {"ts": now, "rx": rx, "tx": tx}
    return rate


def disk_of(path):
    try:
        s = os.statvfs(path)
        total = s.f_blocks * s.f_frsize
        free = s.f_bavail * s.f_frsize
        used = total - free
        return {"total": total, "used": used, "free": free,
                "pct": round(used * 100.0 / total, 1) if total else 0}
    except Exception:
        return {"total": 0, "used": 0, "free": 0, "pct": 0}


def temp_c():
    v = read("/sys/class/thermal/thermal_zone0/temp", "")
    if v.isdigit():
        return round(int(v) / 1000.0, 1)
    return 0.0


def service_state(unit):
    return run("systemctl is-active %s 2>/dev/null" % unit) or "unknown"


def port_open(port):
    if not port:
        return None
    s = socket.socket()
    s.settimeout(0.25)
    try:
        s.connect(("127.0.0.1", int(port)))
        return True
    except Exception:
        return False
    finally:
        s.close()


# ---------------------------------------------------------------- 文件操作
def safe_path(p):
    p = os.path.realpath(p or "/")
    for root in FILE_ROOTS:
        if p == root or p.startswith(root.rstrip("/") + "/"):
            for d in DENY_PREFIX:
                if p == d or p.startswith(d + "/"):
                    raise ValueError("该目录不允许访问")
            return p
    raise ValueError("路径越界")


def writable(p):
    """该路径是否允许写操作（系统目录只读保护）"""
    try:
        p = os.path.realpath(p or "/")
    except Exception:
        return False
    for root in WRITE_ROOTS:
        if p == root or p.startswith(root.rstrip("/") + "/"):
            return True
    return False


def require_writable(p):
    if not writable(p):
        raise ValueError("系统目录受保护，不能修改（数据请放在 /mnt）")
    return p


def human(n):
    n = float(n or 0)
    for u in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024:
            return ("%.0f %s" % (n, u)) if u == "B" else ("%.1f %s" % (n, u))
        n /= 1024
    return "%.1f PB" % n


def list_dir(path):
    p = safe_path(path)
    items = []
    with os.scandir(p) as it:
        for e in it:
            try:
                st = e.stat(follow_symlinks=False)
                is_dir = e.is_dir(follow_symlinks=False)
                items.append({
                    "name": e.name,
                    "dir": is_dir,
                    "size": 0 if is_dir else st.st_size,
                    "size_h": "" if is_dir else human(st.st_size),
                    "mtime": int(st.st_mtime),
                    "mode": oct(st.st_mode & 0o777)[2:],
                })
            except Exception:
                continue
    items.sort(key=lambda x: (not x["dir"], x["name"].lower()))
    return {"path": p, "parent": os.path.dirname(p) if p != "/" else None,
            "writable": writable(p), "items": items}


def move_to_trash(path):
    p = require_writable(safe_path(path))
    rel = p.lstrip("/")
    dest = os.path.join(TRASH_DIR, time.strftime("%Y%m%d-%H%M%S"), rel)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.move(p, dest)
    return dest


def scan_media(base, exts, limit=600, depth=4):
    """递归扫描媒体文件，限制深度与数量，避免小内存设备卡死"""
    try:
        base = safe_path(base)
    except Exception:
        return []
    out = []
    base_depth = base.rstrip("/").count("/")
    for root, dirs, files in os.walk(base):
        if root.count("/") - base_depth >= depth:
            dirs[:] = []
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fn in files:
            if fn.startswith("."):
                continue
            if os.path.splitext(fn)[1].lower() in exts:
                fp = os.path.join(root, fn)
                try:
                    st = os.stat(fp)
                except Exception:
                    continue
                out.append({"name": fn, "path": fp,
                            "size": st.st_size, "size_h": human(st.st_size),
                            "mtime": int(st.st_mtime)})
                if len(out) >= limit:
                    break
        if len(out) >= limit:
            break
    out.sort(key=lambda x: -x["mtime"])
    return out


def load_notes():
    try:
        with open(NOTES_FILE) as f:
            return json.load(f).get("notes", [])
    except Exception:
        return []


def save_notes(notes):
    ensure_data_dir()
    with open(NOTES_FILE, "w") as f:
        json.dump({"notes": notes}, f, ensure_ascii=False)
    os.chmod(NOTES_FILE, 0o600)


def load_ui():
    try:
        with open(UI_FILE) as f:
            d = json.load(f)
    except Exception:
        d = {}
    d.setdefault("theme", "light")
    d.setdefault("wall", "default")
    d.setdefault("accent", "#0f7b5f")
    d.setdefault("video_speed", 1)
    d.setdefault("warn_temp", 65)
    d.setdefault("home_order", ["cpu", "mem", "disk", "temp"])
    return d


def save_ui(d):
    ensure_data_dir()
    cur = load_ui()
    cur.update(d or {})
    with open(UI_FILE, "w") as f:
        json.dump(cur, f, ensure_ascii=False)
    os.chmod(UI_FILE, 0o600)
    return cur


def load_albums():
    try:
        with open(ALBUM_FILE) as f:
            return json.load(f).get("albums", [])
    except Exception:
        return []


def save_albums(albums):
    ensure_data_dir()
    with open(ALBUM_FILE, "w") as f:
        json.dump({"albums": albums}, f, ensure_ascii=False)
    os.chmod(ALBUM_FILE, 0o600)


WALL_PRESETS = [
    "#0f2b33,#12404a,#1c4f57,#0b1e26",
    "#1a1a2e,#16213e,#0f3460,#1a1a2e",
    "#232526,#414345,#232526,#1c1c1c",
    "#134e5e,#71b280,#134e5e,#0f3d2e",
    "#2c3e50,#4ca1af,#2c3e50,#1a252f",
    "#3a1c71,#d76d77,#ffaf7b,#3a1c71",
    "#0f2027,#203a43,#2c5364,#0f2027",
    "#141e30,#243b55,#141e30,#0b1220",
]


def _gradient_css(colors):
    c = colors.split(",")
    stops = ", ".join("%s %d%%" % (x, round(i * 100.0 / (len(c) - 1)))
                      for i, x in enumerate(c))
    return "linear-gradient(150deg, %s)" % stops


# 壁纸库：纯渐变 + 极光/晚霞/深海/波纹/网格等风格（纯 CSS，无外部图片依赖）
WALLS = [{"id": "g%d" % i, "name": "渐变 %d" % (i + 1), "css": _gradient_css(c)}
         for i, c in enumerate(WALL_PRESETS)] + [
    {"id": "aurora", "name": "极光", "css":
        "radial-gradient(52% 68% at 18% 12%, rgba(46,213,115,.45) 0%, transparent 60%),"
        "radial-gradient(48% 62% at 82% 22%, rgba(124,108,255,.40) 0%, transparent 62%),"
        "radial-gradient(60% 70% at 55% 88%, rgba(34,211,238,.32) 0%, transparent 65%),"
        "linear-gradient(160deg, #071a1e 0%, #0b2530 55%, #06121a 100%)"},
    {"id": "dusk", "name": "晚霞", "css":
        "radial-gradient(70% 60% at 75% 15%, rgba(255,175,123,.50) 0%, transparent 60%),"
        "radial-gradient(55% 65% at 20% 80%, rgba(215,109,119,.45) 0%, transparent 62%),"
        "linear-gradient(165deg, #2b1650 0%, #3a1c71 45%, #1c1032 100%)"},
    {"id": "ocean", "name": "深海", "css":
        "radial-gradient(60% 55% at 30% 20%, rgba(34,211,238,.35) 0%, transparent 60%),"
        "radial-gradient(50% 60% at 80% 75%, rgba(37,99,235,.40) 0%, transparent 62%),"
        "linear-gradient(170deg, #06202e 0%, #0a3547 50%, #041520 100%)"},
    {"id": "mist", "name": "晨雾", "css":
        "radial-gradient(55% 60% at 25% 18%, rgba(163,230,178,.40) 0%, transparent 60%),"
        "radial-gradient(60% 65% at 78% 30%, rgba(113,178,128,.35) 0%, transparent 62%),"
        "linear-gradient(160deg, #12291f 0%, #1c4f57 55%, #0b1e26 100%)"},
    {"id": "waves", "name": "波纹", "size": "auto, auto, cover, cover", "css":
        "repeating-radial-gradient(circle at 50% 120%, rgba(96,165,250,.14) 0 2px, transparent 2px 90px),"
        "radial-gradient(65% 60% at 50% 0%, rgba(59,130,246,.30) 0%, transparent 62%),"
        "linear-gradient(180deg, #0b1526 0%, #10233f 60%, #0a1322 100%)"},
    {"id": "grid", "name": "蓝图", "size": "44px 44px, 44px 44px, cover, cover", "css":
        "linear-gradient(rgba(125,211,252,.09) 1px, transparent 1px),"
        "linear-gradient(90deg, rgba(125,211,252,.09) 1px, transparent 1px),"
        "radial-gradient(70% 60% at 50% 20%, rgba(56,189,248,.22) 0%, transparent 60%),"
        "linear-gradient(180deg, #081521 0%, #0d2436 100%)"},
]


def wall_by_id(wid):
    for w in WALLS:
        if w["id"] == wid:
            return w
    return None


def wall_file():
    if not os.path.isdir(WALL_DIR):
        return None
    for name in os.listdir(WALL_DIR):
        if name.startswith("wall."):
            return name
    return None


def trash_stat():
    total, count = 0, 0
    if os.path.isdir(TRASH_DIR):
        for root, dirs, files in os.walk(TRASH_DIR):
            for fn in files:
                try:
                    total += os.path.getsize(os.path.join(root, fn))
                    count += 1
                except OSError:
                    pass
    return {"count": count, "size": total}


# ---------------------------------------------------------------- 后台任务
JOBS = {}
JOBS_LOCK = threading.Lock()


def start_job(name, cmd):
    """在后台跑一条 shell 命令，输出写日志，返回 job id"""
    jid = "%d-%d" % (int(time.time()), secrets.randbelow(900) + 100)
    logf = "/tmp/box-job-%s.log" % jid
    with JOBS_LOCK:
        JOBS[jid] = {"name": name, "log": logf, "running": True,
                     "rc": None, "started": time.time(), "cmd": cmd}

    def _run():
        try:
            with open(logf, "wb") as f:
                f.write(("$ %s\n\n" % cmd).encode())
                f.flush()
                p = subprocess.Popen(["/bin/bash", "-lc", cmd],
                                     stdout=f, stderr=subprocess.STDOUT,
                                     stdin=subprocess.DEVNULL)
                rc = p.wait()
        except Exception as e:
            rc = 1
            with open(logf, "a") as f:
                f.write("\n[启动失败] %s\n" % e)
        with JOBS_LOCK:
            JOBS[jid]["running"] = False
            JOBS[jid]["rc"] = rc

    t = threading.Thread(target=_run)
    t.daemon = True
    t.start()
    return jid


def job_state(jid, tail=6000):
    j = JOBS.get(jid)
    if not j:
        return None
    try:
        with open(j["log"], "rb") as f:
            data = f.read()[-tail:]
        text = data.decode("utf-8", "replace")
    except Exception:
        text = ""
    # 去掉 apt 的彩色控制符与进度条转义
    text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text)
    text = re.sub(r"\x1b\][^\x07]*\x07", "", text)
    text = text.replace("\r", "")
    return {"id": jid, "name": j["name"], "running": j["running"],
            "rc": j["rc"], "text": text}



# ---------------------------------------------------------------- 网络共享
def smb_users():
    out = run("pdbedit -L 2>/dev/null", 10)
    users = []
    for line in out.split("\n"):
        if ":" in line:
            users.append(line.split(":", 1)[0].strip())
    return [u for u in users if u]


def nfs_exports():
    out = []
    try:
        with open("/etc/exports") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    out.append({"path": parts[0], "clients": parts[1]})
    except Exception:
        pass
    return out


def load_net():
    try:
        with open(NET_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_net(d):
    ensure_data_dir()
    cur = load_net()
    cur.update(d or {})
    with open(NET_FILE, "w") as f:
        json.dump(cur, f, ensure_ascii=False)
    os.chmod(NET_FILE, 0o600)
    return cur


def load_shares():
    try:
        with open(SHARE_FILE) as f:
            return json.load(f).get("items", {})
    except Exception:
        return {}


def save_shares(items):
    ensure_data_dir()
    with open(SHARE_FILE, "w") as f:
        json.dump({"items": items}, f, ensure_ascii=False)
    os.chmod(SHARE_FILE, 0o600)


def webdav_unit():
    return "/etc/systemd/system/box-webdav.service"


def write_webdav(cfg):
    unit = """[Unit]
Description=Box WebDAV
After=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/rclone serve webdav %(path)s --addr 0.0.0.0:%(port)d --user %(user)s --pass %(pass)s --vfs-cache-mode off --no-modtime
Restart=always
RestartSec=4

[Install]
WantedBy=multi-user.target
""" % cfg
    with open(webdav_unit(), "w") as f:
        f.write(unit)
    run("systemctl daemon-reload", 20)
    run("systemctl enable box-webdav 2>/dev/null", 20)


def ftp_conf(root):
    return """listen=YES
listen_ipv6=NO
anonymous_enable=NO
local_enable=YES
write_enable=YES
local_umask=022
dirmessage_enable=YES
use_localtime=YES
xferlog_enable=YES
connect_from_port_20=YES
chroot_local_user=YES
allow_writeable_chroot=YES
secure_chroot_dir=/var/run/vsftpd/empty
pam_service_name=vsftpd
pasv_enable=YES
pasv_min_port=30000
pasv_max_port=30100
local_root=%s
""" % root


# ---------------------------------------------------------------- 进程 / 维护
def proc_list(limit=60):
    out = run("ps -eo pid,ppid,pcpu,pmem,rss,etime,comm,args --sort=-pcpu 2>/dev/null", 10)
    rows = []
    for line in out.split("\n")[1:limit + 1]:
        parts = line.split(None, 7)
        if len(parts) < 8:
            continue
        pid, ppid, pcpu, pmem, rss, etime, comm, args = parts
        if not pid.isdigit():
            continue
        rows.append({"pid": int(pid), "ppid": ppid, "cpu": float(pcpu),
                     "mem": float(pmem), "rss": int(rss) * 1024,
                     "etime": etime, "name": comm, "cmd": args[:180]})
    return rows


def diagnose():
    parts = []
    def sec(title, cmd):
        parts.append("== %s ==" % title)
        parts.append(run(cmd, 12).strip() or "(无输出)")
        parts.append("")

    sec("系统", "uname -a; uptime")
    sec("内存", "free -m")
    sec("磁盘", "df -h / /mnt 2>/dev/null")
    sec("温度", "for z in /sys/class/thermal/thermal_zone*/temp; do echo -n \"$z \"; cat $z; done")
    sec("失败的服务", "systemctl --failed --no-legend")
    sec("最近的内核错误", "dmesg 2>/dev/null | grep -iE 'error|fail|oom|I/O' | tail -15")
    sec("OOM 记录", "dmesg 2>/dev/null | grep -i 'killed process' | tail -8")
    sec("磁盘健康", "for d in /dev/mmcblk1 /dev/sda; do [ -b $d ] && smartctl -H $d 2>/dev/null | grep -iE 'result|health|SMART'; done")
    return "\n".join(parts)


# ---------------------------------------------------------------- 分享链接
def share_urls():
    items = load_shares()
    out = []
    for tok, v in items.items():
        out.append({"token": tok, "path": v.get("path"), "created": v.get("created", 0),
                    "downloads": v.get("downloads", 0)})
    out.sort(key=lambda x: -x["created"])
    return out


# ---------------------------------------------------------------- 应用商店
STORE = [
    # ---------- 共享 / 存储 ----------
    {"id": "samba", "name": "Samba 共享", "cat": "共享", "pkg": "samba", "need": "smbd",
     "icon": "share", "color": "#0f7b5f",
     "desc": "Mac 访达 / Windows 网上邻居访问", "size": "约 35MB"},
    {"id": "nginx", "name": "Nginx", "cat": "共享", "pkg": "nginx", "need": "nginx",
     "icon": "web", "color": "#0891b2",
     "desc": "网站服务，部署网页要用", "size": "约 12MB"},
    {"id": "vsftpd", "name": "FTP 服务", "cat": "共享", "pkg": "vsftpd", "need": "vsftpd",
     "icon": "share", "color": "#0f7b5f",
     "desc": "老式 FTP，部分设备只认这个", "size": "约 1MB"},
    {"id": "caddy", "name": "Caddy", "cat": "共享", "pkg": "caddy", "need": "caddy",
     "icon": "web", "color": "#22b3a3",
     "desc": "现代 Web 服务器，自动 HTTPS", "size": "约 20MB"},
    {"id": "filebrowser", "name": "File Browser", "cat": "共享", "kind": "docker",
     "container": "filebrowser", "image": "filebrowser/filebrowser:latest",
     "ports": "-p 8090:80", "args": "-v /mnt:/srv",
     "need": "filebrowser", "icon": "folder", "color": "#4f8cff",
     "desc": "网页文件管理（端口 8090，默认 admin/admin）", "size": "镜像约 30MB",
     "app": {"path": "http://{host}:8090", "port": 8090}},

    # ---------- 下载 ----------
    {"id": "aria2", "name": "Aria2", "cat": "下载", "pkg": "aria2", "need": "aria2c",
     "icon": "bolt", "color": "#2ecc8f",
     "desc": "HTTP / 磁力 多线程下载", "size": "约 6MB"},
    {"id": "transmission", "name": "Transmission", "cat": "下载", "pkg": "transmission-daemon",
     "need": "transmission-daemon", "icon": "download", "color": "#f5a524",
     "desc": "BT / PT 下载守护进程", "size": "约 9MB"},
    {"id": "qbittorrent", "name": "qBittorrent", "cat": "下载", "pkg": "qbittorrent-nox",
     "need": "qbittorrent-nox", "icon": "download", "color": "#3498db",
     "desc": "另一款 BT 客户端，功能更全", "size": "约 40MB"},

    # ---------- 同步 ----------
    {"id": "syncthing", "name": "Syncthing", "cat": "同步", "pkg": "syncthing",
     "need": "syncthing", "icon": "refresh", "color": "#7c6cff",
     "desc": "多设备间自动同步文件", "size": "约 25MB"},
    {"id": "rclone", "name": "rclone", "cat": "同步", "pkg": "rclone", "need": "rclone",
     "icon": "globe", "color": "#4f8cff",
     "desc": "同步到云盘 / S3，备份用", "size": "约 40MB"},
    {"id": "rsync", "name": "rsync", "cat": "同步", "pkg": "rsync", "need": "rsync",
     "icon": "refresh", "color": "#7c6cff",
     "desc": "增量同步与备份的老牌工具", "size": "约 1MB"},

    # ---------- 媒体 ----------
    {"id": "minidlna", "name": "DLNA", "cat": "媒体", "pkg": "minidlna", "need": "minidlnad",
     "icon": "play", "color": "#22d3ee",
     "desc": "电视 / 播放器直接发现影片", "size": "约 2MB"},
    {"id": "ffmpeg", "name": "ffmpeg", "cat": "媒体", "pkg": "ffmpeg", "need": "ffmpeg",
     "icon": "play", "color": "#e879f9",
     "desc": "转码 / 缩略图，CPU 弱慎装", "size": "约 60MB"},
    {"id": "imagemagick", "name": "ImageMagick", "cat": "媒体", "pkg": "imagemagick",
     "need": "convert", "icon": "image", "color": "#f5a524",
     "desc": "图片批处理、格式转换", "size": "约 30MB"},
    {"id": "navidrome", "name": "Navidrome", "cat": "媒体", "kind": "docker",
     "container": "navidrome", "image": "deluan/navidrome:latest",
     "ports": "-p 4533:4533", "args": "-v /mnt/navidrome:/data",
     "need": "navidrome", "icon": "music", "color": "#e879f9",
     "desc": "个人音乐流媒体（端口 4533）", "size": "镜像约 90MB",
     "app": {"path": "http://{host}:4533", "port": 4533}},
    {"id": "jellyfin", "name": "Jellyfin", "cat": "媒体", "kind": "docker",
     "container": "jellyfin", "image": "jellyfin/jellyfin:latest",
     "ports": "-p 8096:8096",
     "args": "-v /mnt/jellyfin/config:/config -v /mnt/jellyfin/cache:/cache -v /mnt:/media:ro",
     "need": "jellyfin", "icon": "play", "color": "#a45ee5",
     "desc": "媒体服务器（端口 8096，armv7 转码弱，建议直接播放）", "size": "镜像约 500MB",
     "app": {"path": "http://{host}:8096", "port": 8096}},

    # ---------- 系统 / 监控 ----------
    {"id": "docker", "name": "Docker", "cat": "系统", "pkg": "docker.io", "need": "docker",
     "icon": "box", "color": "#2496ed",
     "desc": "容器运行时，装应用商店里的容器", "size": "约 200MB"},
    {"id": "htop", "name": "htop", "cat": "系统", "pkg": "htop", "need": "htop",
     "icon": "layers", "color": "#0f7b5f",
     "desc": "彩色进程监控（SSH 里用）", "size": "约 1MB"},
    {"id": "tmux", "name": "tmux", "cat": "系统", "pkg": "tmux", "need": "tmux",
     "icon": "terminal", "color": "#2ecc8f",
     "desc": "终端复用，断开也不掉任务", "size": "约 1MB"},
    {"id": "glances", "name": "Glances", "cat": "系统", "pkg": "glances", "need": "glances",
     "icon": "eye", "color": "#0891b2",
     "desc": "轻量系统总览（SSH 里用）", "size": "约 8MB"},
    {"id": "netdata", "name": "Netdata", "cat": "系统", "pkg": "netdata", "need": "netdata",
     "icon": "chart", "color": "#0f7b5f",
     "desc": "实时性能监控面板（端口 19999，约 60MB，1GB 内存慎装）", "size": "约 60MB",
     "app": {"path": "http://{host}:19999", "port": 19999}},
    {"id": "cups", "name": "打印服务器", "cat": "系统", "pkg": "cups", "need": "cupsd",
     "icon": "file", "color": "#9ca3af",
     "desc": "USB 打印机变 AirPrint", "size": "约 30MB"},

    # ---------- 开发 ----------
    {"id": "git", "name": "Git", "cat": "开发", "pkg": "git", "need": "git",
     "icon": "git", "color": "#f1502f",
     "desc": "版本管理，拉取代码用", "size": "约 12MB"},
    {"id": "python3-pip", "name": "Python pip", "cat": "开发", "pkg": "python3-pip", "need": "pip3",
     "icon": "save", "color": "#3776ab",
     "desc": "Python 包管理", "size": "约 20MB"},
    {"id": "code-server", "name": "code-server", "cat": "开发", "kind": "docker",
     "container": "code-server", "image": "codercom/code-server:latest",
     "ports": "-p 8443:8443", "args": "-e PASSWORD=covernas -v /mnt/code:/home/coder/project",
     "need": "code-server", "icon": "terminal", "color": "#4f8cff",
     "desc": "浏览器里的 VS Code（端口 8443，密码 covernas，内存大户）", "size": "镜像约 300MB",
     "app": {"path": "http://{host}:8443", "port": 8443}},
    {"id": "node-red", "name": "Node-RED", "cat": "开发", "kind": "docker",
     "container": "node-red", "image": "nodered/node-red:latest",
     "ports": "-p 1880:1880", "args": "-v /mnt/node-red:/data",
     "need": "node-red", "icon": "node", "color": "#8f0000",
     "desc": "可视化流程编排（端口 1880）", "size": "镜像约 180MB",
     "app": {"path": "http://{host}:1880", "port": 1880}},

    # ---------- 网络 / 工具 ----------
    {"id": "mosquitto", "name": "Mosquitto", "cat": "网络", "pkg": "mosquitto", "need": "mosquitto",
     "icon": "node", "color": "#660066",
     "desc": "MQTT 消息代理，智能家居常用", "size": "约 3MB"},
    {"id": "ddns-go", "name": "DDNS-GO", "cat": "网络", "kind": "docker",
     "container": "ddns-go", "image": "jeessy/ddns-go:latest",
     "ports": "-p 9876:9876", "args": "-v /mnt/ddns-go:/root",
     "need": "ddns-go", "icon": "globe", "color": "#0891b2",
     "desc": "动态域名解析（端口 9876）", "size": "镜像约 20MB",
     "app": {"path": "http://{host}:9876", "port": 9876}},
    {"id": "portainer", "name": "Portainer", "cat": "容器", "kind": "docker",
     "container": "portainer", "image": "portainer/portainer-ce:latest",
     "ports": "-p 9009:9000",
     "args": "-v /var/run/docker.sock:/var/run/docker.sock -v /mnt/portainer:/data",
     "need": "portainer", "icon": "ship", "color": "#13bef9",
     "desc": "容器图形管理（端口 9009）", "size": "镜像约 100MB",
     "app": {"path": "http://{host}:9009", "port": 9009}},
    {"id": "uptime-kuma", "name": "Uptime Kuma", "cat": "容器", "kind": "docker",
     "container": "uptime-kuma", "image": "louislam/uptime-kuma:1",
     "ports": "-p 3001:3001", "args": "-v /mnt/uptime-kuma:/app/data",
     "need": "uptime-kuma", "icon": "pulse", "color": "#5cdd8b",
     "desc": "站点 / 服务可用性监控（端口 3001）", "size": "镜像约 200MB",
     "app": {"path": "http://{host}:3001", "port": 3001}},
    {"id": "vaultwarden", "name": "Vaultwarden", "cat": "工具", "kind": "docker",
     "container": "vaultwarden", "image": "vaultwarden/server:latest",
     "ports": "-p 8100:80", "args": "-v /mnt/vaultwarden:/data",
     "need": "vaultwarden", "icon": "lock", "color": "#4f8cff",
     "desc": "轻量密码管理（端口 8100，兼容 Bitwarden 客户端）", "size": "镜像约 60MB",
     "app": {"path": "http://{host}:8100", "port": 8100}},
    {"id": "memos", "name": "Memos", "cat": "工具", "kind": "docker",
     "container": "memos", "image": "neosmemo/memos:stable",
     "ports": "-p 5230:5230", "args": "-v /mnt/memos:/var/opt/memos",
     "need": "memos", "icon": "edit", "color": "#f5a524",
     "desc": "碎片化笔记（端口 5230，支持手机端）", "size": "镜像约 50MB",
     "app": {"path": "http://{host}:5230", "port": 5230}},

    # ---------- 内置（不进安装流程） ----------
    {"id": "alist", "name": "Alist", "cat": "已有", "pkg": "", "need": "/opt/alist/alist",
     "icon": "globe", "color": "#4f8cff",
     "desc": "网盘聚合（已安装，端口 5244）", "size": "已装"},
    {"id": "ariang", "name": "AriaNg", "cat": "已有", "pkg": "",
     "need": "/opt/box/web/ariang/index.html",
     "icon": "bolt", "color": "#2ecc8f",
     "desc": "Aria2 网页界面（已内置）", "size": "已装"},
]


PKG_OK = {}


# 商店安装状态缓存：一次 dpkg 全量 + 一次 docker ps，避免 30+ 次子进程拖慢页面
_DPKG_CACHE = {"ts": 0, "set": set()}
_DOCKER_CACHE = {"ts": 0, "names": set(), "running": set()}


def _dpkg_installed(pkg):
    now = time.time()
    if now - _DPKG_CACHE["ts"] > 60:
        out = run("dpkg-query -W -f='${Package} ${Status}\\n' 2>/dev/null", 15)
        names = set()
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 3 and "installed" in line:
                names.add(parts[0])
        _DPKG_CACHE["set"] = names
        _DPKG_CACHE["ts"] = now
    return pkg in _DPKG_CACHE["set"]


def _docker_state():
    now = time.time()
    if now - _DOCKER_CACHE["ts"] > 20:
        out = run("docker ps -a --format '{{.Names}}|{{.State}}' 2>/dev/null", 10)
        names, running = set(), set()
        for line in out.splitlines():
            if "|" in line:
                cn, st = line.split("|", 1)
                names.add(cn.strip())
                if st.strip().lower() == "running":
                    running.add(cn.strip())
        _DOCKER_CACHE["names"] = names
        _DOCKER_CACHE["running"] = running
        _DOCKER_CACHE["ts"] = now
    return _DOCKER_CACHE


def _invalidate_store_cache():
    _DPKG_CACHE["ts"] = 0
    _DOCKER_CACHE["ts"] = 0
    PKG_OK.clear()


def store_installed(item):
    """判断应用是否已安装。docker 类看容器（含已停止），apt 类看 dpkg/命令，内置看路径。"""
    need = item.get("need")
    if not need:
        return False
    if need.startswith("/"):
        return os.path.exists(need)
    if item.get("kind") == "docker":
        cname = item.get("container") or ""
        if not cname:
            return False
        return cname in _docker_state()["names"]
    if item.get("pkg"):
        if item["pkg"] not in PKG_OK:
            PKG_OK[item["pkg"]] = _dpkg_installed(item["pkg"])
        if PKG_OK[item["pkg"]]:
            return True
    return bool(shutil.which(need))


def store_install_cmd(item, act):
    """按类型生成安装/卸载命令：apt / docker / 内置不处理。"""
    kind = item.get("kind", "apt")
    if kind == "docker":
        cname = item["container"]
        if act != "install":
            return "docker rm -f %s" % cname
        return ('docker rm -f %s >/dev/null 2>&1; docker pull %s && '
                'docker run -d --name %s --restart=unless-stopped %s %s %s'
                % (cname, item["image"], cname, item.get("ports", ""),
                   item.get("args", ""), item["image"]))
    pkg = item.get("pkg") or ""
    return "DEBIAN_FRONTEND=noninteractive apt-get %s -y %s" % (
        "install" if act == "install" else "remove", pkg)


# ---------------------------------------------------------------- Samba
SMB_CONF = "/etc/samba/smb.conf"


def samba_shares():
    if not os.path.exists(SMB_CONF):
        return []
    out, cur, buf = [], None, {}
    try:
        with open(SMB_CONF, "r", errors="replace") as f:
            for line in f:
                s = line.strip()
                if s.startswith("[") and s.endswith("]"):
                    if cur and cur.lower() not in ("global", "printers", "print$"):
                        buf["name"] = cur
                        out.append(buf)
                    cur, buf = s[1:-1], {}
                elif cur and "=" in s and not s.startswith("#"):
                    k, v = s.split("=", 1)
                    buf[k.strip().lower()] = v.strip()
    except Exception:
        return []
    if cur and cur.lower() not in ("global", "printers", "print$"):
        buf["name"] = cur
        out.append(buf)
    res = []
    for b in out:
        res.append({"name": b.get("name", ""),
                    "path": b.get("path", ""),
                    "writable": b.get("read only", "no").lower() in ("no", "false"),
                    "guest": b.get("guest ok", "no").lower() in ("yes", "true"),
                    "comment": b.get("comment", "")})
    return res


def samba_write(shares):
    """按结构化数据重写 smb.conf 的共享段（保留 global）"""
    head = []
    try:
        with open(SMB_CONF, "r", errors="replace") as f:
            for line in f:
                if line.strip().startswith("[") and not line.strip().startswith("[global]"):
                    break
                head.append(line)
    except Exception:
        head = ["[global]\n", "   workgroup = WORKGROUP\n", "   server string = Box\n",
                "   map to guest = bad user\n", "   security = user\n"]
    body = []
    for s in shares:
        body.append("\n[%s]\n" % s["name"])
        body.append("   comment = %s\n" % (s.get("comment") or s["name"]))
        body.append("   path = %s\n" % s["path"])
        body.append("   browseable = yes\n")
        body.append("   read only = %s\n" % ("no" if s.get("writable") else "yes"))
        body.append("   guest ok = %s\n" % ("yes" if s.get("guest") else "no"))
        body.append("   create mask = 0664\n   directory mask = 0775\n")
    with open(SMB_CONF, "w") as f:
        f.write("".join(head) + "".join(body))
    run("systemctl reload smbd 2>/dev/null || systemctl restart smbd 2>/dev/null", 15)


# ---------------------------------------------------------------- 备份任务
BACKUP_FILE = os.path.join(DATA_DIR, "backups.json")


def load_backups():
    try:
        with open(BACKUP_FILE) as f:
            return json.load(f).get("tasks", [])
    except Exception:
        return []


def save_backups(tasks):
    ensure_data_dir()
    with open(BACKUP_FILE, "w") as f:
        json.dump({"tasks": tasks}, f, ensure_ascii=False)
    os.chmod(BACKUP_FILE, 0o600)


BACKUP_LAST = os.path.join(DATA_DIR, "backups-last.json")


def load_backup_last():
    try:
        with open(BACKUP_LAST) as f:
            return json.load(f)
    except Exception:
        return {}


# ---------------------------------------------------------------- 建站
SITES_ROOT = "/mnt/www"
NGX_AVAIL = "/etc/nginx/sites-available"
NGX_ENABLED = "/etc/nginx/sites-enabled"


def list_sites():
    out = []
    if not os.path.isdir(SITES_ROOT):
        return out
    for name in sorted(os.listdir(SITES_ROOT)):
        d = os.path.join(SITES_ROOT, name)
        if not os.path.isdir(d):
            continue
        conf = os.path.join(NGX_AVAIL, "box-%s.conf" % name)
        port = ""
        if os.path.exists(conf):
            try:
                with open(conf) as f:
                    m = re.search(r"listen\s+(\d+)", f.read())
                    port = m.group(1) if m else ""
            except Exception:
                pass
        out.append({"name": name, "dir": d, "port": port,
                    "enabled": os.path.exists(os.path.join(NGX_ENABLED, "box-%s.conf" % name)),
                    "files": len(os.listdir(d)) if os.path.isdir(d) else 0})
    return out


def free_port(start=8081):
    import socket as _s
    for p in range(start, start + 80):
        s = _s.socket()
        try:
            s.bind(("127.0.0.1", p))
            return p
        except OSError:
            continue
        finally:
            s.close()
    return start


SITE_CONF = """server {
    listen %(port)s;
    server_name _;
    root %(root)s;
    index index.html;
    client_max_body_size 0;
    location / {
        try_files $uri $uri/ /index.html;
    }
}
"""

SITE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%(name)s</title>
<style>
  html,body{height:100%%;margin:0}
  body{display:flex;align-items:center;justify-content:center;
       font-family:-apple-system,"PingFang SC",sans-serif;background:#f6f7f6;color:#1c1f1e}
  .c{text-align:center}
  h1{font-size:22px;margin:0 0 8px}
  p{color:#6b7672;font-size:13px;margin:0}
</style>
</head>
<body><div class="c"><h1>%(name)s 已上线</h1>
<p>把网页文件放进这个站点的目录就能替换这一页。</p></div></body>
</html>
"""


def write_ddns_script(cfg):
    """生成 Cloudflare DDNS 脚本并挂进 crontab（每 5 分钟）"""
    script = """#!/bin/bash
# Box 自动生成的 DDNS 脚本（Cloudflare）
DOMAIN="%(domain)s"
TOKEN="%(token)s"
IP=$(curl -s --max-time 8 https://api.ipify.org)
[ -z "$IP" ] && exit 1
ZONE=$(echo "$DOMAIN" | awk -F. '{print $(NF-1)"."$NF}')
ZID=$(curl -s -H "Authorization: Bearer $TOKEN" \\
  "https://api.cloudflare.com/client/v4/zones?name=$ZONE" \\
  | sed -n 's/.*"id":"\\([a-f0-9]*\\)".*/\\1/p' | head -1)
[ -z "$ZID" ] && exit 1
RID=$(curl -s -H "Authorization: Bearer $TOKEN" \\
  "https://api.cloudflare.com/client/v4/zones/$ZID/dns_records?name=$DOMAIN" \\
  | sed -n 's/.*"id":"\\([a-f0-9]*\\)".*/\\1/p' | head -1)
curl -s -X PUT -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \\
  --data "{\\"type\\":\\"A\\",\\"name\\":\\"$DOMAIN\\",\\"content\\":\\"$IP\\",\\"ttl\\":120,\\"proxied\\":false}" \\
  "https://api.cloudflare.com/client/v4/zones/$ZID/dns_records/$RID" > /dev/null
echo "$(date) -> $IP"
""" % cfg
    path = "/usr/local/sbin/box-ddns"
    with open(path, "w") as f:
        f.write(script)
    os.chmod(path, 0o700)
    cur = run("crontab -l 2>/dev/null")
    lines = [l for l in cur.split("\n") if l.strip() and "box-ddns" not in l]
    lines.append("*/5 * * * * /usr/local/sbin/box-ddns >> /var/log/box-ddns.log 2>&1")
    p = subprocess.Popen(["crontab", "-"], stdin=subprocess.PIPE,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    p.communicate(("\n".join(lines) + "\n").encode())
    return path



# ---------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "Box/0.1"
    protocol_version = "HTTP/1.1"

    # ---- 响应helper
    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _html(self, text, code=200):
        body = text.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, text, code=200):
        data = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _page(self, name):
        fp = os.path.join(WEB_DIR, name)
        try:
            with open(fp, "r", encoding="utf-8") as f:
                html_text = f.read()
        except Exception:
            return self._json({"ok": False, "err": "not found"}, 404)
        data = html_text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _file(self, path, ctype, cache=False):
        try:
            with open(path, "rb") as f:
                data = f.read()
        except Exception:
            self._json({"ok": False, "err": "not found"}, 404)
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        if cache:
            self.send_header("Cache-Control", "public, max-age=604800")
        self.end_headers()
        self.wfile.write(data)

    def _cookie_token(self):
        raw = self.headers.get("Cookie", "")
        for part in raw.split(";"):
            if "=" in part:
                k, v = part.strip().split("=", 1)
                if k == "box_sess":
                    return v
        return None

    def _authed(self):
        return session_ok(self._cookie_token())

    def _audit(self, event, detail=""):
        try:
            ip = self.client_address[0] if self.client_address else ""
        except Exception:
            ip = ""
        info = session_info(self._cookie_token()) or {}
        audit(event, detail, ip=ip, user=info.get("user") or "admin")

    # ---- DDNS 配置
    DDNS_FILE = os.path.join(DATA_DIR, "ddns.json")

    def _load_ddns(self):
        try:
            with open(self.DDNS_FILE) as f:
                return json.load(f)
        except Exception:
            return {"domain": "", "token": "", "enabled": False}

    def _save_ddns(self, cfg):
        ensure_data_dir()
        with open(self.DDNS_FILE, "w") as f:
            json.dump(cfg, f, ensure_ascii=False)
        os.chmod(self.DDNS_FILE, 0o600)

    def log_message(self, fmt, *args):
        pass

    # ---- 路由
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        p = u.path

        if p == "/api/login":
            return self._json({"ok": True, "authed": self._authed(), "init": has_password()})

        if p == "/api/me":
            info = session_info(self._cookie_token()) or {}
            return self._json({"ok": True, "user": info.get("user", ""),
                               "role": info.get("role", ""), "users": len(load_users())})

        if p == "/api/users":
            info = session_info(self._cookie_token()) or {}
            if info.get("role") != "admin":
                return self._json({"ok": False, "err": "只有管理员能查看账号"}, 403)
            users = [{"name": u.get("name"), "role": u.get("role", "viewer"),
                      "created": u.get("created", 0)} for u in load_users()]
            return self._json({"ok": True, "users": users, "me": info.get("user")})

        if p == "/api/recovery-info":
            # 触发生成恢复码（若尚未生成）
            _rk = recovery_key()
            return self._json({"ok": True, "has_password": has_password(),
                               "recovery_file": "/etc/box/recovery-key",
                               "generated": bool(_rk)})

        # ---- 免登录：登录页壁纸（只返回壁纸本身，无其他信息）
        if p == "/api/login-wall":
            ui = load_ui()
            wf = wall_file()
            if ui.get("wall") == "custom" and wf:
                return self._json({"ok": True, "kind": "img",
                                   "url": "/api/login-wall?img=1&v=%d" % int(os.path.getmtime(os.path.join(WALL_DIR, wf)))})
            w = None
            if ui.get("wall", "").startswith("preset:"):
                w = wall_by_id(ui["wall"].split(":", 1)[1])
            if w is None:  # default / random / 未知 → 给一张标志性的
                import random as _rnd
                w = _rnd.choice(WALLS) if ui.get("wall") == "random" else wall_by_id("aurora")
            return self._json({"ok": True, "kind": "css", "css": w["css"],
                               "size": w.get("size", "")})
        if p == "/api/wallpaper" and q.get("img"):
            wf = wall_file()
            if not wf:
                return self._json({"ok": False, "err": "没有自定义壁纸"}, 404)
            fp = os.path.join(WALL_DIR, wf)
            ctype = MIME.get(os.path.splitext(wf)[1].lower(), "image/jpeg")
            return self._file(fp, ctype, cache=True)

        if p.startswith("/api/") and not self._authed():
            return self._json({"ok": False, "err": "未登录", "login": True,
                               "init": has_password()}, 401)

        # ---- 全局搜索（文件 / 笔记 / 应用）
        if p == "/api/search":
            qq = (q.get("q", [""])[0] or "").strip()
            ql = qq.lower()
            notes_hits = []
            apps_hits = []
            if ql:
                for n in load_notes():
                    blob = (str(n.get("title", "")) + " " + str(n.get("body", ""))).lower()
                    if ql in blob:
                        notes_hits.append({"id": n.get("id"), "title": n.get("title", "无标题"),
                                           "snippet": str(n.get("body", ""))[:90]})
                for a in APPS:
                    if ql in a["name"].lower() or ql in a["desc"].lower() or ql in a["id"]:
                        apps_hits.append({"id": a["id"], "name": a["name"],
                                          "desc": a["desc"], "path": a["path"]})
            files_hits = search_files(qq, 60) if ql else []
            return self._json({"ok": True, "q": qq, "files": files_hits,
                               "notes": notes_hits[:20], "apps": apps_hits[:12]})

        # ---- 操作审计
        if p == "/api/audit":
            try:
                lim = int(q.get("limit", ["200"])[0] or 200)
            except ValueError:
                lim = 200
            lim = max(1, min(lim, 1000))
            ev = (q.get("event", [""])[0] or "").strip()
            kw = (q.get("q", [""])[0] or "").strip()
            return self._json({"ok": True, "items": read_audit(lim, ev, kw),
                               "stat": audit_stat()})

        # ---- 配置导出（下载 tar.gz）
        if p == "/api/config/export":
            try:
                data, cnt = export_config_bytes()
            except Exception as e:
                return self._json({"ok": False, "err": "导出失败：%s" % e}, 500)
            self._audit("配置导出", "files=%d bytes=%d" % (cnt, len(data)))
            self.send_response(200)
            self.send_header("Content-Type", "application/gzip")
            self.send_header("Content-Length", str(len(data)))
            fname = "covernas-config-%s.tar.gz" % time.strftime("%Y%m%d-%H%M")
            self.send_header("Content-Disposition", 'attachment; filename="%s"' % fname)
            self.end_headers()
            self.wfile.write(data)
            return

        if p in ("/", "/index.html"):
            if not self._authed():
                return self._file(os.path.join(WEB_DIR, "login.html"), "text/html; charset=utf-8")
            return self._file(os.path.join(WEB_DIR, "index.html"), "text/html; charset=utf-8")

        if p == "/api/status":
            mi = meminfo()
            total = mi.get("MemTotal", 0)
            avail = mi.get("MemAvailable", 0)
            used = max(0, total - avail)
            swap_t = mi.get("SwapTotal", 0)
            swap_f = mi.get("SwapFree", 0)
            load = read("/proc/loadavg", "0 0 0").split()
            up = int(float(read("/proc/uptime", "0").split()[0] or 0))
            return self._json({
                "ok": True,
                "host": {"name": socket.gethostname(), "uptime": up,
                         "kernel": os.uname().release, "ip": run("hostname -I | awk '{print $1}'")},
                "cpu": {"pct": round(cpu_pct(), 1), "load": [float(x) for x in load[:3]],
                        "cores": os.cpu_count() or 4},
                "mem": {"total": total, "used": used,
                        "pct": round(used * 100.0 / total, 1) if total else 0,
                        "swap_total": swap_t,
                        "swap_pct": round((swap_t - swap_f) * 100.0 / swap_t, 1) if swap_t else 0},
                "disk": disk_of("/"),
                "mnt": disk_of("/mnt") if os.path.isdir("/mnt") else None,
                "temp": temp_c(),
                "net": net_rate(),
                "net_io": {"rx": human(int(read("/sys/class/net/eth0/statistics/rx_bytes", "0") or 0)),
                           "tx": human(int(read("/sys/class/net/eth0/statistics/tx_bytes", "0") or 0))},
            })

        if p == "/api/apps":
            host = self.headers.get("Host", "").split(":")[0]
            out = []
            for a in APPS:
                d = dict(a)
                d["path"] = a["path"].replace("{host}", host)
                d["online"] = port_open(a["port"]) if a["port"] else True
                out.append(d)
            # 商店里已安装、且声明了入口的应用也上桌面
            try:
                for it in STORE:
                    app = it.get("app")
                    if not app or not store_installed(it):
                        continue
                    port = app.get("port", 0)
                    out.append({"id": "store-" + it["id"], "name": it["name"],
                                "icon": it.get("icon", "box"), "desc": it.get("desc", ""),
                                "path": app["path"].replace("{host}", host),
                                "port": port, "color": it.get("color", "#0f7b5f"),
                                "online": port_open(port) if port else True})
            except Exception:
                pass
            return self._json({"ok": True, "apps": out})

        if p == "/api/files":
            try:
                target = q.get("path", ["/"])[0]
                if q.get("trash"):
                    target = TRASH_DIR
                    os.makedirs(TRASH_DIR, exist_ok=True)
                return self._json({"ok": True, **list_dir(target)})
            except Exception as e:
                return self._json({"ok": False, "err": str(e)}, 400)

        if p == "/api/download":
            try:
                fp = safe_path(q.get("path", ["/"])[0])
            except Exception as e:
                return self._json({"ok": False, "err": str(e)}, 400)
            if not os.path.isfile(fp):
                return self._json({"ok": False, "err": "不是文件"}, 400)
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(os.path.getsize(fp)))
            self.send_header("Content-Disposition",
                             "attachment; filename*=UTF-8''%s" % urllib.parse.quote(os.path.basename(fp)))
            self.end_headers()
            with open(fp, "rb") as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
            return

        if p == "/api/services":
            out = []
            for unit, meta in SERVICES.items():
                out.append({"unit": unit, "name": meta["name"], "desc": meta["desc"],
                            "state": service_state(unit)})
            return self._json({"ok": True, "services": out})

        if p == "/api/storage":
            rows = []
            for line in run("df -kP 2>/dev/null").split("\n")[1:]:
                f = line.split()
                if len(f) >= 6 and f[0].startswith("/dev/"):
                    rows.append({"dev": f[0], "total": int(f[1]) * 1024,
                                 "used": int(f[2]) * 1024, "free": int(f[3]) * 1024,
                                 "pct": int(f[4].rstrip("%")), "mount": f[5]})
            return self._json({"ok": True, "mounts": rows, "lsblk": run("lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT 2>/dev/null")})

        if p == "/api/raw":
            # 流式输出，支持 Range（视频/音频拖动进度必需）
            try:
                fp = safe_path(q.get("path", [""])[0])
            except Exception as e:
                return self._json({"ok": False, "err": str(e)}, 400)
            if not os.path.isfile(fp):
                return self._json({"ok": False, "err": "不是文件"}, 404)
            size = os.path.getsize(fp)
            ctype = MIME.get(os.path.splitext(fp)[1].lower(), "application/octet-stream")
            rng = self.headers.get("Range", "")
            start, end = 0, size - 1
            partial = False
            m = re.match(r"bytes=(\d*)-(\d*)", rng or "")
            if m and (m.group(1) or m.group(2)):
                if m.group(1):
                    start = int(m.group(1))
                    end = int(m.group(2)) if m.group(2) else size - 1
                else:
                    start = max(0, size - int(m.group(2)))
                end = min(end, size - 1)
                if start > end:
                    start = 0
                partial = True
            length = end - start + 1
            self.send_response(206 if partial else 200)
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(length))
            if partial:
                self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
            self.end_headers()
            try:
                with open(fp, "rb") as f:
                    f.seek(start)
                    remain = length
                    while remain > 0:
                        chunk = f.read(min(65536, remain))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remain -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return

        if p == "/api/preview":
            try:
                fp = safe_path(q.get("path", [""])[0])
            except Exception as e:
                return self._json({"ok": False, "err": str(e)}, 400)
            if not os.path.isfile(fp):
                return self._json({"ok": False, "err": "不是文件"}, 404)
            ext = os.path.splitext(fp)[1].lower()
            if ext in IMG_EXT:
                return self._json({"ok": True, "kind": "image", "url": "/api/raw?path=" + urllib.parse.quote(fp)})
            if os.path.getsize(fp) > 2 * 1024 * 1024:
                return self._json({"ok": False, "err": "文件太大，无法预览"})
            try:
                with open(fp, "r", errors="replace") as f:
                    txt = f.read(65536)
                return self._json({"ok": True, "kind": "text", "text": txt})
            except Exception as e:
                return self._json({"ok": False, "err": str(e)})

        if p == "/api/logs":
            unit = q.get("unit", [""])[0]
            name = q.get("name", [""])[0]
            if unit and re.match(r"^[\w@.-]{1,64}$", unit):
                return self._json({"ok": True, "text": run("journalctl -u %s -n 80 --no-pager 2>&1" % unit, 12)})
            if name and re.match(r"^[\w][\w.-]{0,62}$", name):
                return self._json({"ok": True, "text": run("docker logs --tail 80 %s 2>&1" % name, 15)})
            return self._json({"ok": False, "err": "参数不对"}, 400)

        if p == "/api/photos":
            base = q.get("path", ["/mnt"])[0]
            sub = q.get("dir", [""])[0]
            album_id = q.get("album", [""])[0]
            items = scan_media(base, IMG_EXT)
            dirs = sorted({os.path.dirname(x["path"]) for x in items})
            if album_id:
                alb = next((a for a in load_albums() if a["id"] == album_id), None)
                keep = set(alb["items"]) if alb else set()
                items = [x for x in items if x["path"] in keep]
            elif sub:
                items = [x for x in items if x["path"].startswith(sub.rstrip("/") + "/")]
            return self._json({"ok": True, "items": items, "dirs": dirs,
                               "albums": load_albums()})

        if p == "/api/media":
            base = q.get("path", ["/mnt"])[0]
            sub = q.get("dir", [""])[0]
            video = scan_media(base, VIDEO_EXT)
            audio = scan_media(base, AUDIO_EXT)
            dirs = sorted({os.path.dirname(x["path"]) for x in video + audio})
            if sub:
                video = [x for x in video if x["path"].startswith(sub.rstrip("/") + "/")]
                audio = [x for x in audio if x["path"].startswith(sub.rstrip("/") + "/")]
            return self._json({"ok": True, "video": video, "audio": audio, "dirs": dirs})

        if p == "/api/albums":
            return self._json({"ok": True, "albums": load_albums()})

        if p == "/api/notes":
            return self._json({"ok": True, "notes": load_notes()})

        if p == "/api/cron":
            return self._json({"ok": True, "text": run("crontab -l 2>/dev/null")})

        if p == "/api/docker":
            out = run("docker ps -a --format '{{.Names}}|{{.Image}}|{{.State}}|{{.Status}}' 2>/dev/null")
            rows = []
            for line in out.split("\n"):
                if "|" in line:
                    n, img, st, stat = line.split("|", 3)
                    rows.append({"name": n, "image": img, "state": st, "status": stat})
            return self._json({"ok": True, "containers": rows,
                               "version": run("docker --version 2>/dev/null")})

        if p == "/api/store":
            items = []
            for it in STORE:
                row = dict(it)
                row["installed"] = store_installed(it)
                items.append(row)
            return self._json({"ok": True, "items": items})

        if p == "/api/job":
            jid = q.get("id", [""])[0]
            st = job_state(jid)
            if not st:
                return self._json({"ok": False, "err": "任务不存在"}, 404)
            return self._json(dict(ok=True, **st))

        if p == "/api/samba":
            running = service_state("smbd")
            return self._json({"ok": True, "shares": samba_shares(),
                               "users": smb_users(),
                               "installed": os.path.exists(SMB_CONF),
                               "state": running})

        if p == "/api/nfs":
            installed = bool(shutil.which("exportfs"))
            return self._json({"ok": True, "installed": installed,
                               "state": service_state("nfs-kernel-server") if installed else "not-installed",
                               "exports": nfs_exports()})

        if p == "/api/ftp":
            net = load_net()
            return self._json({"ok": True,
                               "installed": bool(shutil.which("vsftpd")),
                               "state": service_state("vsftpd"),
                               "root": net.get("ftp_root", "/mnt"),
                               "user": net.get("ftp_user", "share")})

        if p == "/api/webdav":
            net = load_net()
            return self._json({"ok": True,
                               "state": service_state("box-webdav"),
                               "installed": bool(shutil.which("rclone")),
                               "port": net.get("webdav_port", 8082),
                               "user": net.get("webdav_user", "webdav"),
                               "path": net.get("webdav_path", "/mnt")})

        if p == "/api/sysinfo":
            mi = meminfo()
            total = mi.get("MemTotal", 0)
            avail = mi.get("MemAvailable", 0)
            used = max(0, total - avail)
            osrel = read("/etc/os-release", "")
            pretty = ""
            m = re.search(r'PRETTY_NAME="([^"]+)"', osrel)
            if m:
                pretty = m.group(1)
            disks = []
            for d in ("/dev/mmcblk1", "/dev/sda", "/dev/sdb"):
                if os.path.exists(d):
                    disks.append(d)
            info = {
                "hostname": socket.gethostname(),
                "os": pretty or "Linux",
                "kernel": read("/proc/sys/kernel/osrelease", "").strip(),
                "arch": os.uname().machine,
                "cpu_cores": os.cpu_count() or 4,
                "cpu_model": _cpu_model(),
                "mem_total": total, "mem_used": used,
                "mem_total_h": human(total), "mem_used_h": human(used),
                "swap_total": mi.get("SwapTotal", 0),
                "swap_total_h": human(mi.get("SwapTotal", 0)),
                "uptime": int(float(read("/proc/uptime", "0 0").split()[0] or 0)),
                "disks": disks,
                "temp": temp_c(),
                "load": [float(x) for x in read("/proc/loadavg", "0 0 0").split()[:3]],
                "box_ver": "1.0.0",
                "ip": socket.gethostbyname(socket.gethostname()) or "",
            }
            return self._json({"ok": True, "info": info})

        if p == "/api/processes":
            return self._json({"ok": True, "items": proc_list(80)})

        if p == "/api/smart":
            dev = q.get("dev", ["/dev/mmcblk1"])[0]
            if not re.match(r"^/dev/[a-z0-9]{1,20}$", dev):
                return self._json({"ok": False, "err": "设备名不合法"}, 400)
            out = run("smartctl -a %s 2>&1 | head -40" % dev, 25)
            health = ""
            m = re.search(r"SMART overall-health self-assessment test result: (\w+)", out)
            if m:
                health = m.group(1)
            return self._json({"ok": True, "dev": dev, "health": health, "text": out})

        if p == "/api/shares":
            return self._json({"ok": True, "items": share_urls()})

        if p == "/api/backup":
            return self._json({"ok": True, "tasks": load_backups(),
                               "last": load_backup_last()})

        if p == "/api/site":
            return self._json({"ok": True, "sites": list_sites(),
                               "root": SITES_ROOT,
                               "nginx": service_state("nginx")})

        if p == "/api/remote":
            items = []
            ts_installed = bool(shutil.which("tailscale"))
            ts_state = service_state("tailscaled") if ts_installed else "not-installed"
            ts_ip = ""
            if ts_installed:
                ts_ip = run("tailscale ip -4 2>/dev/null | head -1", 6).strip()
            items.append({"id": "tailscale", "name": "Tailscale", "unit": "tailscaled",
                          "installed": ts_installed, "state": ts_state, "detail": ts_ip})
            frp_ok = os.path.exists("/etc/frp/frpc.ini") or bool(shutil.which("frpc"))
            items.append({"id": "frp", "name": "frp 内网穿透", "unit": "frpc",
                          "installed": frp_ok, "state": service_state("frpc") if frp_ok else "not-installed",
                          "detail": "/etc/frp/frpc.ini" if frp_ok else ""})
            zt_ok = bool(shutil.which("zerotier-one"))
            items.append({"id": "zerotier", "name": "ZeroTier", "unit": "zerotier-one",
                          "installed": zt_ok, "state": service_state("zerotier-one") if zt_ok else "not-installed",
                          "detail": ""})
            return self._json({"ok": True, "items": items,
                               "ddns": self._load_ddns()})

        if p == "/api/ui":
            d = load_ui()
            wf = wall_file()
            d["wall_url"] = ("/api/wallpaper?v=%d" % int(os.path.getmtime(os.path.join(WALL_DIR, wf)))) if wf else ""
            d["walls"] = WALLS
            return self._json({"ok": True, "ui": d})

        if p == "/api/wallpaper":
            preset = q.get("preset", [""])[0]
            if preset:
                try:
                    idx = int(preset) % len(WALL_PRESETS)
                except Exception:
                    idx = 0
                return self._json({"ok": True, "preset": idx,
                                   "gradient": WALL_PRESETS[idx]})
            wf = wall_file()
            if not wf:
                return self._json({"ok": False, "err": "没有自定义壁纸"}, 404)
            fp = os.path.join(WALL_DIR, wf)
            ext = os.path.splitext(wf)[1].lower()
            ctype = MIME.get(ext, "image/jpeg")
            return self._file(fp, ctype, cache=True)

        if p == "/api/trash":
            st = trash_stat()
            return self._json({"ok": True, "count": st["count"], "size": st["size"],
                               "size_h": human(st["size"]),
                               "path": TRASH_DIR})

        if p.startswith("/s/"):
            tok = p[3:].strip("/")
            item = load_shares().get(tok)
            if not item:
                return self._file(os.path.join(WEB_DIR, "login.html"), "text/html; charset=utf-8")
            fp = item.get("path", "")
            try:
                fp = safe_path(fp)
            except Exception:
                return self._json({"ok": False, "err": "路径不可用"}, 404)
            if os.path.isfile(fp):
                items = load_shares()
                items[tok]["downloads"] = items[tok].get("downloads", 0) + 1
                save_shares(items)
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Disposition",
                                 "attachment; filename*=UTF-8''%s" % urllib.parse.quote(os.path.basename(fp)))
                self.send_header("Content-Length", str(os.path.getsize(fp)))
                self.end_headers()
                with open(fp, "rb") as f:
                    shutil.copyfileobj(f, self.wfile)
                return
            if os.path.isdir(fp):
                rows = []
                for name in sorted(os.listdir(fp))[:500]:
                    full = os.path.join(fp, name)
                    size = human(os.path.getsize(full)) if os.path.isfile(full) else "—"
                    rows.append("<li><a href=\"/s/%s/%s\">%s</a><span>%s</span></li>" %
                                (tok, urllib.parse.quote(name), name, size))
                html_text = ("<!DOCTYPE html><meta charset=utf-8><title>%s</title>"
                             "<style>body{font:14px -apple-system,'PingFang SC',sans-serif;"
                             "max-width:720px;margin:40px auto;padding:0 18px;color:#16221c}"
                             "h2{font-size:16px}ul{list-style:none;padding:0}"
                             "li{display:flex;justify-content:space-between;padding:9px 0;"
                             "border-bottom:1px solid #eee}a{color:#0f7b5f;text-decoration:none}"
                             "span{color:#8a958f;font-size:12px}</style>"
                             "<h2>%s</h2><ul>%s</ul>") % (os.path.basename(fp), os.path.basename(fp), "".join(rows))
                return self._html(html_text)
            return self._json({"ok": False, "err": "文件不存在"}, 404)

        # AriaNg 静态资源（下载中心）
        if p.startswith("/ariang"):
            rel = p[len("/ariang"):].lstrip("/") or "index.html"
            fp = os.path.join(WEB_DIR, "ariang", os.path.normpath(rel))
            if not os.path.abspath(fp).startswith(os.path.join(WEB_DIR, "ariang")):
                return self._json({"ok": False}, 403)
            ext = os.path.splitext(fp)[1].lower()
            return self._file(fp, MIME.get(ext, "application/octet-stream"))

        # 静态资源
        if p.startswith("/static/"):
            fp = os.path.join(WEB_DIR, os.path.normpath(p[len("/static/"):]))
            if not os.path.abspath(fp).startswith(WEB_DIR):
                return self._json({"ok": False}, 403)
            CT = {".css": "text/css; charset=utf-8",
                  ".js": "application/javascript; charset=utf-8",
                  ".html": "text/html; charset=utf-8",
                  ".svg": "image/svg+xml",
                  ".png": "image/png",
                  ".ico": "image/x-icon",
                  ".json": "application/json",
                  ".webmanifest": "application/manifest+json",
                  ".gz": "application/gzip"}
            ext = os.path.splitext(fp)[1].lower()
            return self._file(fp, CT.get(ext, "application/octet-stream"))

        return self._json({"ok": False, "err": "not found"}, 404)

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        p = u.path
        length = int(self.headers.get("Content-Length") or 0)

        # 登录 / 初始化
        if p in ("/api/login", "/api/setup"):
            body = self.rfile.read(length).decode()
            data = urllib.parse.parse_qs(body)
            pw = (data.get("password") or [""])[0]
            uname = (data.get("username") or ["admin"])[0].strip() or "admin"
            _ip = self.client_address[0] if self.client_address else ""
            if p == "/api/setup":
                if has_password():
                    return self._json({"ok": False, "err": "已初始化"}, 400)
                if len(pw) < 8:
                    return self._json({"ok": False, "err": "至少 8 位"}, 400)
                save_password(pw)
                uname = "admin"
                audit("初始化", "创建管理员 admin", _ip)
            elif not verify_user(uname, pw):
                time.sleep(0.4)
                audit("登录失败", "user=%s 密码错误" % uname, _ip, user=uname)
                return self._json({"ok": False, "err": "用户名或密码错误"}, 401)
            _u = find_user(uname) or {}
            _role = _u.get("role", "admin")
            audit("登录成功", "user=%s role=%s" % (uname, _role), _ip, user=uname)
            tok = new_session(uname, _role)
            body = json.dumps({"ok": True}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Set-Cookie", "box_sess=%s; Path=/; HttpOnly; SameSite=Lax; Max-Age=604800" % tok)
            self.end_headers()
            self.wfile.write(body)
            return

        # 忘记密码：免登录重置（需恢复码）
        if p == "/api/recover":
            body = self.rfile.read(length).decode()
            data = urllib.parse.parse_qs(body)
            code = (data.get("code") or [""])[0].strip()
            newpw = (data.get("new") or [""])[0]
            if not hmac.compare_digest(code, recovery_key()):
                time.sleep(0.4)
                return self._json({"ok": False, "err": "恢复码不正确"}, 401)
            if len(newpw) < 8:
                return self._json({"ok": False, "err": "新密码至少 8 位"}, 400)
            reset_password(newpw)
            audit("密码重置", "通过恢复码", self.client_address[0] if self.client_address else "")
            return self._json({"ok": True, "msg": "密码已重置，请用新密码登录"})

        if not self._authed():
            return self._json({"ok": False, "err": "未登录", "login": True}, 401)

        # 操作审计：所有写接口统一留痕（细化动作的分支会再写一条更具体的）
        if p not in AUDIT_DETAILED_POST:
            self._audit("api", p.replace("/api/", ""))

        # 只读账号：除退出登录 / 改自己密码外，禁止一切写操作
        _sess = session_info(self._cookie_token()) or {}
        if _sess.get("role") != "admin" and p not in ("/api/logout", "/api/passwd"):
            return self._json({"ok": False, "err": "只读账号无权执行这个操作", "readonly": True}, 403)

        if p == "/api/logout":
            with _SESSION_LOCK:
                SESSIONS.pop(self._cookie_token(), None)
            self._audit("退出登录", "user=admin")
            body = json.dumps({"ok": True}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Set-Cookie", "box_sess=; Path=/; Max-Age=0")
            self.end_headers()
            self.wfile.write(body)
            return

        if p == "/api/users":
            data = urllib.parse.parse_qs(self.rfile.read(length).decode())
            act = (data.get("act") or [""])[0]
            name = (data.get("name") or [""])[0].strip()
            role = (data.get("role") or ["viewer"])[0]
            pw = (data.get("password") or [""])[0]
            info = session_info(self._cookie_token()) or {}
            try:
                if act == "add":
                    if not re.match(r"^[A-Za-z0-9_-]{2,20}$", name):
                        raise ValueError("用户名 2-20 位，仅字母数字下划线横线")
                    if len(pw) < 8:
                        raise ValueError("密码至少 8 位")
                    add_user(name, pw, role)
                elif act == "del":
                    if name == (info.get("user") or ""):
                        raise ValueError("不能删除当前登录的账号")
                    del_user(name)
                elif act == "passwd":
                    if len(pw) < 8:
                        raise ValueError("密码至少 8 位")
                    if not set_user_password(name, pw):
                        raise ValueError("用户不存在")
                elif act == "role":
                    set_user_role(name, role)
                else:
                    raise ValueError("未知操作")
            except ValueError as e:
                return self._json({"ok": False, "err": str(e)}, 400)
            self._audit("账号管理", "%s %s %s" % (act, name, role or "-"))
            return self._json({"ok": True})

        if p == "/api/config/import":
            ctype = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in ctype:
                return self._json({"ok": False, "err": "需要 multipart"}, 400)
            fs = cgi.FieldStorage(fp=self.rfile, headers=self.headers,
                                  environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": ctype})
            f = fs["file"] if "file" in fs else None
            if not f or not getattr(f, "filename", None):
                return self._json({"ok": False, "err": "没有收到文件"}, 400)
            raw = f.file.read(8 * 1024 * 1024 + 1)
            if len(raw) > 8 * 1024 * 1024:
                return self._json({"ok": False, "err": "配置文件不能超过 8MB"}, 400)
            try:
                applied = import_config_bytes(raw)
            except Exception as e:
                return self._json({"ok": False, "err": "配置包无法解析：%s" % e}, 400)
            if not applied:
                return self._json({"ok": False, "err": "配置包里没有可恢复的内容"}, 400)
            run("systemctl daemon-reload", 6)
            run("exportfs -ra", 6)
            run("systemctl reload smbd", 8)
            run("nginx -t && systemctl reload nginx", 8)
            run("systemctl restart box-webdav", 8)
            self._audit("配置恢复", "files=%d" % len(applied))
            return self._json({"ok": True, "applied": applied, "count": len(applied)})

        if p == "/api/mkdir":
            data = urllib.parse.parse_qs(self.rfile.read(length).decode())
            try:
                d = require_writable(safe_path((data.get("path") or [""])[0]))
                name = (data.get("name") or [""])[0].strip()
                if not name or "/" in name:
                    raise ValueError("名称不合法")
                os.makedirs(os.path.join(d, name), exist_ok=False)
                return self._json({"ok": True})
            except Exception as e:
                return self._json({"ok": False, "err": str(e)}, 400)

        if p == "/api/delete":
            data = urllib.parse.parse_qs(self.rfile.read(length).decode())
            try:
                paths = data.get("path") or []
                moved = []
                for one in paths:
                    moved.append(move_to_trash(one))
                self._audit("删除文件", ", ".join(os.path.basename(str(x)) for x in moved[:8]))
                return self._json({"ok": True, "moved": moved})
            except Exception as e:
                return self._json({"ok": False, "err": str(e)}, 400)

        if p == "/api/rename":
            data = urllib.parse.parse_qs(self.rfile.read(length).decode())
            try:
                src = require_writable(safe_path((data.get("path") or [""])[0]))
                name = (data.get("name") or [""])[0].strip()
                if not name or "/" in name:
                    raise ValueError("名称不合法")
                os.rename(src, os.path.join(os.path.dirname(src), name))
                return self._json({"ok": True})
            except Exception as e:
                return self._json({"ok": False, "err": str(e)}, 400)

        if p == "/api/service":
            data = urllib.parse.parse_qs(self.rfile.read(length).decode())
            unit = (data.get("unit") or [""])[0]
            op = (data.get("op") or [""])[0]
            if unit not in SERVICES or op not in ("start", "stop", "restart"):
                return self._json({"ok": False, "err": "不允许"}, 400)
            run("systemctl %s %s" % (op, unit))
            self._audit("服务操作", "%s %s" % (op, unit))
            time.sleep(0.6)
            return self._json({"ok": True, "state": service_state(unit)})

        if p == "/api/upload":
            ctype = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in ctype:
                return self._json({"ok": False, "err": "需要 multipart"}, 400)
            fs = cgi.FieldStorage(fp=self.rfile, headers=self.headers,
                                  environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": ctype})
            dest_dir = require_writable(safe_path(fs.getvalue("path") or "/"))
            saved = []
            files = fs["files"] if "files" in fs else []
            if not isinstance(files, list):
                files = [files]
            for f in files:
                if not getattr(f, "filename", None):
                    continue
                name = os.path.basename(f.filename)
                target = os.path.join(dest_dir, name)
                with open(target, "wb") as out:
                    while True:
                        chunk = f.file.read(65536)
                        if not chunk:
                            break
                        out.write(chunk)
                saved.append(name)
            self._audit("上传文件", "%d 个 -> %s" % (len(saved), dest_dir))
            return self._json({"ok": True, "saved": saved})

        if p == "/api/notes":
            data = urllib.parse.parse_qs(self.rfile.read(length).decode())
            act = (data.get("act") or ["save"])[0]
            notes = load_notes()
            nid = (data.get("id") or [""])[0]
            if act == "delete":
                notes = [n for n in notes if n.get("id") != nid]
                save_notes(notes)
                return self._json({"ok": True})
            title = (data.get("title") or ["未命名"])[0][:80]
            body = (data.get("body") or [""])[0][:20000]
            if not nid:
                nid = secrets.token_hex(4)
                notes.insert(0, {"id": nid, "title": title, "body": body, "updated": int(time.time())})
            else:
                for n in notes:
                    if n.get("id") == nid:
                        n.update({"title": title, "body": body, "updated": int(time.time())})
                        break
            save_notes(notes)
            return self._json({"ok": True, "id": nid})

        if p == "/api/cron":
            data = urllib.parse.parse_qs(self.rfile.read(length).decode())
            text = (data.get("text") or [""])[0]
            tmp = "/tmp/box-cron-%d" % os.getpid()
            with open(tmp, "w") as f:
                f.write(text.rstrip("\n") + "\n")
            out = run("crontab %s 2>&1" % tmp)
            try:
                os.unlink(tmp)
            except Exception:
                pass
            return self._json({"ok": out == "", "err": out})

        if p == "/api/docker":
            data = urllib.parse.parse_qs(self.rfile.read(length).decode())
            name = (data.get("name") or [""])[0]
            op = (data.get("op") or [""])[0]
            if not re.match(r"^[\w][\w.-]{0,62}$", name):
                return self._json({"ok": False, "err": "容器名不合法"}, 400)
            if op not in ("start", "stop", "restart"):
                return self._json({"ok": False, "err": "不允许的操作"}, 400)
            out = run("docker %s %s 2>&1" % (op, name))
            self._audit("容器操作", "%s %s" % (op, name))
            return self._json({"ok": out == "", "err": out})

        if p == "/api/file/new":
            data = urllib.parse.parse_qs(self.rfile.read(length).decode())
            try:
                d = require_writable(safe_path((data.get("path") or [""])[0]))
                name = (data.get("name") or [""])[0].strip()
                if not name or "/" in name:
                    raise ValueError("名称不合法")
                target = os.path.join(d, name)
                if os.path.exists(target):
                    raise ValueError("同名文件已存在")
                open(target, "w").close()
                return self._json({"ok": True})
            except Exception as e:
                return self._json({"ok": False, "err": str(e)}, 400)

        if p == "/api/files/move":
            data = urllib.parse.parse_qs(self.rfile.read(length).decode())
            try:
                dst = require_writable(safe_path((data.get("dst") or ["/"])[0]))
                mode = (data.get("mode") or ["move"])[0]
                srcs = data.get("src") or []
                if not os.path.isdir(dst):
                    raise ValueError("目标不是目录")
                done = []
                for s in srcs:
                    sp = safe_path(s)
                    if mode != "copy":
                        require_writable(sp)
                    if sp == dst or dst.startswith(sp.rstrip("/") + "/"):
                        raise ValueError("不能移动到自身或子目录")
                    target = os.path.join(dst, os.path.basename(sp))
                    if os.path.exists(target):
                        raise ValueError("目标已存在：" + os.path.basename(sp))
                    if mode == "copy":
                        if os.path.isdir(sp):
                            shutil.copytree(sp, target)
                        else:
                            shutil.copy2(sp, target)
                    else:
                        shutil.move(sp, target)
                    done.append(os.path.basename(sp))
                return self._json({"ok": True, "done": done})
            except Exception as e:
                return self._json({"ok": False, "err": str(e)}, 400)

        if p == "/api/service/enable":
            data = urllib.parse.parse_qs(self.rfile.read(length).decode())
            unit = (data.get("unit") or [""])[0]
            on = (data.get("on") or ["1"])[0] == "1"
            if unit not in SERVICES:
                return self._json({"ok": False, "err": "不允许"}, 400)
            run("systemctl %s %s" % ("enable" if on else "disable", unit), 20)
            return self._json({"ok": True})

        if p == "/api/docker/run":
            data = urllib.parse.parse_qs(self.rfile.read(length).decode())
            image = (data.get("image") or [""])[0].strip()
            name = (data.get("name") or [""])[0].strip()
            ports = (data.get("ports") or [""])[0].strip()
            vols = (data.get("volumes") or [""])[0].strip()
            envs = (data.get("envs") or [""])[0].strip()
            if not re.match(r"^[a-zA-Z0-9][\w./:@-]{0,120}$", image):
                return self._json({"ok": False, "err": "镜像名不合法"}, 400)
            if name and not re.match(r"^[\w][\w.-]{0,62}$", name):
                return self._json({"ok": False, "err": "容器名不合法"}, 400)
            cmd = ["docker", "run", "-d"]
            if name:
                cmd += ["--name", name]
            cmd += ["--restart", "unless-stopped"]
            for pv in [x.strip() for x in ports.split(",") if x.strip()]:
                if not re.match(r"^[0-9:\-/]+$", pv):
                    return self._json({"ok": False, "err": "端口格式不对"}, 400)
                cmd += ["-p", pv]
            for v in [x.strip() for x in vols.split(",") if x.strip()]:
                cmd += ["-v", v]
            for e in [x.strip() for x in envs.split(",") if x.strip()]:
                if "=" not in e:
                    return self._json({"ok": False, "err": "环境变量要写成 KEY=VALUE"}, 400)
                cmd += ["-e", e]
            cmd.append(image)
            jid = start_job("启动容器 " + (name or image), " ".join(cmd))
            return self._json({"ok": True, "job": jid})

        if p == "/api/docker/remove":
            data = urllib.parse.parse_qs(self.rfile.read(length).decode())
            name = (data.get("name") or [""])[0]
            force = (data.get("force") or ["0"])[0] == "1"
            if not re.match(r"^[\w][\w.-]{0,62}$", name):
                return self._json({"ok": False, "err": "容器名不合法"}, 400)
            out = run("docker rm %s %s 2>&1" % ("-f" if force else "", name), 30)
            return self._json({"ok": out == "", "err": out})

        # ---------------- SMB 用户 ----------------
        if p == "/api/smb/user":
            data = urllib.parse.parse_qs(self.rfile.read(length).decode())
            act = (data.get("act") or ["add"])[0]
            user = (data.get("user") or [""])[0].strip()
            pw = (data.get("password") or [""])[0]
            if not re.match(r"^[a-z_][a-z0-9_-]{0,20}$", user):
                return self._json({"ok": False, "err": "用户名只能小写字母数字下划线"}, 400)
            try:
                if act == "add":
                    if len(pw) < 4:
                        raise ValueError("密码至少 4 位")
                    run("id %s >/dev/null 2>&1 || useradd -M -s /usr/sbin/nologin %s" % (user, user), 10)
                    out = run("printf '%s\\n%s\\n' '%s' '%s' | smbpasswd -a -s %s 2>&1" %
                              (pw, pw, pw, pw, user), 20)
                    if "Added user" not in out and "password" not in out.lower():
                        pass
                    run("smbpasswd -e %s >/dev/null 2>&1" % user, 10)
                    return self._json({"ok": True, "users": smb_users()})
                if act == "del":
                    run("smbpasswd -x %s >/dev/null 2>&1" % user, 10)
                    return self._json({"ok": True, "users": smb_users()})
            except Exception as e:
                return self._json({"ok": False, "err": str(e)}, 400)

        # ---------------- NFS ----------------
        if p == "/api/nfs":
            data = urllib.parse.parse_qs(self.rfile.read(length).decode())
            act = (data.get("act") or [""])[0]
            if act == "install":
                jid = start_job("安装 NFS 服务",
                                "DEBIAN_FRONTEND=noninteractive apt-get install -y nfs-kernel-server")
                return self._json({"ok": True, "job": jid})
            try:
                lines = []
                try:
                    with open("/etc/exports") as f:
                        lines = [l.rstrip("\n") for l in f]
                except Exception:
                    lines = []
                if act == "add":
                    path = safe_path((data.get("path") or [""])[0])
                    clients = (data.get("clients") or ["*"])[0].strip()
                    ro = (data.get("ro") or ["0"])[0] == "1"
                    if not os.path.isdir(path):
                        raise ValueError("目录不存在")
                    if not re.match(r"^[0-9a-zA-Z.*/,-]+$", clients):
                        raise ValueError("客户端格式不对，例如 * 或 192.168.1.0/24")
                    opts = "ro,sync,no_subtree_check" if ro else "rw,sync,no_subtree_check"
                    lines = [l for l in lines if not l.startswith(path + " ")]
                    lines.append("%s %s(%s)" % (path, clients, opts))
                elif act == "delete":
                    path = (data.get("path") or [""])[0]
                    lines = [l for l in lines if not l.startswith(path + " ")]
                elif act != "add":
                    return self._json({"ok": False, "err": "未知操作"}, 400)
                with open("/etc/exports", "w") as f:
                    f.write("\n".join([l for l in lines if l.strip()]) + "\n")
                run("exportfs -ra 2>&1 || systemctl restart nfs-kernel-server 2>&1", 20)
                return self._json({"ok": True, "exports": nfs_exports()})
            except Exception as e:
                return self._json({"ok": False, "err": str(e)}, 400)

        # ---------------- FTP ----------------
        if p == "/api/ftp":
            data = urllib.parse.parse_qs(self.rfile.read(length).decode())
            act = (data.get("act") or [""])[0]
            if act == "install":
                jid = start_job("安装 FTP 服务", "DEBIAN_FRONTEND=noninteractive apt-get install -y vsftpd")
                return self._json({"ok": True, "job": jid})
            try:
                if act == "save":
                    root = safe_path((data.get("root") or ["/mnt"])[0])
                    user = (data.get("user") or ["share"])[0].strip()
                    pw = (data.get("password") or [""])[0]
                    if not os.path.isdir(root):
                        raise ValueError("目录不存在")
                    if not re.match(r"^[a-z_][a-z0-9_-]{0,20}$", user):
                        raise ValueError("用户名不合法")
                    run("id %s >/dev/null 2>&1 || useradd -M -d %s -s /bin/bash %s" % (user, root, user), 10)
                    if pw:
                        if len(pw) < 4:
                            raise ValueError("密码至少 4 位")
                        p2 = subprocess.Popen(["chpasswd"], stdin=subprocess.PIPE,
                                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        p2.communicate(("%s:%s\n" % (user, pw)).encode())
                    with open("/etc/vsftpd.conf", "w") as f:
                        f.write(ftp_conf(root))
                    save_net({"ftp_root": root, "ftp_user": user})
                    run("systemctl enable vsftpd 2>/dev/null; systemctl restart vsftpd 2>&1", 25)
                    time.sleep(0.6)
                    return self._json({"ok": True, "state": service_state("vsftpd")})
                if act in ("start", "stop", "restart"):
                    if not shutil.which("vsftpd"):
                        raise ValueError("还没安装 vsftpd，先点安装")
                    run("systemctl %s vsftpd 2>&1" % act, 20)
                    time.sleep(0.5)
                    return self._json({"ok": True, "state": service_state("vsftpd")})
            except Exception as e:
                return self._json({"ok": False, "err": str(e)}, 400)

        # ---------------- WebDAV ----------------
        if p == "/api/webdav":
            data = urllib.parse.parse_qs(self.rfile.read(length).decode())
            act = (data.get("act") or [""])[0]
            try:
                if act == "save":
                    path = safe_path((data.get("path") or ["/mnt"])[0])
                    user = (data.get("user") or ["webdav"])[0].strip()
                    pw = (data.get("password") or [""])[0]
                    port = (data.get("port") or ["8082"])[0]
                    if not os.path.isdir(path):
                        raise ValueError("目录不存在")
                    if not re.match(r"^[a-zA-Z0-9_-]{2,20}$", user):
                        raise ValueError("用户名不合法")
                    if len(pw) < 4:
                        raise ValueError("密码至少 4 位")
                    if not port.isdigit() or not (1024 < int(port) < 65535):
                        raise ValueError("端口不合法")
                    write_webdav({"path": path, "user": user, "pass": pw, "port": int(port)})
                    save_net({"webdav_path": path, "webdav_user": user, "webdav_port": int(port)})
                    run("systemctl restart box-webdav 2>&1", 25)
                    time.sleep(0.8)
                    return self._json({"ok": True, "state": service_state("box-webdav")})
                if act in ("start", "stop", "restart"):
                    run("systemctl %s box-webdav 2>&1" % act, 20)
                    time.sleep(0.5)
                    return self._json({"ok": True, "state": service_state("box-webdav")})
            except Exception as e:
                return self._json({"ok": False, "err": str(e)}, 400)

        # ---------------- 进程 ----------------
        if p == "/api/kill":
            data = urllib.parse.parse_qs(self.rfile.read(length).decode())
            pid = (data.get("pid") or [""])[0]
            sig = (data.get("sig") or ["15"])[0]
            if not pid.isdigit() or sig not in ("15", "9"):
                return self._json({"ok": False, "err": "参数不合法"}, 400)
            out = run("kill -%s %s 2>&1" % (sig, pid), 8)
            return self._json({"ok": out == "", "err": out.strip()})

        # ---------------- 维护 ----------------
        if p == "/api/maintenance":
            data = urllib.parse.parse_qs(self.rfile.read(length).decode())
            act = (data.get("act") or [""])[0]
            if act == "clean":
                jid = start_job("系统清理",
                                "apt-get clean; journalctl --vacuum-time=3d 2>/dev/null; "
                                "rm -rf /tmp/box-job-*.log /tmp/*.tgz 2>/dev/null; "
                                "echo '--- 清理后 ---'; df -h / | tail -1")
                return self._json({"ok": True, "job": jid})
            if act == "update":
                jid = start_job("系统更新",
                                "DEBIAN_FRONTEND=noninteractive apt-get update && "
                                "DEBIAN_FRONTEND=noninteractive apt-get upgrade -y")
                return self._json({"ok": True, "job": jid})
            if act == "diagnose":
                return self._json({"ok": True, "text": diagnose()})
            if act == "reboot":
                subprocess.Popen(["/bin/bash", "-c", "sleep 1; /sbin/reboot"], start_new_session=True)
                return self._json({"ok": True})
            if act == "shutdown":
                subprocess.Popen(["/bin/bash", "-c", "sleep 1; /sbin/poweroff"], start_new_session=True)
                return self._json({"ok": True})
            return self._json({"ok": False, "err": "未知操作"}, 400)

        # ---------------- 文件属性 / 压缩 / 解压 ----------------
        if p == "/api/file/stat":
            data = urllib.parse.parse_qs(self.rfile.read(length).decode())
            try:
                fp = safe_path((data.get("path") or [""])[0])
                st = os.stat(fp)
                import pwd as _pwd
                import grp as _grp
                try:
                    owner = _pwd.getpwuid(st.st_uid).pw_name
                except Exception:
                    owner = str(st.st_uid)
                try:
                    group = _grp.getgrgid(st.st_gid).gr_name
                except Exception:
                    group = str(st.st_gid)
                info = {"path": fp, "name": os.path.basename(fp) or "/",
                        "dir": os.path.isdir(fp), "size": st.st_size,
                        "size_h": human(st.st_size), "mode": oct(st.st_mode & 0o7777)[2:],
                        "owner": owner, "group": group,
                        "mtime": int(st.st_mtime),
                        "count": len(os.listdir(fp)) if os.path.isdir(fp) else 0}
                return self._json({"ok": True, "info": info})
            except Exception as e:
                return self._json({"ok": False, "err": str(e)}, 400)

        if p == "/api/file/chmod":
            data = urllib.parse.parse_qs(self.rfile.read(length).decode())
            fp = (data.get("path") or [""])[0]
            mode = (data.get("mode") or [""])[0]
            if not re.match(r"^[0-7]{3,4}$", mode):
                return self._json({"ok": False, "err": "权限要写成 755 这样"}, 400)
            try:
                os.chmod(require_writable(safe_path(fp)), int(mode, 8))
                return self._json({"ok": True})
            except Exception as e:
                return self._json({"ok": False, "err": str(e)}, 400)

        if p == "/api/file/compress":
            data = urllib.parse.parse_qs(self.rfile.read(length).decode())
            try:
                paths = [require_writable(safe_path(x)) for x in (data.get("path") or [])]
            except Exception as e:
                return self._json({"ok": False, "err": str(e)}, 400)
            fmt = (data.get("format") or ["zip"])[0]
            if not paths:
                return self._json({"ok": False, "err": "没选文件"}, 400)
            base = os.path.dirname(paths[0])
            name = (data.get("name") or [os.path.basename(base) or "archive"])[0].strip()[:60]
            name = re.sub(r"[^\w\u4e00-\u9fa5.-]", "_", name)
            names = " ".join("'%s'" % os.path.basename(x) for x in paths)
            if fmt == "tar":
                out = os.path.join(base, name + ".tar.gz")
                cmd = "cd '%s' && tar czf '%s' %s" % (base, os.path.basename(out), names)
            else:
                out = os.path.join(base, name + ".zip")
                cmd = "cd '%s' && zip -r -q '%s' %s" % (base, os.path.basename(out), names)
            jid = start_job("压缩 " + os.path.basename(out), cmd + " && echo '\n完成'")
            return self._json({"ok": True, "job": jid, "out": out})

        if p == "/api/file/extract":
            data = urllib.parse.parse_qs(self.rfile.read(length).decode())
            fp = (data.get("path") or [""])[0]
            try:
                fp = safe_path(fp)
                dest = os.path.dirname(fp)
                require_writable(dest)
                low = fp.lower()
                if low.endswith(".zip"):
                    cmd = "cd '%s' && unzip -o '%s' >/dev/null && echo 解压完成" % (dest, fp)
                elif low.endswith((".tar.gz", ".tgz")):
                    cmd = "cd '%s' && tar xzf '%s' && echo 解压完成" % (dest, fp)
                elif low.endswith(".tar"):
                    cmd = "cd '%s' && tar xf '%s' && echo 解压完成" % (dest, fp)
                elif low.endswith(".tar.bz2"):
                    cmd = "cd '%s' && tar xjf '%s' && echo 解压完成" % (dest, fp)
                else:
                    return self._json({"ok": False, "err": "只支持 zip / tar.gz / tar / tar.bz2"}, 400)
                jid = start_job("解压 " + os.path.basename(fp), cmd)
                return self._json({"ok": True, "job": jid})
            except Exception as e:
                return self._json({"ok": False, "err": str(e)}, 400)

        # ---------------- 分享链接 ----------------
        if p == "/api/shares":
            data = urllib.parse.parse_qs(self.rfile.read(length).decode())
            act = (data.get("act") or ["create"])[0]
            items = load_shares()
            try:
                if act == "create":
                    fp = safe_path((data.get("path") or [""])[0])
                    if not os.path.exists(fp):
                        raise ValueError("文件不存在")
                    tok = secrets.token_urlsafe(9).replace("-", "x")[:12]
                    items[tok] = {"path": fp, "created": int(time.time()), "downloads": 0}
                    save_shares(items)
                    return self._json({"ok": True, "token": tok, "items": share_urls()})
                if act == "delete":
                    tok = (data.get("token") or [""])[0]
                    items.pop(tok, None)
                    save_shares(items)
                    return self._json({"ok": True, "items": share_urls()})
            except Exception as e:
                return self._json({"ok": False, "err": str(e)}, 400)

        # ---------------- 相册 ----------------
        if p == "/api/albums":
            data = urllib.parse.parse_qs(self.rfile.read(length).decode())
            act = (data.get("act") or ["create"])[0]
            albums = load_albums()
            try:
                if act == "create":
                    name = (data.get("name") or [""])[0].strip()[:30]
                    if not name:
                        raise ValueError("相册名不能为空")
                    aid = "%d" % int(time.time() * 1000)
                    albums.append({"id": aid, "name": name, "items": [],
                                   "created": int(time.time())})
                    save_albums(albums)
                    return self._json({"ok": True, "albums": albums, "id": aid})
                if act == "delete":
                    aid = (data.get("id") or [""])[0]
                    albums = [a for a in albums if a["id"] != aid]
                    save_albums(albums)
                    return self._json({"ok": True, "albums": albums})
                if act == "rename":
                    aid = (data.get("id") or [""])[0]
                    name = (data.get("name") or [""])[0].strip()[:30]
                    for a in albums:
                        if a["id"] == aid and name:
                            a["name"] = name
                    save_albums(albums)
                    return self._json({"ok": True, "albums": albums})
                if act in ("add", "remove"):
                    aid = (data.get("id") or [""])[0]
                    paths = data.get("path") or []
                    for a in albums:
                        if a["id"] != aid:
                            continue
                        if act == "add":
                            for pth in paths:
                                if pth not in a["items"]:
                                    a["items"].append(pth)
                        else:
                            a["items"] = [x for x in a["items"] if x not in paths]
                    save_albums(albums)
                    return self._json({"ok": True, "albums": albums})
                return self._json({"ok": False, "err": "未知操作"}, 400)
            except Exception as e:
                return self._json({"ok": False, "err": str(e)}, 400)

        # ---------------- 忘记密码重置 ----------------
        if p == "/api/recover":
            # 已在 do_POST 顶部（免登录）处理，这里兜底返回
            return self._json({"ok": False, "err": "未登录", "login": True}, 401)

        # ---------------- 界面设置 ----------------
        if p == "/api/ui":
            data = urllib.parse.parse_qs(self.rfile.read(length).decode())
            patch = {}
            if "theme" in data:
                patch["theme"] = data["theme"][0] if data["theme"][0] in ("light", "dark", "auto") else "light"
            if "wall" in data:
                wv = data["wall"][0][:80]
                if wv in ("default", "random", "custom") or \
                        (wv.startswith("preset:") and wall_by_id(wv.split(":", 1)[1])):
                    patch["wall"] = wv
            if "accent" in data:
                ac = data["accent"][0].strip()
                if re.match(r"^#[0-9a-fA-F]{6}$", ac):
                    patch["accent"] = ac.lower()
            if "video_speed" in data:
                try:
                    patch["video_speed"] = float(data["video_speed"][0])
                except Exception:
                    pass
            if "reset_wall" in data:
                shutil.rmtree(WALL_DIR, ignore_errors=True)
                patch["wall"] = "default"
            if "warn_temp" in data:
                try:
                    wt = int(float(data["warn_temp"][0]))
                    if 30 <= wt <= 110:
                        patch["warn_temp"] = wt
                except Exception:
                    pass
            if "home_order" in data:
                try:
                    order = json.loads(data["home_order"][0])
                    if isinstance(order, list) and sorted(order) == ["cpu", "disk", "mem", "temp"]:
                        patch["home_order"] = order
                except Exception:
                    pass
            return self._json({"ok": True, "ui": save_ui(patch)})

        # ---------------- 壁纸上传 ----------------
        if p == "/api/wallpaper":
            ctype = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in ctype:
                return self._json({"ok": False, "err": "需要 multipart"}, 400)
            fs = cgi.FieldStorage(fp=self.rfile, headers=self.headers,
                                  environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": ctype})
            f = fs["file"] if "file" in fs else None
            if not f or not getattr(f, "filename", None):
                return self._json({"ok": False, "err": "没有收到文件"}, 400)
            name = os.path.basename(f.filename)
            ext = os.path.splitext(name)[1].lower()
            if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
                return self._json({"ok": False, "err": "只支持 jpg / png / webp"}, 400)
            raw = f.file.read(12 * 1024 * 1024 + 1)
            if len(raw) > 12 * 1024 * 1024:
                return self._json({"ok": False, "err": "图片不能超过 12MB"}, 400)
            os.makedirs(WALL_DIR, exist_ok=True)
            for old in os.listdir(WALL_DIR):
                try:
                    os.remove(os.path.join(WALL_DIR, old))
                except OSError:
                    pass
            fn = "wall" + ext
            with open(os.path.join(WALL_DIR, fn), "wb") as out:
                out.write(raw)
            save_ui({"wall": "custom"})
            return self._json({"ok": True, "wall_url": "/api/wallpaper?v=%d" % int(time.time())})

        # ---------------- 回收站 ----------------
        if p == "/api/trash/empty":
            n = 0
            if os.path.isdir(TRASH_DIR):
                for name in os.listdir(TRASH_DIR):
                    p2 = os.path.join(TRASH_DIR, name)
                    try:
                        if os.path.isdir(p2) and not os.path.islink(p2):
                            shutil.rmtree(p2)
                        else:
                            os.remove(p2)
                        n += 1
                    except OSError:
                        pass
            return self._json({"ok": True, "removed": n})

        # ---------------- 重启 ----------------
        if p == "/api/restart":
            data = urllib.parse.parse_qs(self.rfile.read(length).decode())
            target = (data.get("target") or ["panel"])[0]
            if target == "panel":
                cmd = "sleep 1; systemctl restart box"
            elif target == "device":
                cmd = "sleep 1; /sbin/reboot"
            else:
                return self._json({"ok": False, "err": "不允许"}, 400)
            subprocess.Popen(["/bin/bash", "-c", cmd], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return self._json({"ok": True})

        if p == "/api/passwd":
            data = urllib.parse.parse_qs(self.rfile.read(length).decode())
            old = (data.get("old") or [""])[0]
            new = (data.get("new") or [""])[0]
            info = session_info(self._cookie_token()) or {}
            me = info.get("user") or "admin"
            if not verify_user(me, old):
                return self._json({"ok": False, "err": "原密码错误"}, 400)
            if len(new) < 8:
                return self._json({"ok": False, "err": "新密码至少 8 位"}, 400)
            set_user_password(me, new)
            self._audit("修改密码", "user=%s" % me)
            return self._json({"ok": True})

        # ---------------- 应用商店：安装 / 卸载 ----------------
        if p == "/api/store/install":
            data = urllib.parse.parse_qs(self.rfile.read(length).decode())
            sid = (data.get("id") or [""])[0]
            act = (data.get("act") or ["install"])[0]
            item = next((x for x in STORE if x["id"] == sid), None)
            if not item:
                return self._json({"ok": False, "err": "没有这个应用"}, 400)
            if item.get("kind", "apt") != "docker" and not item["pkg"]:
                return self._json({"ok": False, "err": "这个应用是内置的，不能在这里装卸"}, 400)
            cmd = store_install_cmd(item, act)
            _invalidate_store_cache()
            jid = start_job("%s %s（%s）" % ("安装" if act == "install" else "卸载",
                                          item["name"], item.get("kind", "apt")), cmd)
            self._audit("应用商店", "%s %s" % ("安装" if act == "install" else "卸载", item["name"]))
            return self._json({"ok": True, "job": jid})

        # ---------------- Samba 共享 ----------------
        if p == "/api/samba":
            data = urllib.parse.parse_qs(self.rfile.read(length).decode())
            act = (data.get("act") or ["add"])[0]
            try:
                if not os.path.exists(SMB_CONF):
                    return self._json({"ok": False, "err": "Samba 还没安装，先去应用商店装"}, 400)
                shares = samba_shares()
                if act == "add":
                    sname = (data.get("name") or [""])[0].strip()
                    spath = (data.get("path") or [""])[0].strip()
                    if not re.match(r"^[A-Za-z0-9_\-]{1,20}$", sname):
                        raise ValueError("共享名只能用字母数字下划线横线")
                    if any(s["name"] == sname for s in shares):
                        raise ValueError("共享名已存在")
                    spath = safe_path(spath)
                    if not os.path.isdir(spath):
                        raise ValueError("目录不存在：" + spath)
                    shares.append({"name": sname, "path": spath,
                                   "writable": (data.get("writable") or ["1"])[0] == "1",
                                   "guest": (data.get("guest") or ["1"])[0] == "1",
                                   "comment": (data.get("comment") or [sname])[0][:60]})
                elif act == "delete":
                    sname = (data.get("name") or [""])[0]
                    shares = [s for s in shares if s["name"] != sname]
                elif act == "toggle":
                    sname = (data.get("name") or [""])[0]
                    for s in shares:
                        if s["name"] == sname:
                            s["writable"] = not s["writable"]
                samba_write(shares)
                return self._json({"ok": True, "shares": samba_shares()})
            except Exception as e:
                return self._json({"ok": False, "err": str(e)}, 400)

        # ---------------- 备份任务 ----------------
        if p == "/api/backup":
            data = urllib.parse.parse_qs(self.rfile.read(length).decode())
            act = (data.get("act") or ["save"])[0]
            tasks = load_backups()
            try:
                if act == "save":
                    tid = (data.get("id") or [""])[0]
                    src = safe_path((data.get("src") or [""])[0])
                    dst = safe_path((data.get("dst") or [""])[0])
                    name = (data.get("name") or ["备份"])[0].strip()[:40]
                    mirror = (data.get("mirror") or ["1"])[0] == "1"
                    if not os.path.isdir(src):
                        raise ValueError("源目录不存在")
                    if src == dst:
                        raise ValueError("源和目标不能相同")
                    if dst.startswith(src.rstrip("/") + "/"):
                        raise ValueError("目标不能放在源目录里面")
                    if tid:
                        for t in tasks:
                            if t["id"] == tid:
                                t.update({"src": src, "dst": dst, "name": name, "mirror": mirror})
                    else:
                        tasks.append({"id": "%d" % int(time.time()),
                                      "name": name, "src": src, "dst": dst,
                                      "mirror": mirror, "last": 0, "last_ok": None})
                    save_backups(tasks)
                    return self._json({"ok": True, "tasks": tasks})
                if act == "delete":
                    tid = (data.get("id") or [""])[0]
                    tasks = [t for t in tasks if t["id"] != tid]
                    save_backups(tasks)
                    return self._json({"ok": True, "tasks": tasks})
                if act == "run":
                    tid = (data.get("id") or [""])[0]
                    t = next((x for x in tasks if x["id"] == tid), None)
                    if not t:
                        raise ValueError("任务不存在")
                    os.makedirs(t["dst"], exist_ok=True)
                    flags = "-a --delete" if t.get("mirror") else "-a"
                    cmd = "rsync %s %s/ %s/ && echo '\n完成'" % (
                        flags, t["src"].rstrip("/"), t["dst"].rstrip("/"))
                    jid = start_job("备份 " + t["name"], cmd)
                    last = load_backup_last()
                    last[tid] = {"ts": int(time.time()), "job": jid}
                    ensure_data_dir()
                    with open(BACKUP_LAST, "w") as f:
                        json.dump(last, f)
                    return self._json({"ok": True, "job": jid})
            except Exception as e:
                return self._json({"ok": False, "err": str(e)}, 400)

        # ---------------- 部署网站 ----------------
        if p == "/api/site":
            data = urllib.parse.parse_qs(self.rfile.read(length).decode())
            act = (data.get("act") or ["create"])[0]
            try:
                if act == "create":
                    name = (data.get("name") or [""])[0].strip().lower()
                    if not re.match(r"^[a-z0-9\-]{2,24}$", name):
                        raise ValueError("站点名只能用小写字母、数字、横线")
                    d = os.path.join(SITES_ROOT, name)
                    if os.path.isdir(d):
                        raise ValueError("站点已存在")
                    port = (data.get("port") or [""])[0].strip()
                    port = int(port) if port.isdigit() else free_port()
                    os.makedirs(d, exist_ok=True)
                    with open(os.path.join(d, "index.html"), "w") as f:
                        f.write(SITE_TEMPLATE % {"name": name})
                    os.makedirs(NGX_AVAIL, exist_ok=True)
                    with open(os.path.join(NGX_AVAIL, "box-%s.conf" % name), "w") as f:
                        f.write(SITE_CONF % {"port": port, "root": d, "name": name})
                    os.makedirs(NGX_ENABLED, exist_ok=True)
                    lp = os.path.join(NGX_ENABLED, "box-%s.conf" % name)
                    if not os.path.exists(lp):
                        os.symlink(os.path.join(NGX_AVAIL, "box-%s.conf" % name), lp)
                    out = run("nginx -t 2>&1", 10)
                    if "successful" not in out:
                        return self._json({"ok": False, "err": out[-400:]}, 400)
                    run("systemctl reload nginx 2>/dev/null", 10)
                    return self._json({"ok": True, "port": port, "sites": list_sites()})
                if act == "delete":
                    name = (data.get("name") or [""])[0].strip().lower()
                    if not re.match(r"^[a-z0-9\-]{2,24}$", name):
                        raise ValueError("站点名不合法")
                    for f in (os.path.join(NGX_ENABLED, "box-%s.conf" % name),
                              os.path.join(NGX_AVAIL, "box-%s.conf" % name)):
                        if os.path.lexists(f):
                            os.remove(f)
                    keep = (data.get("keep_files") or ["1"])[0] == "1"
                    if not keep:
                        shutil.rmtree(os.path.join(SITES_ROOT, name), ignore_errors=True)
                    run("systemctl reload nginx 2>/dev/null", 10)
                    return self._json({"ok": True, "sites": list_sites()})
            except Exception as e:
                return self._json({"ok": False, "err": str(e)}, 400)

        # ---------------- 远程访问 ----------------
        if p == "/api/remote":
            data = urllib.parse.parse_qs(self.rfile.read(length).decode())
            act = (data.get("act") or [""])[0]
            if act in ("start", "stop", "restart"):
                unit = (data.get("unit") or [""])[0]
                if unit not in ("tailscaled", "frpc", "zerotier-one"):
                    return self._json({"ok": False, "err": "不允许"}, 400)
                run("systemctl %s %s" % (act, unit), 20)
                time.sleep(0.8)
                return self._json({"ok": True, "state": service_state(unit)})
            if act == "install-ts":
                jid = start_job("安装 Tailscale",
                                "curl -fsSL https://tailscale.com/install.sh | sh")
                return self._json({"ok": True, "job": jid})
            if act == "up-ts":
                auth = (data.get("authkey") or [""])[0].strip()
                cmd = "tailscale up --accept-dns=false --timeout=25s"
                if auth:
                    cmd += " --authkey=%s" % auth
                jid = start_job("连接 Tailscale 网络", cmd)
                return self._json({"ok": True, "job": jid})
            if act == "ddns":
                cfg = {"domain": (data.get("domain") or [""])[0].strip(),
                       "token": (data.get("token") or [""])[0].strip(),
                       "enabled": (data.get("enabled") or ["0"])[0] == "1"}
                self._save_ddns(cfg)
                if cfg["enabled"] and cfg["domain"] and cfg["token"]:
                    write_ddns_script(cfg)
                return self._json({"ok": True, "ddns": cfg})
            return self._json({"ok": False, "err": "未知操作"}, 400)

        return self._json({"ok": False, "err": "not found"}, 404)


def main():
    ensure_data_dir()
    os.makedirs(TRASH_DIR, exist_ok=True)
    srv = ThreadingHTTPServer(LISTEN, Handler)
    srv.daemon_threads = True
    print("%s listening on %s:%d" % (APP_NAME, LISTEN[0], LISTEN[1]), flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
