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

brun("grep -aE 'ALSA|AUDIO|denoise' /tmp/rtc_run.log | head -5", "音频日志确认", 20)
brun("pgrep -af '[r]v1126b_webrtc_push' | grep -v bash || echo '(无进程!)'", "进程确认", 20)

board.close()
print("\n===== 完成 =====")
