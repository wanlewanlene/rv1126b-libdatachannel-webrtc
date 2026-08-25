import paramiko, time, sys, socket
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

vm = paramiko.SSHClient()
vm.set_missing_host_key_policy(paramiko.AutoAddPolicy())
vm.connect('192.168.2.5', port=22, username='elf', password='elf', timeout=15)
shell = vm.invoke_shell()
shell.settimeout(8)
time.sleep(1)

def run(cmd, wait=3):
    shell.send(cmd + '\n')
    time.sleep(wait)
    data = ''
    while True:
        try:
            chunk = shell.recv(65536)
            if not chunk: break
            data += chunk.decode(errors='replace')
        except socket.timeout:
            break
        except Exception:
            break
    return data

run('', 1)  # 清欢迎
def show(title, out):
    print(f"\n########## [VM] {title} ##########")
    print(out.strip())

show('架构/系统', run('uname -m; . /etc/os-release; echo OS=$PRETTY_NAME', 3))
show('coturn 现状', run('which turnserver; ls /usr/bin/turn* 2>/dev/null; dpkg -l 2>/dev/null | grep -i coturn', 3))
show('apt 可用性', run('apt-get --version 2>&1 | head -1; timeout 12 apt-cache policy coturn 2>&1 | head -8', 8))
show('网络', run("ip -4 addr | grep -E 'inet '; ip route | head -2", 3))

vm.close()
print("\n===== 完成 =====")
