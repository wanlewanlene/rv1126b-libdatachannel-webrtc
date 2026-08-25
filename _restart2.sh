echo elf | sudo -S ip route del default via 192.168.0.1 dev eth0 2>/dev/null
echo '== route after fix =='
ip route show default
echo '== internet check =='
ping -c 2 -I 192.168.2.14 8.8.8.8 2>&1 | tail -3
echo '== stop old =='
pkill -9 -f rv1126b_webrtc_push 2>/dev/null
pkill -9 -f WebSocket.js 2>/dev/null
fuser -k /dev/video52 2>/dev/null
sleep 2
echo '== start run.sh =='
cd /userdata/rtc
setsid bash /userdata/rtc/run.sh > /userdata/rtc/run.log 2>&1 < /dev/null &
disown 2>/dev/null || true
sleep 6
echo '== procs =='
ps aux | grep -E 'rv1126b_webrtc_push|WebSocket.js' | grep -v grep
echo '== log tail =='
tail -15 /userdata/rtc/run.log
