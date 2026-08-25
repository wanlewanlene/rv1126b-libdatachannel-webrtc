import paramiko, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

board = paramiko.SSHClient()
board.set_missing_host_key_policy(paramiko.AutoAddPolicy())
board.connect('192.168.2.14', port=22, username='elf', password='elf', timeout=15)

def brun(cmd, title, timeout=120):
    print(f"\n########## [BOARD] {title} ##########")
    stdin, stdout, stderr = board.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors='replace'); err = stderr.read().decode(errors='replace')
    if out: print(out)
    if err: print("[STDERR]", err)

brun("which tcpdump || echo 'NO_TCPDUMP'", "检查 tcpdump", 20)
brun("pkill -f 'tcpdump.*3478' 2>/dev/null; nohup tcpdump -n -tttt udp port 3478 -c 300 -w /userdata/coturn/turn.pcap >/dev/null 2>&1 & echo 'tcpdump started'; sleep 1; pgrep -af tcpdump || echo 'tcpdump 未启动'", "启动 tcpdump 抓 3478", 30)

board.close()
print("\n===== 完成 =====")
