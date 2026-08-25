echo '== date =='; date
echo '== whoami =='; whoami
echo '== lightdm active =='; systemctl is-active lightdm 2>&1
echo '== lightdm failed =='; systemctl is-failed lightdm 2>&1
echo '== lightdm status (head) =='; systemctl status lightdm --no-pager 2>&1 | head -25
echo '== Xorg procs =='; ps aux | grep -i xorg | grep -v grep
echo '== DRM cards =='; ls -l /dev/dri/ 2>&1
echo '== DSI status =='; cat /sys/class/drm/card0-DSI-1/status 2>&1
echo '== DRM all status =='; for f in /sys/class/drm/*/status; do echo -n "$f: "; cat "$f"; done
echo '== backlight =='; for b in /sys/class/backlight/*; do echo -n "$b: "; cat "$b/brightness" 2>/dev/null; echo; done
echo '== free/load =='; uptime; free -m | head -3
echo '== dmesg drm recent =='; dmesg | tail -30 2>&1 | grep -iE "drm|dsi|vop|panel|rockchip|error" | tail -25
