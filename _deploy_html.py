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

# 部署新 Browser_client.html
local = open(r'c:/Users/zyp/Desktop/3/rv1106/Browser_client.html','r',encoding='utf-8').read()
sftp = board.open_sftp()
with sftp.open('/userdata/rtc/server/Browser_client.html','w') as f:
    f.write(local)
sftp.close()
print("\n[LOCAL] Browser_client.html 已部署到板卡")

# 确认已含 TURN 配置
brun("grep -n 'turn:' /userdata/rtc/server/Browser_client.html | head -3", "板卡文件确认 TURN 配置", 20)

# 干净重启 run.sh (先清理残留, 确认摄像头空闲)
brun("pkill -9 -f WebSocket.js; pkill -9 -f rv1126b_webrtc_push; sleep 2; pgrep -af 'WebSocket.js|rv1126b_webrtc_push' || echo '已清理'; fuser /dev/video52 2>&1 || echo 'video52 空闲'", "清理旧进程", 30)
brun("setsid bash /userdata/rtc/run.sh > /userdata/rtc/run.log 2>&1 < /dev/null & echo started pid=$!", "重启 run.sh", 30)
time.sleep(9)
brun("pgrep -af 'WebSocket.js|rv1126b_webrtc_push' 2>&1; echo '=== log ==='; grep -avE 'mpp_|dumping|buffer 0x|ref_count|mpp_mem|mpp_group|h264e|mpp_cfg|mpp_enc|h264' /userdata/rtc/run.log 2>&1", "重启后状态", 30)
brun("ss -lunp 2>/dev/null | grep 3478 || echo 'TURN 3478 未监听'; pgrep -af turnserver || echo 'turnserver 未起'", "TURN 服务器状态", 20)

board.close()
print("\n===== 完成 =====")
