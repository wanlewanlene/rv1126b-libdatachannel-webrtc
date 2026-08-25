cat > /tmp/jcap.conf <<'EOF'
[Journal]
SystemMaxUse=100M
SystemKeepFree=200M
RuntimeMaxUse=50M
MaxRetentionSec=2week
EOF
echo elf | sudo -S mkdir -p /etc/systemd/journald.conf.d
echo elf | sudo -S cp /tmp/jcap.conf /etc/systemd/journald.conf.d/size-cap.conf

cat > /tmp/lightdm-override.conf <<'EOF'
[Service]
Restart=always
RestartSec=2
StartLimitIntervalSec=0
StartLimitBurst=0
EOF
echo elf | sudo -S mkdir -p /etc/systemd/system/lightdm.service.d
echo elf | sudo -S cp /tmp/lightdm-override.conf /etc/systemd/system/lightdm.service.d/override.conf

echo elf | sudo -S systemctl daemon-reload
echo elf | sudo -S systemctl restart systemd-journald
echo '== verify lightdm override =='; echo elf | sudo -S cat /etc/systemd/system/lightdm.service.d/override.conf
echo '== journal usage =='; echo elf | sudo -S journalctl --disk-usage
echo '== lightdm status =='; systemctl is-active lightdm
