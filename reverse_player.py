#!/usr/bin/env python3

# -*- coding: utf-8 -*-

"""

RV1126B 板卡端: 接收浏览器反向推流 (WebRTC) 并实时播放

架构: 浏览器(摄像头+麦克风) --H.264/VP8+Opus RTP--> 板卡 GStreamer webrtcbin

      --> mppvideodec 硬解 --> rkximagesink 显示到 MIPI 屏 (X :0 窗口)

      --> opusdec --> ALSA 喇叭播放

信令: 复用现有 Node 信令 (room=reverse1), 本端以 viewer 角色加入 (answerer)



运行:

  1) sudo apt install -y python3-websocket

  2) DISPLAY=:0 python3 reverse_player.py [信令地址] [房间]

     (X :0 为 elf 用户的 lightdm 会话; 若以其他用户运行需配 XAUTHORITY)

"""

import sys, json, threading

import gi

gi.require_version('Gst', '1.0')

gi.require_version('GstWebRTC', '1.0')

gi.require_version('GstSdp', '1.0')

from gi.repository import Gst, GstWebRTC, GstSdp, GLib

import websocket  # python3-websocket (websocket-client)



SIGNALING = sys.argv[1] if len(sys.argv) > 1 else 'ws://127.0.0.1:8080'

ROOM      = sys.argv[2] if len(sys.argv) > 2 else 'reverse1'

# MIPI 屏 1024x600; 若改变分辨率只需改这里 (0=跟随视频原始尺寸)

OUT_W = 1024

OUT_H = 600



webrtc = None

loop = GLib.MainLoop()

ws_sock = None





def send_signal(obj):

    if ws_sock and ws_sock.sock and ws_sock.sock.connected:

        ws_sock.send(json.dumps(obj))





def build_media_chain(media, encoding):

    """根据 RTP caps 构建视频/音频解码播放链, 返回 Gst.Bin"""

    if media == 'video':

        if encoding == 'H264':

            desc = (f'rtpjitterbuffer latency=0 ! rtph264depay ! h264parse '

                    f'! mppvideodec ! videoconvert ! videoscale '

                    f'! video/x-raw,width={OUT_W},height={OUT_H} '

                    f'! rkximagesink sync=false')

        elif encoding == 'VP8':

            desc = (f'rtpjitterbuffer latency=0 ! rtpvp8depay '

                    f'! mppvideodec ! videoconvert ! videoscale '

                    f'! video/x-raw,width={OUT_W},height={OUT_H} '

                    f'! rkximagesink sync=false')

        elif encoding == 'VP9':

            desc = (f'rtpjitterbuffer latency=0 ! rtpvp9depay '

                    f'! mppvideodec ! videoconvert ! videoscale '

                    f'! video/x-raw,width={OUT_W},height={OUT_H} '

                    f'! rkximagesink sync=false')

        else:

            print(f'[video] 不支持的编码 {encoding}, 尝试通用 depay')

            desc = (f'rtpjitterbuffer latency=0 ! rtpjitterbuffer latency=0 '

                    f'! decodebin ! videoconvert ! videoscale '

                    f'! video/x-raw,width={OUT_W},height={OUT_H} '

                    f'! rkximagesink sync=false')

    elif media == 'audio':

        if encoding == 'OPUS':

            desc = ('rtpjitterbuffer latency=0 ! rtpopusdepay ! opusdec '

                    '! audioconvert ! audioresample '

                    '! autoaudiosink sync=false')

        else:

            print(f'[audio] 不支持的编码 {encoding}, 尝试 decodebin')

            desc = ('rtpjitterbuffer latency=0 ! decodebin '

                    '! audioconvert ! audioresample ! autoaudiosink sync=false')

    else:

        print(f'[warn] 未知 media: {media}')

        return None

    try:

        return Gst.parse_bin_from_description(desc, True)

    except Exception as e:

        print(f'[err] 构建链路失败: {e}')

        return None





def on_pad_added(element, pad):

    caps = pad.get_current_caps()

    if caps is None:

        caps = pad.query_caps(None)

    if caps is None or caps.get_size() == 0:

        print('[pad] 无 caps, 忽略')

        return

    s = caps.get_structure(0)

    name = s.get_name()

    if not name.startswith('application/x-rtp'):

        print(f'[pad] 非 RTP pad: {name}')

        return

    media = s.get_string('media') or ''

    encoding = s.get_string('encoding-name') or ''

    print(f'[pad] 新增媒体流: media={media} encoding={encoding}')

    if media not in ('video', 'audio'):

        return



    bin = build_media_chain(media, encoding)

    if bin is None:

        return

    sinkpad = bin.get_static_pad('sink')

    if sinkpad is None:

        print('[err] 无法获取链的 sink pad')

        return

    pipeline = webrtc.get_parent()

    pipeline.add(bin)

    bin.sync_state_with_parent()

    res = pad.link(sinkpad)

    if res != Gst.PadLinkReturn.OK:

        print(f'[err] pad link 失败: {res}')

    else:

        print(f'[{media}] 播放链已启动 ({encoding})')





