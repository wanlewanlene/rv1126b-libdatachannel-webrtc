echo '== stop old =='
pkill -9 -f rv1126b_webrtc_push 2>/dev/null
pkill -9 -f WebSocket.js 2>/dev/null
fuser -k /dev/video52 2>/dev/null
sleep 2
echo '== ensure route (internet) =='
echo elf | sudo -S ip route del default via 192.168.0.1 dev eth0 2>/dev/null || true
ip route show default
echo '== start run.sh =='
cd /userdata/rtc
setsid bash /userdata/rtc/run.sh > /userdata/rtc/run.log 2>&1 < /dev/null &
disown 2>/dev/null || true
sleep 6
echo '== procs =='
ps aux | grep -E 'rv1126b_webrtc_push|WebSocket.js' | grep -v grep
echo '== which libdatachannel.so loaded =='
PID=$(pgrep -f rv1126b_webrtc_push | head -1)
echo "push PID=$PID"
sudo bash -c "ls -l /proc/$PID/map_files 2>/dev/null | grep -oE '/[^ ]*libdatachannel[^ ]*|/[^ ]*libsrtp[^ ]*' | sort -u"
echo '== log tail =='
tail -18 /userdata/rtc/run.log
