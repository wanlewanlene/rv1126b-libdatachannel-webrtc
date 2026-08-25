echo '== pid of push =='; pgrep -f rv1126b_webrtc_push
PID=$(pgrep -f rv1126b_webrtc_push | head -1)
echo "PID=$PID"
echo '== Max open files limit =='; echo elf | sudo -S cat /proc/$PID/limits 2>/dev/null | grep -i "open files"
echo '== current fd count =='; echo elf | sudo -S bash -c "ls /proc/$PID/fd 2>/dev/null | wc -l"
echo '== fd types breakdown (first 60) =='; echo elf | sudo -S bash -c "ls -l /proc/$PID/fd 2>/dev/null | sed 's/.* -> //' | sed 's:/dev/:\n/dev/:' | awk '{print}' | head -60"
echo '== count fd by category =='; echo elf | sudo -S bash -c "ls -l /proc/$PID/fd 2>/dev/null" | grep -oE 'socket:\[[0-9]+\]|pipe:\[[0-9]+\]|/dev/.*|anon_inode.*|/userdata/.*' | sed -E 's:\[[0-9]+\]::' | sort | uniq -c | sort -rn | head -20
echo '== process RSS/VSZ =='; echo elf | sudo -S cat /proc/$PID/status 2>/dev/null | grep -E "VmRSS|VmSize|FDSize"
echo '== global ulimit default (elf) =='; ulimit -n