def on_answer_created(promise, *args):

    result = promise.wait()

    print(f'[diag] create-answer result: {result}')

    reply = promise.get_reply()

    if reply is None:

        print('[err] create-answer 无 reply')

        return

    print(f'[diag] reply: {reply.to_string()}')

    answer = reply.get_value('answer')

    if answer is None:

        print('[err] create-answer 未生成 answer')

        return

    # set-local-description

    p2 = Gst.Promise.new()

    webrtc.emit('set-local-description', answer, p2)

    p2.interrupt()

    # 回发 answer

    send_signal({'type': 'answer', 'room': ROOM, 'sdp': answer.sdp.as_text()})

    print('[sig] answer 已发送')





def on_remote_desc_set(promise, *args):

    result = promise.wait()

    print(f'[diag] set-remote-description result: {result}')

    try:

        state = webrtc.get_property('signaling-state')

        print(f'[diag] signaling-state: {state}')

    except Exception as e:

        print(f'[warn] 读取 signaling-state: {e}')

    pa = Gst.Promise.new_with_change_func(on_answer_created)

    webrtc.emit('create-answer', None, pa)

    print('[diag] create-answer 已触发')




def handle_offer(sdp_text):

    print('[sig] 收到 offer, 建立会话...')

    try:

        ret, sdp = GstSdp.SDPMessage.new_from_text(sdp_text)

        offer = GstWebRTC.WebRTCSessionDescription.new(

            GstWebRTC.WebRTCSDPType.OFFER, sdp)

    except Exception as e:

        print(f'[err] SDP 解析失败: {e}')

        return

    p = Gst.Promise.new_with_change_func(on_remote_desc_set)

    webrtc.emit('set-remote-description', offer, p)





def handle_ice(candidate, mline):

    if not candidate:

        return

    try:

        try:

            mline = int(mline)

        except Exception:

            mline = 0

        webrtc.emit('add-ice-candidate', mline, candidate)

    except Exception as e:

        print(f'[err] add-ice-candidate: {e}')





def on_ws_message(ws, message):

    try:

        msg = json.loads(message)

    except Exception:

        return

    t = msg.get('type')

    if t == 'offer':

        GLib.idle_add(handle_offer, msg.get('sdp', ''))

    elif t == 'ice':

        c = msg.get('candidate')

        cand_str = c.get('candidate') if isinstance(c, dict) else c

        mline = msg.get('sdpMLineIndex', msg.get('mline'))

        if mline is None and isinstance(c, dict):

            mline = c.get('sdpMLineIndex')

        GLib.idle_add(handle_ice, cand_str or '', mline)





def on_ws_open(ws):

    print('[sig] websocket 已连接, 加入房间', ROOM)

    ws.send(json.dumps({'type': 'viewer_join', 'room': ROOM}))





def main():

    global webrtc, ws_sock

    Gst.init(None)

    print(f'[init] 启动反向播放器  room={ROOM}  signaling={SIGNALING}')

    print(f'[init] 显示输出 {OUT_W}x{OUT_H} (rkximagesink, 需 DISPLAY)')



    # Pipeline: 仅 webrtcbin, 媒体链在 pad-added 时动态添加

    # 用 ElementFactory 直接创建 (parse_launch 对该元素不稳定)

    # ICE: host 直连 / 浏览器侧 TURN (192.168.137.184:3478), 本端无需 STUN

    pipeline = Gst.Pipeline.new('reverse_pipeline')

    webrtc = Gst.ElementFactory.make('webrtcbin', 'wb')

    if webrtc is None:

        print('[err] 无法创建 webrtcbin 插件, 请检查 gst-plugin-webrtc')

        sys.exit(1)

    try:

        webrtc.set_property('bundle-policy', 'max-bundle')

        webrtc.set_property('latency', 0)

    except Exception as e:

        print(f'[warn] 属性设置: {e}')

    pipeline.add(webrtc)

    webrtc.connect('pad-added', on_pad_added)



    pipeline.set_state(Gst.State.READY)

    pipeline.set_state(Gst.State.PLAYING)



    # WebSocket 信令 (独立线程, gst 操作经 idle_add 到主线程)

    ws_sock = websocket.WebSocketApp(

        SIGNALING,

        on_open=on_ws_open,

        on_message=on_ws_message,

        on_error=lambda w, e: print(f'[sig] ws error: {e}'),

        on_close=lambda w, *a: print('[sig] ws closed'))

    threading.Thread(target=ws_sock.run_forever, daemon=True).start()



    try:

        loop.run()

    except KeyboardInterrupt:

        pass

    finally:

        pipeline.set_state(Gst.State.NULL)





if __name__ == '__main__':

    main()

