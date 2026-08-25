echo '== kill stale push/node =='
pkill -9 -f rv1126b_webrtc_push 2>/dev/null; pkill -9 -f WebSocket.js 2>/dev/null
fuser -k /dev/video52 2>/dev/null || true
sleep 2
echo '== camera free? =='; fuser /dev/video52 2>&1 || echo 'camera free'
echo '== start run.sh (detached) =='
cd /userdata/rtc
setsid bash /userdata/rtc/run.sh > /userdata/rtc/run.log 2>&1 < /dev/null &
disown 2>/dev/null || true
echo "launched, waiting 12s..."
sleep 12
echo '== procs =='; ps aux | grep -E 'rv1126b_webrtc_push|WebSocket.js' | grep -v grep
echo '== run.log tail =='; tail -45 /userdata/rtc/run.log
echo '== bin/push.log tail =='; tail -30 /userdata/rtc/bin/push.log 2>&1
echo '== node listen ports =='; (ss -ltnp 2>/dev/null || netstat -ltnp 2>/dev/null) | grep -E '3000|8080' || echo 'no 3000/8080 listener'
