echo '== df -h =='; df -h
echo '== df -h / /tmp /var =='; df -h / /tmp /var /var/log 2>&1
echo '== du top dirs under / (depth1) =='; echo elf | sudo -S du -sh /* 2>/dev/null | sort -h | tail -25
echo '== /var/log size =='; echo elf | sudo -S du -sh /var/log 2>/dev/null
echo '== /var/cache/apt =='; echo elf | sudo -S du -sh /var/cache/apt 2>/dev/null
echo '== /tmp size =='; echo elf | sudo -S du -sh /tmp 2>/dev/null
echo '== journal size =='; echo elf | sudo -S journalctl --disk-usage 2>&1
echo '== apt lists =='; echo elf | sudo -S du -sh /var/lib/apt/lists 2>/dev/null
