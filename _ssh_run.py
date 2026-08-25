import sys, paramiko

HOST = "192.168.2.14"
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
    cmd = sys.argv[1] if len(sys.argv) > 1 else "echo ok"
    out, err = run(cmd)
    print(out)
    if err.strip():
        print("--- STDERR ---")
        print(err)
