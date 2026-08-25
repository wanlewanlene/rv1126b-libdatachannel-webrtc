import paramiko, time, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BOARD_IP = '192.168.2.14'

def brun(board, cmd, title, timeout=120):
    print(f"\n########## [BOARD {BOARD_IP}] {title} ##########")
    stdin, stdout, stderr = board.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors='replace'); err = stderr.read().decode(errors='replace')
    if out: print(out)
    if err: print("[STDERR]", err)

try:
    board = paramiko.SSHClient()
    board.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    board.connect(BOARD_IP, port=22, username='elf', password='elf', timeout=15)
    print(f"\n[OK] 成功连接 {BOARD_IP}")
except Exception as e:
    print(f"\n[FAIL] 无法连接 {BOARD_IP}: {e}")
    sys.exit(1)

# 确认板卡自身 IP
brun(board, "ip -4 addr show | grep -E 'inet '; echo '---'; hostname", "板卡网络确认", timeout=20)

# 检查残留进程 + 摄像头占用
brun(board, "pgrep -af 'WebSocket.js|rv1126b_webrtc_push' || echo '无残留进程'; echo '--- camera ---'; fuser /dev/video52 2>&1 || echo 'video52 空闲'", "残留检查", timeout=20)

# 若有残留则清理
brun(board, "pkill -9 -f WebSocket.js; pkill -9 -f rv1126b_webrtc_push; sleep 2; pgrep -af 'WebSocket.js|rv1126b_webrtc_push' || echo '已全部清理'; fuser /dev/video52 2>&1 || echo 'video52 空闲'", "清理残留", timeout=30)

# 启动 run.sh
brun(board, "setsid bash /userdata/rtc/run.sh > /userdata/rtc/run.log 2>&1 < /dev/null & echo started pid=$!", "启动 run.sh", timeout=30)
time.sleep(9)
brun(board, "pgrep -af 'WebSocket.js|rv1126b_webrtc_push' 2>&1; echo '=== log ==='; grep -avE 'mpp_|dumping|buffer 0x|ref_count|mpp_mem|mpp_group|h264e|mpp_cfg|mpp_enc|h264' /userdata/rtc/run.log 2>&1", "启动后状态", timeout=30)

# HTTP 验证 (板卡本地)
brun(board, "node -e \"const http=require('http'); http.get('http://127.0.0.1:3000/', r=>{let d='';r.on('data',c=>d+=c);r.on('end',()=>console.log('HTTP',r.statusCode,'len',d.length,'hasVideo',d.includes('remoteVideo')))})\" 2>&1 || echo 'node 不可用'", "HTTP 3000 本地验证", timeout=30)

board.close()
print("\n===== 完成 =====")
