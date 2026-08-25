import paramiko
import sys
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

# 1. 查看 run.sh 内容
brun("cat /userdata/rtc/run.sh 2>&1", "run.sh 内容")
# 2. 检查是否已有进程在跑
brun("pgrep -af 'WebSocket.js|rv1126b_webrtc_push' 2>&1", "已有相关进程")

board.close()
print("\n===== 完成 =====")
