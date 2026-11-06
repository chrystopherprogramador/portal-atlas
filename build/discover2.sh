#!/bin/bash
grep -n -E 'location |proxy_pass|unix:|listen |server_name' /etc/nginx/sites-enabled/atlas-portal.conf | tail -60
echo ---
lsb_release -a 2>/dev/null
echo ---
# ver qual user roda o portal (pra permitir PAM login no ttyd)
systemctl show portal-atlas -p User,Group 2>/dev/null
