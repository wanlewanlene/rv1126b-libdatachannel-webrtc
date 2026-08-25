import paramiko
import sys
time = __import__('time')
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

# 后台启动 run.sh (nohup + setsid 防止 SSH 断开被 kill), 输出到日志
brun("setsid bash /userdata/rtc/run.sh > /userdata/rtc/run.log 2>&1 < /dev/null & echo started pid=$!", "启动 run.sh", timeout=30)
time.sleep(8)

# 检查进程 + 日志
brun("pgrep -af 'WebSocket.js|rv1126b_webrtc_push' 2>&1; echo '=== run.log ==='; grep -vE 'mpp_|dumping|buffer 0x|ref_count|mpp_mem|mpp_group|h264e|mpp_cfg|mpp_enc' /userdata/rtc/run.log 2>&1", "进程与日志", timeout=30)

# 验证 HTTP 3000
brun("node -e \"const http=require('http'); http.get('http://127.0.0.1:3000/', r=>{let d='';r.on('data',c=>d+=c);r.on('end',()=>console.log('HTTP',r.statusCode,'len',d.length,'hasVideo',d.includes('remoteVideo')))})\" 2>&1", "HTTP 3000 验证", timeout=30)

board.close()
print("\n===== 完成 =====")
