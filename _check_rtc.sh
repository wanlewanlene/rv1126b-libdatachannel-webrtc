echo '== procs =='
ps aux | grep -E 'rv1126b_webrtc_push|WebSocket.js' | grep -v grep
PID=$(pgrep -f rv1126b_webrtc_push | head -1)
echo "PID=$PID"
echo '== fd count (fixed => low) =='
sudo bash -c "ls /proc/$PID/fd 2>/dev/null | wc -l"
echo '== dmabuf fd count =='
sudo bash -c "ls -l /proc/$PID/fd 2>/dev/null | grep -c dmabuf"
echo '== RTC / signaling recent log =='
grep -iE 'state:|RTC|recv|viewer|ICE|answer|connected|conn|frame|send' /userdata/rtc/run.log | tail -40
echo '== full tail =='
tail -25 /userdata/rtc/run.log
