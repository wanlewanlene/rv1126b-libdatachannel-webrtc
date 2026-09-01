#!/bin/bash
# RV1126B WebRTC 推流启动脚本
export LD_LIBRARY_PATH=/userdata/rtc/lib:$LD_LIBRARY_PATH

# 修复默认路由：eth0 的网关 192.168.0.1 不可达，会让板卡无法上公网，
# 导致 STUN 解析失败、拿不到 srflx 候选，WebRTC 无法与浏览器联通。
# 删除该无效默认路由，使流量走 wlan0(192.168.2.1, 可达) 出网。
echo elf | sudo -S ip route del default via 192.168.0.1 dev eth0 2>/dev/null || true

# 音频增益固化: 板载 MIC 数字/模拟增益 (防板卡重启后恢复默认 -95dB 导致音量过小)
amixer -c 0 sset 'ACodec_LP Digital Gain' 110 >/dev/null 2>&1
amixer -c 0 sset 'ACodec_LP PGA Gain' 100% >/dev/null 2>&1

# 本机 TURN 服务器 (低延迟中继): 浏览器同网段直连板卡 3478,
# 避免走公网 srflx NAT 回环 (700ms 高延迟不稳定 -> 毫秒级本机回环)
if ! pgrep -f '[t]urnserver' >/dev/null; then
    nohup turnserver -c /etc/turnserver.conf > /tmp/turn.log 2>&1 &
    sleep 1
fi

echo "==> 启动信令服务器 ..."
cd /userdata/rtc/server && node WebSocket.js &
sleep 2
echo "==> 启动推流程序 ..."
cd /userdata/rtc/bin && ./rv1126b_webrtc_push
