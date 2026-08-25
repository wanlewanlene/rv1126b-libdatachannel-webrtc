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

LIBDIR="/userdata/coturn/usr/lib/aarch64-linux-gnu:/userdata/coturn/usr/lib"
brun("pkill -f turnserver; sleep 1; echo cleared", "清理旧进程", 20)
brun(f"LD_LIBRARY_PATH={LIBDIR} /userdata/coturn/usr/bin/turnserver -c /etc/turnserver.conf --daemon --log-file=/userdata/coturn/turn.log --pidfile=/userdata/coturn/turn.pid 2>&1; sleep 2; echo started", "daemon 启动(写日志)", 40)
brun("echo '=== turn.log ==='; cat /userdata/coturn/turn.log 2>&1 | tail -30", "查看 turn 日志", 30)
brun("ss -lunp 2>/dev/null | grep 3478 || echo '3478 未监听'; echo '--- proc ---'; pgrep -af turnserver || echo '进程未起'", "验证 3478 监听", 30)

board.close()
print("\n===== 完成 =====")
