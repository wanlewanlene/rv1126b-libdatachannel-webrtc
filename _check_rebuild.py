import paramiko, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BOARD_IP = '192.168.137.184'

board = paramiko.SSHClient()
board.set_missing_host_key_policy(paramiko.AutoAddPolicy())
board.connect(BOARD_IP, port=22, username='elf', password='elf', timeout=15)

def brun(cmd, title, timeout=60):
    print(f"\n########## {title} ##########")
    stdin, stdout, stderr = board.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors='replace'); err = stderr.read().decode(errors='replace')
    if out: print(out.rstrip())
    if err: print("[STDERR]", err.rstrip())
    return out

brun("echo '== 进程 =='; pgrep -af '[r]v1126b_webrtc_push' | grep -v bash || echo '(无进程!)'; echo '== 完整日志 =='; tr -cd '[:print:]\\n' < /tmp/rtc_run.log | tail -25", "进程与日志", 20)
brun("echo '== 信令 =='; pgrep -af '[W]ebSocket.js' | grep -v bash || echo '(信令未运行!)'", "信令状态", 20)

board.close()
print("\n===== 完成 =====")
