echo '== /var/log breakdown (top) =='; echo elf | sudo -S du -sh /var/log/* 2>/dev/null | sort -h | tail -20
echo '== /root contents =='; echo elf | sudo -S du -sh /root/* 2>/dev/null | sort -h | tail -25
echo '== /elf-env contents =='; echo elf | sudo -S du -sh /elf-env/* 2>/dev/null | sort -h | tail -20
echo '== biggest files overall in / (excl /userdata /proc /sys /dev) =='; echo elf | sudo -S find / -xdev -type f -size +50M -exec du -h {} + 2>/dev/null | sort -h | tail -30
