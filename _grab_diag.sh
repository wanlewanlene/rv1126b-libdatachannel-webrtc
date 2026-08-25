echo '== stop push to free /dev/video52 =='
pkill -9 -f rv1126b_webrtc_push 2>/dev/null || true
pkill -9 -f WebSocket.js 2>/dev/null || true
fuser -k /dev/video52 2>/dev/null || true
sleep 1
echo '== grab raw YUYV (640x480, read mode) =='
rm -f /tmp/raw.yuyv
v4l2-ctl -d /dev/video52 --set-fmt-video=width=640,height=480,pixelformat=YUYV \
  --stream-mmap --stream-count=1 --stream-to=/tmp/raw.yuyv 2>&1 | tail -3
ls -l /tmp/raw.yuyv
echo '== grab H264 (gstreamer mpph264enc) =='
rm -f /tmp/test.h264
gst-launch-1.0 -e --gst-debug=1 \
  v4l2src device=/dev/video52 num-buffers=1 do-timestamp=true \
  ! 'video/x-raw,width=640,height=480,format=YUYV,framerate=30/1' \
  ! videoconvert \
  ! mpph264enc bps=1024000 gop=30 \
  ! h264parse \
  ! filesink location=/tmp/test.h264 2>/tmp/gst.log
ls -l /tmp/test.h264
echo '== H264 SPS width/height (parse Annex-B) =='
# 用 Python 扫 00 00 00 01 67 (SPS) 里的 width/height
python3 - <<'PY'
import os,re
p='/tmp/test.h264'
if not os.path.exists(p) or os.path.getsize(p)==0:
    print('no h264'); raise SystemExit
d=open(p,'rb').read()
i=0; sps=''
while i<len(d)-5:
    if d[i:i+4]==b'\x00\x00\x00\x01':
        nal=d[i+4]
        if nal==0x67: sps=d[i+5:i+5+64]; break
        if nal==0x65: pass
    elif d[i:i+3]==b'\x00\x00\x01':
        nal=d[i+3]
        if nal==0x67: sps=d[i+4:i+4+64]; break
    i+=1
print('SPS bytes:', sps.hex() if sps else 'not found')
if sps:
    # parse width/height from SPS exp-golomb (rough)
    b=bits=sps
    print('first 32 bytes hex:', sps[:32].hex())
PY
echo '== restart push =='
cd /userdata/rtc
setsid bash /userdata/rtc/run.sh > /userdata/rtc/run.log 2>&1 < /dev/null &
disown 2>/dev/null || true
sleep 5
ps aux | grep -E 'rv1126b|WebSocket' | grep -v grep
echo 'done'