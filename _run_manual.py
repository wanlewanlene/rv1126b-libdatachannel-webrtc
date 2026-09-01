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

# 清理 + 手动前台启动 8s 看初始化错误
brun("sudo pkill -9 -f '[r]v1126b_webrtc_push' 2>/dev/null; sudo fuser -k /dev/video52 2>/dev/null; sleep 2; ls -l /dev/video52 2>&1", "清理", 20)
brun("cd /userdata/rtc && timeout 8 env LD_LIBRARY_PATH=/userdata/rtc/lib:$LD_LIBRARY_PATH ./bin/rv1126b_webrtc_push 2>&1 | tr -cd '[:print:]\\n' | head -20", "前台启动诊断", 30)

board.close()
print("\n===== 完成 =====")
