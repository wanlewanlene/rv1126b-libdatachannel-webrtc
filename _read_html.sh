echo '== grep ipInput / ws usage in Browser_client.html =='; grep -nE "ipInput|ws://|WebSocket|location.host|192.168" /userdata/rtc/server/Browser_client.html | head -30
