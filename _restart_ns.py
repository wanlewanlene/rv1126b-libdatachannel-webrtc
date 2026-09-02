import paramiko, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BOARD_IP = '192.168.137.184'

board = paramiko.SSHClient()
board.set_missing_host_key_policy(paramiko.AutoAddPolicy())
board.connect(BOARD_IP, port=22, username='elf', password='elf', timeout=15)

def brun(cmd, title, timeout=60):
    print(f"\n########## {title} ##########")
    stdin, stdout, stderr = board.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors='replace'); err = stderr.read().decode(errors='replace')
    if out: print(out.rstrip())
    if err: print("[STDERR]", err.rstrip())
    return out

# 清理设备占用 + 启动
brun("sudo pkill -9 -f '[r]v1126b_webrtc_push' 2>/dev/null; sudo fuser -k /dev/video52 2>/dev/null; sleep 2; ls /dev/video52 2>&1", "清理", 20)
brun("cd /userdata/rtc && sudo -b nohup env LD_LIBRARY_PATH=/userdata/rtc/lib:$LD_LIBRARY_PATH ./bin/rv1126b_webrtc_push > /tmp/rtc_run.log 2>&1 & sleep 10; pgrep -af '[r]v1126b_webrtc_push' | grep -v bash || echo '(启动失败!)'", "启动推流", 40)
brun("grep -aE 'ALSA|AUDIO|denoise|streaming' /tmp/rtc_run.log | head -6", "音频日志确认", 20)

board.close()
print("\n===== 完成 =====")
