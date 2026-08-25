import sys, paramiko
HOST="192.168.2.14"; USER="elf"; PASS="elf"
c=paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST,22,USER,PASS,timeout=15)
cmds=[
 ("*.img files", "find / -maxdepth 8 -name '*.img' 2>/dev/null | head -n 20"),
 ("rootfs dirs", "find / -maxdepth 6 -type d -iname 'rootfs*' 2>/dev/null | head -n 20"),
 ("~/work", "ls -la /home/elf/work 2>/dev/null; echo '---'; ls -la ~/work 2>/dev/null"),
 ("df -h", "df -h / /home /userdata 2>/dev/null"),
 ("loop mounts", "mount | grep -E 'loop|rootfs' "),
]
for t,cmd in cmds:
    print("===",t,"===")
    stdin,stdout,stderr=c.exec_command(cmd,timeout=40)
    sys.stdout.write(stdout.read().decode(errors='replace'))
    e=stderr.read().decode(errors='replace')
    if e.strip(): sys.stdout.write("ERR: "+e+"\n")
    sys.stdout.flush()
c.close()
