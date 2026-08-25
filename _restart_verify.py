import paramiko, sys, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BOARD_IP = '192.168.137.184'

board = paramiko.SSHClient()
board.set_missing_host_key_policy(paramiko.AutoAddPolicy())
board.connect(BOARD_IP, port=22, username='elf', password='elf', timeout=15)

def brun(cmd, title, timeout=120):
    print(f"\n########## {title} ##########")
    stdin, stdout, stderr = board.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors='replace'); err = stderr.read().decode(errors='replace')
    if out: print(out.rstrip())
    if err: print("[STDERR]", err.rstrip())
    return out

# 1) 干净重启推流 (信令保留)
brun("sudo pkill -TERM -f '[r]v1126b_webrtc_push'; sleep 3; sudo pkill -9 -f '[r]v1126b_webrtc_push' 2>/dev/null; sudo fuser -k /dev/video52 2>/dev/null; sleep 1; pgrep -af '[r]v1126b_webrtc_push' | grep -v bash || echo '(已停止)'", "停止旧推流", 30)
brun("ls -l /dev/video52 2>&1; pgrep -af '[W]ebSocket.js' | grep -v bash || echo '(信令未运行!)'", "摄像头/信令检查", 20)
brun("cd /userdata/rtc && sudo -b nohup env LD_LIBRARY_PATH=/userdata/rtc/lib:$LD_LIBRARY_PATH ./bin/rv1126b_webrtc_push > /tmp/rtc_run.log 2>&1 & sleep 10; pgrep -af '[r]v1126b_webrtc_push' | grep -v bash || echo '(启动失败!)'", "重启推流", 40)

# 2) 验证解码数据流 (视频流核心指标)
brun("grep -aE 'V4L2|DEC|streaming' /tmp/rtc_run.log | head -12", "启动日志", 30)

# 3) 找板卡上的 MPP 源码
brun("dpkg -L rockchip-mpp-demos 2>/dev/null | head -20; echo '---'; find /usr/share /usr/src /opt /home -maxdepth 4 -iname '*mpi_dec*' -o -iname 'mpp' -type d 2>/dev/null | head -10; echo '--- (end)'", "板卡 MPP 源码搜索", 40)

board.close()
print("\n===== 完成 =====")
