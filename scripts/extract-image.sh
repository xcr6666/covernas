#!/bin/bash
# 从已部署的 Covernas 设备提取「可分发」整机镜像
#
# 用法：
#   1) 在设备上直接跑，输出到本地文件：
#        ssh root@<设备IP> 'bash -s' < scripts/extract-image.sh > covernas.img.gz
#   2) 或在设备上跑并保存到设备：
#        bash extract-image.sh /mnt/covernas.img.gz
#
# 做的事：停止面板服务 → 清理账号/密钥/私人数据/日志 → 重命名分区标签 → dd 全盘 + gzip
# 警告：会清空 /etc/box 配置与 /mnt 数据！脚本会先把它们打包到 /root/pre-image-backup.tar.gz，
#       提取完成后可用 `tar xzf /root/pre-image-backup.tar.gz -C /` 恢复。
set -uo pipefail

OUT="${1:-}"
log() { echo "[extract] $*" >&2; }
[ "$(id -u)" = "0" ] || { log "需要 root 运行"; exit 1; }
[ -b /dev/mmcblk1 ] || { log "找不到 /dev/mmcblk1（请确认目标盘）"; exit 1; }

log "0/8 备份配置与数据到 /root/pre-image-backup.tar.gz"
tar czf /root/pre-image-backup.tar.gz -C / etc/box mnt etc/ssh 2>/dev/null || true

log "1/8 停止服务"
for s in box nginx ttyd alist-box transmission-daemon smbd nmbd aria2 docker docker.socket avahi-daemon; do
  systemctl stop "$s" 2>/dev/null || true
done

log "2/8 清理面板配置与数据盘"
rm -rf /etc/box/* /etc/box/.[!.]* 2>/dev/null || true
rm -rf /mnt/* /mnt/.[!.]* 2>/dev/null || true

log "3/8 重置凭据"
rm -rf /opt/alist/data/* 2>/dev/null || true
rm -f /var/lib/samba/private/passdb.tdb 2>/dev/null || true
rm -f /var/lib/transmission-daemon/info/settings.json 2>/dev/null || true
sed -i 's/^TTYD_PASS=.*/TTYD_PASS=box12345/' /etc/ttyd-auth.conf 2>/dev/null || true
echo 'root:ecoo1234' | chpasswd
rm -f /etc/ssh/ssh_host_*
ssh-keygen -A >/dev/null 2>&1 || true

log "4/8 清理日志/缓存/临时/机器标识"
find /var/log -type f -exec truncate -s 0 {} + 2>/dev/null || true
rm -rf /var/log/journal/* /tmp/* /var/tmp/* 2>/dev/null || true
rm -f /var/cache/apt/archives/*.deb /etc/machine-id /var/lib/systemd/random-seed 2>/dev/null || true

log "5/8 私钥/历史/备份清理"
rm -f /root/.bash_history 2>/dev/null || true
rm -rf /root/.cache /root/.local 2>/dev/null || true
rm -rf /root/*backup* /root/*.bak* /root/box-* 2>/dev/null || true

log "6/8 重命名分区标签并同步 fstab"
cp /etc/fstab /root/fstab.bak 2>/dev/null || true
e2label /dev/mmcblk1p2 COVERNAS_ROOT 2>/dev/null || true
if mountpoint -q /boot; then umount /boot 2>/dev/null || true; fi
# FAT 标签最多 11 字符
fatlabel /dev/mmcblk1p1 COVERNAS_BT 2>/dev/null || true
mount /boot 2>/dev/null || true
P1LBL=$(blkid -s LABEL -o value /dev/mmcblk1p1 2>/dev/null)
P2LBL=$(blkid -s LABEL -o value /dev/mmcblk1p2 2>/dev/null)
# 用实际标签值重写 fstab 两行
sed -i "s|^LABEL=[^ ]* / |LABEL=$P2LBL / |" /etc/fstab
sed -i "s|^LABEL=[^ ]* /boot |LABEL=$P1LBL /boot |" /etc/fstab
grep -E '^LABEL=' /etc/fstab >&2

log "7/8 开始提取（约 20 分钟）"
if [ -n "$OUT" ]; then
  dd if=/dev/mmcblk1 bs=4M status=progress 2>/tmp/dd-progress.log | gzip -1 > "$OUT"
  log "完成：$OUT"
else
  dd if=/dev/mmcblk1 bs=4M status=progress 2>/tmp/dd-progress.log | gzip -1
fi

log "8/8 提取完成。恢复配置：tar xzf /root/pre-image-backup.tar.gz -C / && systemctl start box nginx ttyd smbd alist-box transmission-daemon aria2 docker avahi-daemon"
