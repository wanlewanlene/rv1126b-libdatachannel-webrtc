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

# 信令服务器日志 (viewer_join / offer 转发)
brun("echo '== 信令日志尾部 =='; tr -cd '[:print:]\\n' < /tmp/sig.log 2>/dev/null | tail -25", "信令日志", 20)
# 推流日志 (request_offer / answer / ICE 状态)
brun("echo '== 推流日志尾部 =='; tr -cd '[:print:]\\n' < /tmp/rtc_run.log 2>/dev/null | tail -30", "推流日志", 20)
# libdatachannel 是否支持 renegotiate
brun("grep -n 'renegotiate' /usr/include/rtc/rtc.hpp /usr/include/rtc/peerconnection.hpp 2>/dev/null | head -5", "renegotiate API", 20)

board.close()
print("\n===== 完成 =====")
