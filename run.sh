#!/bin/bash
# RV1126B WebRTC 推流启动脚本
export LD_LIBRARY_PATH=/userdata/rtc/lib:$LD_LIBRARY_PATH

# 修复默认路由：eth0 的网关 192.168.0.1 不可达，会让板卡无法上公网，
# 导致 STUN 解析失败、拿不到 srflx 候选，WebRTC 无法与浏览器联通。
# 删除该无效默认路由，使流量走 wlan0(192.168.2.1, 可达) 出网。
echo elf | sudo -S ip route del default via 192.168.0.1 dev eth0 2>/dev/null || true

echo "==> 启动信令服务器 ..."
cd /userdata/rtc/server && node WebSocket.js &
sleep 2
echo "==> 启动推流程序 ..."
cd /userdata/rtc/bin && ./rv1126b_webrtc_push
