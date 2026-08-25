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

brun("echo '== 推流/信令 =='; pgrep -af '[r]v1126b_webrtc_push' | grep -v bash; pgrep -af '[W]ebSocket.js' | grep -v bash; echo '== 解码计数 =='; grep -a 'decoded' /tmp/rtc_run.log | tail -3; echo '== 连接状态 =='; grep -aE 'CONNECTED|offer|viewer' /tmp/rtc_run.log | tail -5; echo '== 码率调整 =='; grep -a 'bitrate' /tmp/rtc_run.log | tail -3", "推流状态总览", 30)
brun("echo '== 负载 =='; top -bn1 | grep -E 'rv1126b|node' | head -2; echo '== 端口 =='; sudo ss -tlnp | grep -E ':3000|:8080' | head -2", "负载与端口", 20)

board.close()
print("\n===== 完成 =====")
