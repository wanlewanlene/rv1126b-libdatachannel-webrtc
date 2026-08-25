import paramiko

HOST = "192.168.2.2"
PORT = 22
USER = "elf"
PASS = "elf"

def run(cmd, timeout=60):
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, port=PORT, username=USER, password=PASS, timeout=15)
    stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    c.close()
    return out, err

if __name__ == "__main__":
    cmds = [
        ("=== hostname/whoami ===", "hostname; whoami; uname -a"),
        ("=== find *.img (maxdepth8) ===", "find / -maxdepth 8 -name '*.img' 2>/dev/null | head -n 20"),
        ("=== find rootfs* under HOME ===", "find ~ -maxdepth 5 -iname 'rootfs*' 2>/dev/null | head -n 30"),
        ("=== ls ~/work ===", "ls -la ~/work 2>/dev/null"),
        ("=== df -h ===", "df -h / /home /mnt 2>/dev/null; echo '---'; df -h | head"),
        ("=== losetup available? ===", "which losetup mount; ls /dev/loop* 2>/dev/null | head"),
    ]
    for title, cmd in cmds:
        print(title)
        out, err = run(cmd)
        print(out)
        if err.strip():
            print("--- STDERR ---")
            print(err)
        print()
