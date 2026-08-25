import paramiko, time, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

board = paramiko.SSHClient()
board.set_missing_host_key_policy(paramiko.AutoAddPolicy())
board.connect('192.168.2.14', port=22, username='elf', password='elf', timeout=15)

def brun(cmd, title, timeout=300):
    print(f"\n########## [BOARD] {title} ##########")
    stdin, stdout, stderr = board.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors='replace'); err = stderr.read().decode(errors='replace')
    if out: print(out)
    if err: print("[STDERR]", err)

# 1. 安装 coturn (sudo, 密码 elf)
brun("echo elf | sudo -S apt-get update 2>&1 | tail -3", "apt update", 180)
brun("echo elf | sudo -S apt-get install -y coturn 2>&1 | tail -20", "安装 coturn", 300)
brun("which turnserver && turnserver --version 2>&1 | head -1", "确认安装", 30)

# 2. 写配置文件到 /tmp 再通过 sudo cp (因为 /etc 需 root)
CFG = """listening-ip=192.168.2.14
listening-port=3478
relay-ip=192.168.2.14
external-ip=119.132.157.76
min-port=49152
max-port=49200
verbose
fingerprint
lt-cred-mech
user=webrtc:webrtc123
realm=rtc.local
"""
sftp = board.open_sftp()
with sftp.open('/tmp/turnserver.conf','w') as f:
    f.write(CFG)
sftp.close()
brun("echo elf | sudo -S cp /tmp/turnserver.conf /etc/turnserver.conf && echo 'config written'; echo elf | sudo -S cat /etc/turnserver.conf", "写入并查看配置", 30)

# 3. 启动 coturn (daemon)
brun("echo elf | sudo -S pkill -f turnserver; sleep 1; echo elf | sudo -S turnserver -c /etc/turnserver.conf --daemon 2>&1; sleep 2; echo started", "启动 coturn", 40)
brun("ss -lunp 2>/dev/null | grep 3478 || echo '3478 未监听'; echo '--- proc ---'; pgrep -af turnserver || echo '进程未起'", "验证 3478 监听", 30)

board.close()
print("\n===== 完成 =====")
