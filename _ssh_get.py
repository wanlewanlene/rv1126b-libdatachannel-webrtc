import sys, paramiko
HOST="192.168.2.14"; PORT=22; USER="elf"; PASS="elf"
c=paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST,port=PORT,username=USER,password=PASS,timeout=15)
sftp=c.open_sftp()
remote=sys.argv[1]; local=sys.argv[2]
sftp.get(remote, local)
print("get ok")
c.close()