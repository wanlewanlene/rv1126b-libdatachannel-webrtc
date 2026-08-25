import paramiko, sys
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

brun(r"grep -aE '\[conn\]|\[recv\]|candidate:|sdp candidate|\[offer\]|\[streamer\]|\[viewer\]|\[SIG\]|\[RTC\]|relay|forwarding' /userdata/rtc/run.log 2>&1 | tail -n 90", "本次连接完整日志(含 relay/TURN)", timeout=30)

board.close()
print("\n===== 完成 =====")
