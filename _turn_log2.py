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
# 配置加 log-file (若未存在)
brun("echo elf | sudo -S bash -c 'grep -q log-file /etc/turnserver.conf || echo log-file=/userdata/coturn/turn.log >> /etc/turnserver.conf'; echo elf | sudo -S cat /etc/turnserver.conf", "配置加 log-file", 20)
brun("pkill -f turnserver; sleep 1; echo stopped", "停 TURN", 20)
brun(f"LD_LIBRARY_PATH={LIBDIR} nohup /userdata/coturn/usr/bin/turnserver -c /etc/turnserver.conf >> /userdata/coturn/turn.out 2>&1 & echo started; sleep 2; ss -lunp 2>/dev/null | grep 3478 && echo 'TURN listening'; ls -l /userdata/coturn/turn.out 2>&1", "重启 TURN(stdout 落盘)", 40)

board.close()
print("\n===== 完成 =====")
