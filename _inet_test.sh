echo '== temp route to 8.8.8.8 via wlan0 gateway =='
sudo ip route add 8.8.8.8/32 via 192.168.2.1 dev wlan0 2>/dev/null
echo '== ping 8.8.8.8 via wlan0 src =='
ping -c 3 -I 192.168.2.14 8.8.8.8 2>&1 | tail -4
echo '== DNS resolution now? =='
getent hosts stun.l.google.com 2>&1 && echo 'DNS OK' || echo 'DNS still failing'
echo '== remove temp route =='
sudo ip route del 8.8.8.8/32 via 192.168.2.1 dev wlan0 2>/dev/null
echo 'done'
