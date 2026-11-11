# 刷机说明（Covernas 整机镜像）

## 镜像信息

| 项目 | 内容 |
|---|---|
| 系统名称 | Covernas 家庭服务器 **v1.1.0**（开发者 XCR） |
| 硬件 | 玩客云 OneCloud（Amlogic S805，ARMv7 32-bit，1GB 内存，8GB eMMC，千兆网口，双 USB 2.0） |
| 底层 | Ubuntu 20.04.6 LTS，内核 5.15.79-meson |
| 镜像格式 | `Covernas-1.1.0-onecloud.img.gz`（eMMC 全盘原始镜像，gzip 压缩；解压后约 7.3 GiB） |
| 分区 | p1：vfat `/boot`（256MB，标签 `COVERNAS_BT`）；p2：ext4 `/`（约 7GB，标签 `COVERNAS_ROOT`） |
| 大小 | gzip 压缩后约 **1.4 GB**（解压后 7.3 GiB） |
| 校验 | `55fd7e6e1ce17881c994a4b75de92f34415dcd87110f912e14bdcf3fde12a8ee`（见 `SHA256SUMS`） |
| 下载 | 本仓库 **Releases** 页面 |

## 默认凭据（刷入后请立即修改）

| 入口 | 账号 | 默认密码 |
|---|---|---|
| 面板 `http://<设备IP>` | `admin` | 首次访问会进入初始化流程，自行设置 |
| SSH `ssh root@<设备IP>` | `root` | `ecoo1234` |
| 网页终端 `:7681` | `admin` | `box12345` |
| Samba 共享 | `share` | 需在面板「网络共享」里重新设置 |

> 镜像已做脱敏：不包含任何私人账号、密钥、文件与历史数据。SSH 主机指纹在每次刷机后重新生成，`known_hosts` 里旧的记录需要删除（`ssh-keygen -R <设备IP>`）。

## 刷机方法

### 方法一：U 盘启动 Linux 写入 eMMC（推荐）

1. 用 U 盘启动任意 Linux（Armbian / Ubuntu / 任一能识别 eMMC 的 Live 系统）。
2. 把镜像传到这台设备（scp / wget / U 盘均可）。
3. **确认目标盘**，千万别写错（U 盘一般是 `/dev/sda`，eMMC 一般是 `/dev/mmcblk1`）：

   ```bash
   lsblk
   ```

4. 解压写入：

   ```bash
   zcat Covernas-1.1.0-onecloud.img.gz | sudo dd of=/dev/mmcblk1 bs=4M conv=fsync status=progress
   sudo sync
   sudo poweroff
   ```

5. 拔掉 U 盘，重新上电，等 1–2 分钟首次启动完成。

### 方法二：已有 Linux 环境直接写入

如果设备已经能进入 Linux（U 盘系统或 SSH 进去的救援系统），在**这台设备上**执行同样的 `zcat | dd` 即可；也可以用另一台 Linux 通过读卡器/USB 转接写入 eMMC。

### 方法三：从现有设备提取自己的镜像

参见 [`scripts/extract-image.sh`](../scripts/extract-image.sh)：它会先清理凭据与私人数据，再流式导出整盘镜像（约 20–25 分钟，需保证 SSH 稳定）。

## 刷机后检查清单

```bash
# 1. 网络与面板
ping <设备IP>
curl -s -o /dev/null -w '%{http_code}\n' http://<设备IP>/     # 期望 200
curl -s http://<设备IP>/api/login                              # {"ok":true,"init":false,"authed":false}

# 2. 服务状态（期望全部 active，failed 为 0）
systemctl is-active box nginx ttyd smbd alist-box transmission-daemon aria2 docker avahi-daemon
systemctl --failed

# 3. 分区标签
blkid /dev/mmcblk1p1 /dev/mmcblk1p2     # 期望 COVERNAS_BT / COVERNAS_ROOT
```

1. 浏览器打开 `http://<设备IP>`，按提示创建管理员密码。
2. 设置页 → 修改 root 密码（或 SSH 里 `passwd`）、网页终端密码。
3. 设置页 → 手机访问，扫码确认手机可访问。
4. 如需外网访问，参考 README 的反向代理 + HTTPS 配置。

## 注意事项

- 刷机会**清空 eMMC 上的全部数据**，不可撤销；镜像不包含原厂固件备份。
- 目标设备必须是 Amlogic S805 平台（玩客云 OneCloud）。其他硬件的 U-Boot/内核不匹配，**不要刷**。
- 首次启动会重新生成 SSH 主机密钥、machine-id，并初始化面板账号。
- 镜像内的 Docker 数据目录为空；应用商店里的 Docker 应用需重新安装（数据卷在 `/mnt`）。
- 镜像不包含媒体文件、个人数据；数据盘 `/mnt` 为空目录结构。

## 免责声明

镜像按「现状」提供，不含任何担保。刷机有变砖风险（短接重刷通常可救回），请在能接受风险的前提下使用。
