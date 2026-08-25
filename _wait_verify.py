import paramiko, time, sys

HOST="192.168.2.14"; PORT=22; USER="elf"; PASS="elf"

def connect():
    c=paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST,port=PORT,username=USER,password=PASS,timeout=8)
    return c

# wait for SSH up to 120s
up=False
for i in range(40):
    try:
        c=connect(); up=True; c.close(); break
    except Exception as e:
        time.sleep(3)
if not up:
    print("SSH NOT UP after wait"); sys.exit(1)
print("SSH UP after ~%ds" % (i*3))

# give lightdm a moment
time.sleep(8)

c=connect()
cmd = (
"echo '== lightdm active =='; systemctl is-active lightdm; "
"echo '== disk / =='; df -h / | tail -1; "
"echo '== desktop procs =='; ps -u elf -o comm | grep -E 'lxsession|openbox|lxpanel|pcmanfm' | sort -u; "
"echo '== DSI =='; cat /sys/class/drm/card0-DSI-1/status; "
"echo '== backlight =='; cat /sys/class/backlight/backlight-dsi/brightness; "
"echo '== Xorg =='; pgrep -a Xorg"
)
stdin,stdout,stderr=c.exec_command(cmd,timeout=30)
print(stdout.read().decode(errors='replace'))
err=stderr.read().decode(errors='replace')
if err.strip(): print("ERR:",err)
c.close()
