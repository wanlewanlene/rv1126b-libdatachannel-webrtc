// ============================================================================
// RV1126B WebRTC 信令服务器 (room-based)
// HTTP 端口: 3000   WebSocket 端口: 8080
//
// 协议:
//   推流端(C++):  {"type":"streamer_join","room":"cam1"}
//                 {"type":"offer","room":"cam1","sdp":"<sdp>"}
//                 {"type":"ice","room":"cam1","candidate":"...","mid":"0"}
//   播放端(浏览器): {"type":"viewer_join","room":"cam1"}
//                 {"type":"answer","room":"cam1","sdp":"<sdp>"}
//                 {"type":"ice","room":"cam1","candidate":"...","mid":"0"}
// ============================================================================

const express = require('express');
const WebSocket = require('ws');

const app = express();
const HTTP_PORT = 3000;
const WS_PORT = 8080;

// room -> { streamer: ws, viewers: Set<ws> }
const rooms = new Map();

const wss = new WebSocket.Server({ port: WS_PORT });

function send(ws, obj) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(obj));
    }
}

wss.on('connection', (ws) => {
    ws.room = null;
    ws.role = null;
    try { console.log(`[conn] client IP=${ws._socket.remoteAddress}`); } catch (e) {}

    ws.on('message', (raw) => {
        let msg;
        try {
            msg = JSON.parse(raw.toString());
        } catch (e) {
            return;
        }

        const room = ws.room ? rooms.get(ws.room) : null;
        console.log(`[recv] role=${ws.role} room=${ws.room} type=${msg.type}`);
        if (msg.candidate) console.log(`       candidate: ${msg.candidate}`);
        if (msg.sdp) {
            const n = (msg.sdp.match(/a=candidate/g) || []).length;
            console.log(`       sdp candidate lines: ${n}`);
        }

        switch (msg.type) {
            case 'streamer_join': {
                ws.room = msg.room;
                ws.role = 'streamer';
                if (!rooms.has(msg.room)) {
                    rooms.set(msg.room, { streamer: null, viewers: new Set() });
                }
                rooms.get(msg.room).streamer = ws;
                console.log(`[streamer] joined room ${msg.room}`);
                break;
            }
            case 'viewer_join': {
                ws.room = msg.room;
                ws.role = 'viewer';
                if (!rooms.has(msg.room)) {
                    rooms.set(msg.room, { streamer: null, viewers: new Set() });
                }
                rooms.get(msg.room).viewers.add(ws);
                console.log(`[viewer] joined room ${msg.room}`);
                // 通知推流端重新发送 offer (解决时序: viewer 后加入)
                const streamer = rooms.get(msg.room).streamer;
                if (streamer) {
                    send(streamer, { type: 'request_offer' });
                }
                break;
            }
            case 'offer': {
                // 正向推流: 推流端(streamer)的 offer -> 所有播放端(viewers)
                // 反向推流: 板卡(viewer)的 offer -> 浏览器(streamer)
                if (room) {
                    if (ws.role === 'viewer') {
                        if (room.streamer) send(room.streamer, msg);
                        console.log('[offer] viewer->streamer forwarded');
                    } else {
                        console.log(`[offer] forwarding to ${room.viewers.size} viewers`);
                        room.viewers.forEach((v) => send(v, msg));
                    }
                } else {
                    console.log('[offer] no room!');
                }
                break;
            }
            case 'answer': {
                // 正向推流: 播放端(viewer)的 answer -> 推流端(streamer)
                // 反向推流: 浏览器(streamer)的 answer -> 板卡(viewer)
                if (room) {
                    if (ws.role === 'streamer') {
                        room.viewers.forEach((v) => send(v, msg));
                        console.log('[answer] streamer->viewers forwarded');
                    } else if (room.streamer) {
                        send(room.streamer, msg);
                        console.log('[answer] viewer->streamer forwarded');
                    }
                }
                break;
            }
            case 'adjust': {
                // 播放端 -> 推流端: 监测面板自动优化指令 (动态码率)
                if (room && room.streamer) send(room.streamer, msg);
                break;
            }
            case 'request_offer': {
                // 反向推流: 浏览器(streamer)请求板卡(viewer)生成 offer
                if (room) room.viewers.forEach((v) => send(v, msg));
                break;
            }
            case 'ice': {
                // 转发给对端
                if (!room) break;
                if (ws.role === 'streamer') {
                    room.viewers.forEach((v) => send(v, msg));
                } else if (room.streamer) {
                    send(room.streamer, msg);
                }
                break;
            }
        }
    });

    ws.on('close', () => {
        if (!ws.room) return;
        const room = rooms.get(ws.room);
        if (!room) return;
        if (ws.role === 'streamer') {
            if (room.streamer === ws) room.streamer = null;
        } else {
            room.viewers.delete(ws);
        }
        if (!room.streamer && room.viewers.size === 0) {
            rooms.delete(ws.room);
        }
    });
});

// 静态文件服务: 浏览器直接访问 http://板卡IP:3000/ 即可打开播放页面
const path = require('path');
app.use(express.static(__dirname));

app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'Browser_client.html'));
});

app.listen(HTTP_PORT, () => {
    console.log(`Signaling server: HTTP ${HTTP_PORT}, WebSocket ${WS_PORT}`);
    console.log(`浏览器访问 http://<板卡IP>:${HTTP_PORT}/ 查看视频`);
});
