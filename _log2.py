import paramiko
import sys
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

# 抓取信令/viewer/answer/ICE 握手相关行
brun(r"grep -nE 'viewer|answer|offer|\[recv\]|\[streamer\]|\[SIG\]|gathering|state|viewer_join|ws connect|connect' /userdata/rtc/run.log 2>&1", "握手相关日志", timeout=30)
# 也看信令服务器 WebSocket.js 自己打印的日志(可能在 run.log 混着)
brun(r"grep -nE '\[offer\]|\[recv\]|\[streamer\]|\[viewer\]|joined|forwarding|viewer_join' /userdata/rtc/run.log 2>&1", "信令服务器打印日志", timeout=30)

board.close()
print("\n===== 完成 =====")
