echo '== stop old =='
pkill -9 -f rv1126b_webrtc_push 2>/dev/null; pkill -9 -f WebSocket.js 2>/dev/null
fuser -k /dev/video52 2>/dev/null || true
sleep 2
echo '== swap binary =='
cd /userdata/rtc/bin
mv -f rv1126b_webrtc_push rv1126b_webrtc_push.bak 2>/dev/null
mv -f rv1126b_webrtc_push.new rv1126b_webrtc_push
ls -l rv1126b_webrtc_push
echo '== start run.sh =='
cd /userdata/rtc
setsid bash /userdata/rtc/run.sh > /userdata/rtc/run.log 2>&1 < /dev/null &
disown 2>/dev/null || true
echo "waiting 20s for fd-leak check..."
sleep 20
echo '== procs =='; ps aux | grep -E 'rv1126b_webrtc_push|WebSocket.js' | grep -v grep
PID=$(pgrep -f rv1126b_webrtc_push | head -1)
echo "PID=$PID"
echo '== fd count (fixed => should stay low, NOT ~1024) =='; echo elf | sudo -S bash -c "ls /proc/$PID/fd 2>/dev/null | wc -l"
echo '== dmabuf fd count (fixed => should be small) =='; echo elf | sudo -S bash -c "ls -l /proc/$PID/fd 2>/dev/null | grep -c dmabuf"
echo '== run.log tail =='; tail -30 /userdata/rtc/run.log
