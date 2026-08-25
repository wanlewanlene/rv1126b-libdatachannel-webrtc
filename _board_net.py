import paramiko, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

board = paramiko.SSHClient()
board.set_missing_host_key_policy(paramiko.AutoAddPolicy())
board.connect('192.168.2.14', port=22, username='elf', password='elf', timeout=15)

def brun(cmd, title, timeout=60):
    print(f"\n########## [BOARD] {title} ##########")
    stdin, stdout, stderr = board.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors='replace'); err = stderr.read().decode(errors='replace')
    if out: print(out)
    if err: print("[STDERR]", err)

brun("dpkg --print-architecture; echo '--- os ---'; . /etc/os-release; echo $PRETTY_NAME", "架构/系统", 20)
brun("cat /etc/apt/sources.list 2>/dev/null | grep -vE '^#|^$'; echo '--- list.d ---'; ls /etc/apt/sources.list.d/ 2>/dev/null", "apt 源", 20)
brun("apt-get --version 2>&1 | head -1", "apt 版本", 20)
brun("timeout 15 curl -sI http://deb.debian.org/debian/dists/bookworm/ 2>&1 | head -5; echo 'EXIT_CURL=$?'", "Debian 源 HTTP 连通性", 25)
brun("apt-cache policy coturn 2>&1 | head -6", "coturn 包可用性", 20)

board.close()
print("\n===== 完成 =====")
