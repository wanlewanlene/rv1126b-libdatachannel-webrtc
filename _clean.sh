echo '== df BEFORE =='; df -h / | tail -1
echo '== 1) vacuum journal to 50M =='; echo elf | sudo -S journalctl --vacuum-size=50M 2>&1 | tail -3
echo '== 2) remove rotated/compressed old logs =='; echo elf | sudo -S find /var/log -type f \( -name '*.gz' -o -name '*.1' -o -name '*.2' -o -name '*.old' -o -name '*.log.old' \) -delete 2>/dev/null; echo done
echo '== 3) truncate active big logs (restart rsyslog first to release fd) =='
echo elf | sudo -S systemctl restart rsyslog 2>/dev/null || true
echo elf | sudo -S truncate -s 0 /var/log/syslog /var/log/kern.log /var/log/user.log /var/log/auth.log /var/log/daemon.log /var/log/messages 2>/dev/null
echo 'truncated'
echo '== 4) pip cache =='; echo elf | sudo -S rm -rf /root/.cache/pip 2>/dev/null; echo done
echo '== 5) libdatachannel .git (already compiled/installed) =='; echo elf | sudo -S rm -rf /root/libdatachannel/.git 2>/dev/null; echo done
echo '== 6) apt cache =='; echo elf | sudo -S rm -rf /var/lib/apt/lists/* 2>/dev/null; echo elf | sudo -S rm -rf /var/cache/apt/archives/* 2>/dev/null; echo done
echo '== sync =='; echo elf | sudo -S sync
echo '== df AFTER =='; df -h / | tail -1
echo '== avail now =='; df -m / | tail -1
