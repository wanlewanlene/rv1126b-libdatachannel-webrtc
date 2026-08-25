echo '== procs alive? =='
ps aux | grep -E 'rv1126b_webrtc_push|WebSocket.js' | grep -v grep
PID=$(pgrep -f rv1126b_webrtc_push | head -1)
echo "PID=$PID"
echo '== fd count =='
sudo bash -c "ls /proc/$PID/fd 2>/dev/null | wc -l"
echo '== RTC state transitions (ordered) =='
grep -nE '\[RTC\] state|gathering state|remote description|connected|disconnected|failed|viewer|answer|ice' /userdata/rtc/run.log | tail -50
echo '== juice/ICE detailed log (consent, connectivity, send) =='
grep -iE 'juice|consent|connectivity|nominat|send|error|timeout|keepalive|failure' /userdata/rtc/run.log | tail -40
echo '== full tail =='
tail -40 /userdata/rtc/run.log
