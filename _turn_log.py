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
brun("pkill -f turnserver; sleep 1; echo stopped", "停止旧 TURN", 20)
brun(f"LD_LIBRARY_PATH={LIBDIR} nohup /userdata/coturn/usr/bin/turnserver -c /etc/turnserver.conf --log-file=/userdata/coturn/turn.log -v >/dev/null 2>&1 & echo started; sleep 2; ss -lunp 2>/dev/null | grep 3478 && echo 'TURN listening'; ls -l /userdata/coturn/turn.log 2>&1", "重启 TURN 带详细日志", 40)

board.close()
print("\n===== 完成 =====")
