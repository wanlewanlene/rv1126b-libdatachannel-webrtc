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

brun("echo '== 信令 =='; pgrep -af '[W]ebSocket.js' | grep -v bash || echo '(未运行)'; echo '== 推流 =='; pgrep -af '[r]v1126b_webrtc_push' | grep -v bash || echo '(未运行)'; echo '== TURN =='; pgrep -af '[t]urnserver' | grep -v bash || echo '(未运行)'; echo '== 端口 =='; sudo ss -tlnp | grep -E ':3000|:8080' || echo '(3000/8080 未监听)'", "服务状态", 20)

board.close()
print("\n===== 完成 =====")
