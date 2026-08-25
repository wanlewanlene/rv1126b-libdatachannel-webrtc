echo '== default route =='
ip route show default
echo '== all routes =='
ip route show
echo '== resolv.conf =='
cat /etc/resolv.conf 2>&1
echo '== gateway ping (assume 192.168.2.1 / 192.168.0.1) =='
for g in 192.168.2.1 192.168.0.1 192.168.2.14 192.168.0.232; do
  ping -c 1 -W 1 $g >/dev/null 2>&1 && echo "reachable: $g" || echo "unreachable: $g"
done
echo '== try DNS resolution with explicit server =='
getent hosts 8.8.8.8 >/dev/null 2>&1 && echo '8.8.8.8 resolvable-as-host'
nslookup stun.l.google.com 8.8.8.8 2>&1 | head -8 || echo 'nslookup not available'
echo '== can board reach a public IP? =='
ping -c 2 -W 1 8.8.8.8 2>&1 | tail -3
echo '== iptables (board firewall) =='
sudo iptables -L -n 2>&1 | head -10
