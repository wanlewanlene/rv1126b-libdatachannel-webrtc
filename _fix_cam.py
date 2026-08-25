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

# 强杀残留推流 + 信令 (保留 turnserver 3847)
brun("kill -9 3212 2>/dev/null; kill -9 3899 2>/dev/null; pkill -9 -f WebSocket.js; pkill -9 -f rv1126b_webrtc_push; sleep 2; pgrep -af 'WebSocket.js|rv1126b_webrtc_push' || echo '已清理'", "强杀残留进程(保留TURN)", 30)
brun("fuser /dev/video52 2>&1 || echo 'video52 空闲'; ss -ltnp 2>/dev/null | grep -E ':3000|:8080' || echo '3000/8080 空闲'", "资源复核", 20)
# 重启 run.sh
brun("setsid bash /userdata/rtc/run.sh > /userdata/rtc/run.log 2>&1 < /dev/null & echo started pid=$!", "重启 run.sh", 30)
time.sleep(9)
brun("pgrep -af 'WebSocket.js|rv1126b_webrtc_push' 2>&1; echo '=== log ==='; grep -avE 'mpp_|dumping|buffer 0x|ref_count|mpp_mem|mpp_group|h264e|mpp_cfg|mpp_enc|h264' /userdata/rtc/run.log 2>&1", "重启后状态", 30)
brun("ss -lunp 2>/dev/null | grep 3478 >/dev/null && echo 'TURN 3478 OK'; pgrep -af turnserver >/dev/null && echo 'turnserver 运行中'", "TURN 状态", 20)

board.close()
print("\n===== 完成 =====")
