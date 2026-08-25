echo '== board interfaces / IPs =='
ip -o -4 addr show 2>/dev/null | awk '{print $2, $4}'
echo '== board -> browser(192.168.2.9) ping test (wired isolation check) =='
ping -c 3 -W 1 192.168.2.9 2>&1 | tail -5
echo '== browser client seen by WS =='
grep -i 'client IP' /userdata/rtc/run.log | tail -3
echo '== coturn binary? =='
ls -l /userdata/coturn/turnserver 2>&1 | head -1
ls -l /usr/bin/turnserver /usr/local/bin/turnserver 2>&1 | head -3
echo '== turnserver.conf =='
cat /etc/turnserver.conf 2>&1 | grep -vE '^\s*#|^\s*$' | head -40
echo '== is coturn running? =='
pgrep -a turnserver 2>&1 | head -3 || echo 'NOT running'
echo '== port 3478 listen? =='
(ss -tlnp 2>/dev/null; ss -ulnp 2>/dev/null) | grep 3478 || echo '3478 not listening'
echo '== board has internet? (STUN dns) =='
getent hosts stun.l.google.com 2>&1 || echo 'NO dns for stun'
