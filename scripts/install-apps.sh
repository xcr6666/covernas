#!/bin/bash
# 安装 Box 需要的外部软件：aria2 / samba / alist
set -uo pipefail
export DEBIAN_FRONTEND=noninteractive

echo "== 1. aria2 =="
if ! command -v aria2c >/dev/null; then
  apt-get install -y aria2 >/tmp/apt-aria2.log 2>&1 && echo "  aria2 已安装" || echo "  aria2 安装失败"
fi

mkdir -p /etc/aria2 /mnt/downloads
cat > /etc/aria2/aria2.conf <<'EOF'
dir=/mnt/downloads
continue=true
input-file=/etc/aria2/aria2.session
save-session=/etc/aria2/aria2.session
save-session-interval=30
enable-rpc=true
rpc-listen-all=true
rpc-listen-port=6800
rpc-secret=boxaria2
rpc-allow-origin-all=true
max-concurrent-downloads=3
max-connection-per-server=4
split=4
bt-enable-lpd=true
enable-dht=true
listen-port=51413
seed-time=0
file-allocation=none
disk-cache=16M
EOF
touch /etc/aria2/aria2.session

cat > /etc/systemd/system/aria2.service <<'EOF'
[Unit]
Description=aria2 downloader
After=network-online.target

[Service]
ExecStart=/usr/bin/aria2c --conf-path=/etc/aria2/aria2.conf
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now aria2 >/dev/null 2>&1
sleep 1
printf '  aria2 状态: %s\n' "$(systemctl is-active aria2)"

echo "== 2. Samba =="
if ! command -v smbd >/dev/null; then
  apt-get install -y samba >/tmp/apt-samba.log 2>&1 && echo "  samba 已安装" || echo "  samba 安装失败"
fi

if ! grep -q '^\[mnt\]' /etc/samba/smb.conf 2>/dev/null; then
  cat >> /etc/samba/smb.conf <<'EOF'

[mnt]
   comment = Box 共享
   path = /mnt
   browseable = yes
   read only = no
   guest ok = no
   create mask = 0664
   directory mask = 0775
EOF
fi

# 建一个 samba 专用账号，密码与面板初始密码一致，可后续改
if ! id -u share >/dev/null 2>&1; then
  useradd -M -s /usr/sbin/nologin share 2>/dev/null
fi
# 生成随机 SMB 密码（首次部署用，请记录；后续可用面板「网络共享」修改）
SMB_PASS="$(head -c 12 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 12)"
printf '%s\n%s\n' "$SMB_PASS" "$SMB_PASS" | smbpasswd -s -a share >/dev/null 2>&1 && \
  echo "  samba 账号 share 已创建，密码: $SMB_PASS"
chown -R share:share /mnt 2>/dev/null
systemctl enable --now smbd nmbd >/dev/null 2>&1
sleep 1
printf '  smbd 状态: %s\n' "$(systemctl is-active smbd)"

echo "== 3. Alist =="
if [ ! -x /opt/alist/alist ]; then
  mkdir -p /opt/alist
  cd /tmp || exit 1
  URL="https://github.com/AlistGo/alist/releases/latest/download/alist-linux-armv7.tar.gz"
  if curl -fsSL --max-time 120 "$URL" -o alist.tar.gz; then
    tar xzf alist.tar.gz -C /opt/alist --strip-components=1 2>/dev/null
    chmod +x /opt/alist/alist
    echo "  alist 已下载"
  else
    echo "  alist 下载失败（可能没有 armv7 包）"
  fi
  rm -f alist.tar.gz
fi

if [ -x /opt/alist/alist ]; then
  cat > /etc/systemd/system/alist-box.service <<'EOF'
[Unit]
Description=Alist file list
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/alist
ExecStart=/opt/alist/alist server
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable --now alist-box >/dev/null 2>&1
  sleep 2
  printf '  alist 状态: %s\n' "$(systemctl is-active alist-box)"
  echo -n "  alist 初始密码: "
  /opt/alist/alist admin random 2>/dev/null | tail -2 | tr -d '\n'
  echo
fi

echo "== 汇总 =="
for s in aria2 smbd alist-box; do printf '  %-12s %s\n' "$s" "$(systemctl is-active $s 2>/dev/null)"; done
df -h / | tail -1
