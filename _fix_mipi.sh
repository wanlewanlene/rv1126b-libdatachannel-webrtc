set -e
echo '== before: autologin-user =='; grep -n '^autologin-user' /etc/lightdm/lightdm.conf || true
echo elf | sudo -S sed -i 's/^autologin-user=.*/autologin-user=elf/' /etc/lightdm/lightdm.conf
echo '== after: autologin-user =='; grep -n '^autologin-user' /etc/lightdm/lightdm.conf

# 创建 systemd drop-in，让 lightdm 失败后自动重试且不轻易放弃
echo elf | sudo -S mkdir -p /etc/systemd/system/lightdm.service.d
cat <<'EOF' | echo elf | sudo -S tee /etc/systemd/system/lightdm.service.d/override.conf >/dev/null
[Service]
Restart=always
RestartSec=2
StartLimitIntervalSec=0
StartLimitBurst=0
EOF
echo elf | sudo -S systemctl daemon-reload

echo '== restart lightdm =='
echo elf | sudo -S systemctl restart lightdm
echo 'waiting 6s for Xorg...'
sleep 6
echo '== lightdm status =='; systemctl is-active lightdm 2>&1
echo '== Xorg procs =='; ps aux | grep -i [X]org
echo '== seat0 x log tail =='; echo elf | sudo -S tail -20 /var/log/lightdm/x-0.log 2>&1
echo '== lightdm log tail =='; echo elf | sudo -S tail -20 /var/log/lightdm/lightdm.log 2>&1
echo '== DSI connected? =='; cat /sys/class/drm/card0-DSI-1/status
echo '== backlight =='; for b in /sys/class/backlight/*/brightness; do echo -n "$b="; cat $b; done
