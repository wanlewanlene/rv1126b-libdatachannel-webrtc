echo '== tools =='
for t in v4l2-ctl ffmpeg gst-launch-1.0 yavta python3; do which $t 2>/dev/null && echo "  $t OK" || echo "  $t MISSING"; done
echo '== USB camera info =='
lsusb 2>/dev/null
echo '== /dev/video52 capabilities & current format =='
ls -l /dev/video52 2>/dev/null
v4l2-ctl -d /dev/video52 --all 2>&1 | head -40
echo '== V4L2 enum formats =='
v4l2-ctl -d /dev/video52 --list-formats 2>&1 | head -20
echo '== dmesg uvc errors =='
sudo dmesg 2>/dev/null | grep -iE 'uvc|video52|usb.*error|over-current' | tail -10
echo '== USB power (lsusb -v power) =='
lsusb -v -d $(lsusb 2>/dev/null | grep -iE 'camera|video' | awk '{print $6}' | head -1) 2>&1 | grep -iE 'MaxPower|iProduct' | head -4
echo '== current libdatachannel/push process =='
ps aux | grep rv1126b | grep -v grep
