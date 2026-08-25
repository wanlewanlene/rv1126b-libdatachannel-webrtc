import paramiko, time, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

board = paramiko.SSHClient()
board.set_missing_host_key_policy(paramiko.AutoAddPolicy())
board.connect('192.168.2.14', port=22, username='elf', password='elf', timeout=15)

def brun(cmd, title, timeout=120):
    print(f"\n########## [BOARD] {title} ##########")
    stdin, stdout, stderr = board.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors='replace'); err = stderr.read().decode(errors='replace')
    if out: print(out)
    if err: print("[STDERR]", err)

# 用 sudo 建目录并改属主, 再解包
brun("echo elf | sudo -S mkdir -p /userdata/coturn; echo elf | sudo -S chown -R elf:elf /userdata/coturn; for d in /userdata/aptcache/archives/*.deb; do dpkg -x \"$d\" /userdata/coturn/; done; echo extracted; ls -l /userdata/coturn/usr/bin/turnserver", "解包到 /userdata/coturn", 60)

# 检查缺失库 (用解包后的真实文件)
brun("ldd /userdata/coturn/usr/bin/turnserver 2>&1 | grep -i 'not found' || echo '无缺失库'", "动态库依赖检查", 30)

# 启动 turnserver (elf 用户, 3478 非特权)
LIBDIR="/userdata/coturn/usr/lib/aarch64-linux-gnu:/userdata/coturn/usr/lib"
brun(f"pkill -f turnserver; sleep 1; LD_LIBRARY_PATH={LIBDIR} /userdata/coturn/usr/bin/turnserver -c /etc/turnserver.conf --daemon 2>&1; sleep 2; echo started", "启动 coturn", 40)
brun("ss -lunp 2>/dev/null | grep 3478 || echo '3478 未监听'; echo '--- proc ---'; pgrep -af turnserver || echo '进程未起'", "验证 3478 监听", 30)

board.close()
print("\n===== 完成 =====")
