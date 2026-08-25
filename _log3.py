import paramiko, sys, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

board = paramiko.SSHClient()
board.set_missing_host_key_policy(paramiko.AutoAddPolicy())
board.connect('192.168.137.184', port=22, username='elf', password='elf', timeout=15)

def brun(cmd, title, timeout=120):
    print(f"\n########## [BOARD] {title} ##########")
    stdin, stdout, stderr = board.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors='replace'); err = stderr.read().decode(errors='replace')
    if out: print(out)
    if err: print("[STDERR]", err)

# 抓取本次连接相关的全部关键行: conn/client IP, recv, candidate, sdp, RTC state, gathering
brun(r"grep -aE '\[conn\]|\[recv\]|candidate:|sdp candidate|\[offer\]|\[streamer\]|\[viewer\]|\[SIG\]|\[RTC\]|\[offer\] forwarding' /userdata/rtc/run.log 2>&1 | tail -n 80", "本次握手完整日志", timeout=30)

board.close()
print("\n===== 完成 =====")
