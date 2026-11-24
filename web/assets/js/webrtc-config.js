/* ============================================================================
 * WebRTC 公共配置（三个页面共用）
 *   Browser_client.html / Dual_webrtc.html / Reverse_pusher.html
 *
 * 暴露：
 *   WEBRTC_CFG            常量表（STUN/TURN/默认板卡 IP）
 *   iceServers(boardIp)   返回 RTCPeerConnection 的 iceServers 数组
 *   signalingUrl(ip, port) 返回信令 URL（HTTPS 隧道下自动走同源 /ws）
 * ==========================================================================*/
(function () {
    'use strict';

    var CFG = {
        STUN: 'stun:stun.l.google.com:19302',
        DEFAULT_BOARD_IP: '192.168.137.184',
        TURN_PORT: 3478,
        TURN_USER: 'webrtc',
        TURN_CRED: 'webrtc123'
    };

    window.WEBRTC_CFG = CFG;

    window.iceServers = function (boardIp) {
        return [
            { urls: CFG.STUN },
            {
                urls: 'turn:' + (boardIp || CFG.DEFAULT_BOARD_IP) + ':' + CFG.TURN_PORT,
                username: CFG.TURN_USER,
                credential: CFG.TURN_CRED
            }
        ];
    };

    window.signalingUrl = function (ip, port) {
        // 经 HTTPS 隧道（外网）访问时：信令走同源 /ws（由 3000 端口提供）
        if (location.protocol === 'https:') {
            return 'wss://' + location.host + '/ws';
        }
        return 'ws://' + ip + ':' + port;
    };
})();
