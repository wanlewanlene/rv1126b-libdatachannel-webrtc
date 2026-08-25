echo '== live run.log tail (RTC state / send) =='; tail -40 /userdata/rtc/run.log
echo '== sig.log tail =='; tail -20 /userdata/rtc/server/sig.log 2>&1
echo '== procs =='; ps aux | grep -E 'rv1126b_webrtc_push|WebSocket.js' | grep -v grep
echo '== any viewer connected? (grep room) =='; grep -iE "viewer|join|offer|answer|state" /userdata/rtc/run.log | tail -15
