import paramiko, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BOARD_IP = '192.168.137.184'
LOCAL_MAIN = r'c:\Users\zyp\Desktop\3\rv1106\_board_main.cpp'

board = paramiko.SSHClient()
board.set_missing_host_key_policy(paramiko.AutoAddPolicy())
board.connect(BOARD_IP, port=22, username='elf', password='elf', timeout=15)

def brun(cmd, title, timeout=300):
    print(f"\n########## {title} ##########")
    stdin, stdout, stderr = board.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors='replace'); err = stderr.read().decode(errors='replace')
    if out: print(out.rstrip())
    if err: print("[STDERR]", err.rstrip())
    return out

# 1) 停止 + 上传 + 编译
brun("sudo pkill -9 -f '[r]v1126b_webrtc_push' 2>/dev/null; sudo fuser -k /dev/video52 2>/dev/null; sleep 1; echo OK", "停止", 20)
sftp = board.open_sftp()
sftp.put(LOCAL_MAIN, '/userdata/rtc/main.cpp.new')
sftp.close()
brun("cd /userdata/rtc && cp -f main.cpp.new main.cpp && echo 已替换", "上传", 20)
out = brun("cd /userdata/rtc && g++ -std=c++17 -O2 main.cpp -o bin/rv1126b_webrtc_push.new -I/userdata/rtc/ldc_install/include -L/userdata/rtc/lib -L/usr/local/lib -ldatachannel -lrockchip_mpp -lssl -lcrypto -lopus -lasound -lspeexdsp -pthread 2>&1; echo 'EXIT='$?", "编译最终版", 300)
if 'EXIT=0' not in out or 'error' in out.lower():
    brun("echo 编译失败", "失败", 10)
    board.close(); sys.exit(1)

# 2) 部署
brun("cd /userdata/rtc && cp -f bin/rv1126b_webrtc_push.new bin/rv1126b_webrtc_push && chmod +x bin/rv1126b_webrtc_push && echo 'DEPLOYED'", "部署", 20)

# 3) 启动 (nohup sudo -b 方式, 上次验证成功)
brun("cd /userdata/rtc && nohup sudo -b env LD_LIBRARY_PATH=/userdata/rtc/lib:$LD_LIBRARY_PATH ./bin/rv1126b_webrtc_push > /tmp/rtc_run.log 2>&1 & sleep 8; echo '== 进程 =='; pgrep -af '[r]v1126b_webrtc_push' | grep -v bash || echo '(未启动)'; echo '== 日志 =='; tr -cd '[:print:]\\n' < /tmp/rtc_run.log | head -12", "启动", 40)

board.close()
print("\n===== 完成 =====")
