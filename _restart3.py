import paramiko, time, sys
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

# 清掉所有残留
brun("pkill -9 -f WebSocket.js; pkill -9 -f rv1126b_webrtc_push; sleep 2; pgrep -af 'WebSocket.js|rv1126b_webrtc_push' || echo '已全部清理'", "清理全部残留", timeout=30)
brun("fuser /dev/video52 2>&1 || echo 'video52 空闲'; ss -ltnp 2>/dev/null | grep -E ':3000|:8080' || echo '3000/8080 空闲'", "资源占用复核", timeout=20)
# 重启
brun("setsid bash /userdata/rtc/run.sh > /userdata/rtc/run.log 2>&1 < /dev/null & echo started pid=$!", "重启 run.sh", timeout=30)
time.sleep(9)
brun("pgrep -af 'WebSocket.js|rv1126b_webrtc_push' 2>&1; echo '=== log ==='; grep -avE 'mpp_|dumping|buffer 0x|ref_count|mpp_mem|mpp_group|h264e|mpp_cfg|mpp_enc|h264' /userdata/rtc/run.log 2>&1", "重启后状态", timeout=30)

board.close()
print("\n===== 完成 =====")
