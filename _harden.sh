echo '== set journald size cap =='
cat <<'EOF' | echo elf | sudo -S tee /etc/systemd/journald.conf.d/size-cap.conf >/dev/null
[Journal]
SystemMaxUse=100M
SystemKeepFree=200M
RuntimeMaxUse=50M
MaxRetentionSec=2week
EOF
echo elf | sudo -S systemctl restart systemd-journald 2>&1
echo '== applied. verify drop-in for lightdm =='
echo elf | sudo -S cat /etc/systemd/system/lightdm.service.d/override.conf 2>&1
echo '== journal disk usage after cap =='
echo elf | sudo -S journalctl --disk-usage 2>&1
echo '== lightdm final status =='; systemctl is-active lightdm
