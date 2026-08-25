#!/usr/bin/env bash
# ============================================================
# 全量备份：本地工程文件 -> 虚拟机 rootfs 镜像（经 chroot）
# 用法：先按需修改下方变量，然后 bash backup_to_rootfs.sh
# 依赖：sshpass（sudo apt install -y sshpass）
# 请在 WSL / Git Bash / 虚拟机内运行（Windows CMD 不可用）
# ============================================================
set -euo pipefail

# ---------- 需按实际环境修改 ----------
REMOTE_HOST="192.168.2.10"
REMOTE_USER="elf"
PASSWORD="elf"                                # ssh / sudo 密码
ROOTFS_DIR="/home/elf/work/<SDK路径>/rootfs"   # 必改：rootfs 实际目录（替换 <SDK路径>）
CHROOT_TARGET="/opt/rv1106_backup"            # rootfs 内的备份目标目录
# 源目录：WSL 用 /mnt/c/Users/...，Git Bash 用 /c/Users/...
LOCAL_DIR="/mnt/c/Users/zyp/Desktop/3/rv1106"

# ---------- 无需修改 ----------
SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=5"
ssh_run() { sshpass -p "$PASSWORD" ssh $SSH_OPTS "$REMOTE_USER@$REMOTE_HOST" "$@"; }

# 1) 依赖检查
command -v sshpass >/dev/null 2>&1 || { echo "缺少 sshpass：sudo apt install -y sshpass"; exit 1; }

# 2) 连通性 + 预缓存 sudo 凭证
#    提前 sudo -v，避免后面 chroot 时 sudo 密码与 tar 管道抢 stdin
ssh_run "echo '$PASSWORD' | sudo -S -v" || { echo "SSH/sudo 认证失败"; exit 1; }
echo "[1/3] SSH 连接与 sudo 凭证 OK"

# 3) rootfs 内创建目标目录
ssh_run "sudo mkdir -p '$CHROOT_TARGET'"
echo "[2/3] 已创建 chroot 目标目录 $CHROOT_TARGET"

# 4) 全量备份：本地 tar（保权限/时间戳/结构/隐藏文件） -> SSH -> chroot 内解包
cd "$LOCAL_DIR"
tar --numeric-owner -cpf - --acls --xattrs . \
  | ssh_run "sudo chroot '$ROOTFS_DIR' bash -c \"mkdir -p '$CHROOT_TARGET' && tar -xpf - -C '$CHROOT_TARGET' --numeric-owner\""
echo "[3/3] 备份完成 -> $REMOTE_USER@$REMOTE_HOST:chroot($ROOTFS_DIR)$CHROOT_TARGET"

# ---------- 校验 ----------
echo
echo "== 校验 =="
echo "本地文件数: $(find "$LOCAL_DIR" -type f | wc -l)"
echo "本地大小:   $(du -sh "$LOCAL_DIR" | cut -f1)"
ssh_run "sudo chroot '$ROOTFS_DIR' bash -c 'echo 远端文件数: \$(find $CHROOT_TARGET -type f | wc -l); echo 远端大小: \$(du -sh $CHROOT_TARGET | cut -f1)'"
echo
echo "两边的文件数与大小应一致，即为完整备份。"
