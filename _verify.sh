echo '== lightdm active =='; systemctl is-active lightdm
echo '== session processes (elf desktop) =='; ps -u elf -o pid,comm,args 2>/dev/null | grep -iE "lxsession|openbox|LXDE|matchbox|xsession|pcmanfm|tint2|panel" | grep -v grep
echo '== any X client procs =='; echo elf | sudo -S ps aux | grep -iE "lxsession|openbox|pcmanfm|lightdm-gtk-greeter" | grep -v grep
echo '== DISPLAY env for elf session =='; echo elf | sudo -S loginctl session-status 2>/dev/null | head -15
echo '== x-0.log (EE) errors =='; echo elf | sudo -S grep -iE '\(EE\)|error' /var/log/Xorg.0.log 2>&1 | head -20
echo '== x-0.log tail =='; echo elf | sudo -S tail -8 /var/log/Xorg.0.log 2>&1
echo '== /var/log/lightdm/seat0-greeter.log =='; echo elf | sudo -S tail -10 /var/log/lightdm/seat0-greeter.log 2>&1
echo '== df final =='; df -h / | tail -1
