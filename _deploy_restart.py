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

# 备份旧日志
brun("cp /userdata/rtc/run.log /userdata/rtc/run.log.bak.$(date +%H%M%S) 2>&1; echo backed", "备份旧日志", timeout=20)

# 用本地增强版覆盖板卡上的 WebSocket.js (通过 stdout 传文件)
local = open(r'c:/Users/zyp/Desktop/3/rv1106/WebSocket.js','r',encoding='utf-8').read()
sftp = board.open_sftp()
with sftp.open('/userdata/rtc/server/WebSocket.js','w') as f:
    f.write(local)
sftp.close()
print("\n[LOCAL] WebSocket.js 已写入板卡 /userdata/rtc/server/WebSocket.js")

# 杀掉旧进程
brun("pkill -f WebSocket.js; pkill -f rv1126b_webrtc_push; sleep 1; pgrep -af 'WebSocket.js|rv1126b_webrtc_push' || echo '进程已清理'", "停止旧进程", timeout=30)

# 重新后台启动
brun("setsid bash /userdata/rtc/run.sh > /userdata/rtc/run.log 2>&1 < /dev/null & echo started pid=$!", "重启 run.sh", timeout=30)

import time
time.sleep(8)
brun("pgrep -af 'WebSocket.js|rv1126b_webrtc_push' 2>&1; echo '=== log ==='; grep -vE 'mpp_|dumping|buffer 0x|ref_count|mpp_mem|mpp_group|h264e|mpp_cfg|mpp_enc|h264' /userdata/rtc/run.log 2>&1", "重启后状态", timeout=30)

board.close()
print("\n===== 完成 =====")
