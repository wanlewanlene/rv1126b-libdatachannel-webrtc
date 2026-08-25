echo '== main.cpp around send()/onStateChange/track callbacks =='
grep -n 'void send\|onStateChange\|onOpen\|onMessage\|onClosed\|addTrack\|createTrack\|packetizer\|Rtcp\|rtcp\|PLI\|pli\|onFrame' /userdata/rtc/main.cpp
echo '=================== full WebRTCStreamer section ==================='
# 打印 WebRTCStreamer 类从 class 开始到结尾
awk '/class WebRTCStreamer/,/^};/' /userdata/rtc/main.cpp | head -220
