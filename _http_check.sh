echo '== HTTP 3000 status =='; curl -s -o /dev/null -w "HTTP %{http_code}\n" http://127.0.0.1:3000/ 2>&1
echo '== page has video tag? =='; curl -s http://127.0.0.1:3000/ 2>&1 | grep -iE "video|<title>|websocket|192.168" | head -8
echo '== WebSocket 8080 reachable (node pid) =='; ss -ltnp 2>/dev/null | grep -E '3000|8080'
echo '== current RTC/push live log tail =='; tail -15 /userdata/rtc/run.log
