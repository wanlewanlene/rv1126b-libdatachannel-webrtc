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

# 1. 抓取日志里所有 candidate (看两端候选类型/地址)
brun(r"grep -oE '\"candidate\":\"[^}]*' /userdata/rtc/run.log 2>&1 | head -n 40", "ICE candidate 候选", timeout=30)
# 2. 板卡公网连通性 (STUN 是否可达)
brun("curl -sS -m 6 -o /dev/null -w 'STUN-TCP443:%{http_code}\\n' https://stun.l.google.com:443 2>&1; echo '---'; getent hosts stun.l.google.com 2>&1", "板卡->公网/STUN 解析", timeout=30)
# 3. 板卡网络接口与到默认网关/同网段路由
brun("ip -4 addr show 2>&1 | grep -E 'inet |^[0-9]'; echo '--- route ---'; ip route 2>&1", "板卡网卡与路由", timeout=30)

board.close()
print("\n===== 完成 =====")
