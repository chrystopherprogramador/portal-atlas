#!/bin/bash
apt-cache policy ttyd 2>&1 | head -6
echo ---
ls /etc/nginx/sites-enabled/ 2>/dev/null
echo ---
ss -tlnp 2>/dev/null | grep -E ':80 |:443 |:8000 |:7681 '
echo ---
systemctl list-unit-files 2>/dev/null | grep -E 'portal|nginx'
echo ---
cat /etc/nginx/sites-enabled/*.conf 2>/dev/null | head -80
cat /etc/nginx/sites-enabled/default 2>/dev/null | head -80
cat /etc/nginx/sites-enabled/portal-atlas 2>/dev/null | head -80
