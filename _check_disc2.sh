echo '== procs alive? =='
ps aux | grep -E 'rv1126b_webrtc_push|WebSocket.js' | grep -v grep
PID=$(pgrep -f rv1126b_webrtc_push | head -1)
echo "PID=$PID"
echo '== which libs loaded (verify new .so) =='
sudo bash -c "ls -l /proc/$PID/map_files 2>/dev/null | grep -oE '/[^ ]*lib(datachannel|srtp)[^ ]*' | sort -u"
echo '== fd count =='
sudo bash -c "ls /proc/$PID/fd 2>/dev/null | wc -l"
echo '== last 60 lines of run.log (binary-safe) =='
strings /userdata/rtc/run.log | tail -60
echo '== key errors =='
strings /userdata/rtc/run.log | grep -iE 'ERROR|SRTP|DTLS|state:|disconn|failed|timeout|alert' | tail -30
