#!/bin/bash
set -e

# 1) script
install -m 0755 -o root -g root /tmp/gerenciar-helpdesk.sh /usr/local/sbin/gerenciar-helpdesk.sh
echo "[OK] gerenciar-helpdesk.sh"

# 2) dirs
mkdir -p /var/backups/atlas-portal/helpdesk
chmod 750 /var/backups/atlas-portal/helpdesk
mkdir -p /var/log/atlas-portal/helpdesk
chmod 750 /var/log/atlas-portal/helpdesk

# 3) preserve list
mkdir -p /etc/portal-atlas
if [ ! -f /etc/portal-atlas/helpdesk-preserve.list ]; then
cat > /etc/portal-atlas/helpdesk-preserve.list <<'EOF'
# Caminhos relativos a /var/www/helpdesk/ preservados em deploy/rollback
config/database.php
EOF
chmod 644 /etc/portal-atlas/helpdesk-preserve.list
fi
echo "[OK] dirs + preserve.list"

# 4) portal files
P=/opt/atlas-portal
install -m 0644 -o root -g root /tmp/app.py $P/app.py
install -m 0644 -o root -g root /tmp/helpdesk_deploy_bp.py $P/blueprints/helpdesk_deploy_bp.py
install -m 0644 -o root -g root /tmp/helpdesk_deploy.py $P/modules/helpdesk_deploy.py
mkdir -p $P/templates/helpdesk_deploy
install -m 0644 -o root -g root /tmp/index.html $P/templates/helpdesk_deploy/index.html
echo "[OK] portal files"

# 5) nginx — bump 2200m + timeouts
NG=/etc/nginx/sites-available/atlas-portal.conf
sed -i -E 's/client_max_body_size [0-9]+[mMkKgG];/client_max_body_size 2200m;/' $NG
if ! grep -q "client_body_timeout" $NG; then
  sed -i '/client_max_body_size 2200m;/a\    client_body_timeout 1800s;\n    proxy_read_timeout 1800s;\n    proxy_send_timeout 1800s;\n    proxy_request_buffering off;' $NG
fi
nginx -t
systemctl reload nginx
echo "[OK] nginx 2200m"

# 6) gunicorn timeout
UNIT=/etc/systemd/system/portal-atlas.service
if grep -q "ExecStart=.*gunicorn" $UNIT; then
  if grep -q -- "--timeout" $UNIT; then
    sed -i -E 's/--timeout [0-9]+/--timeout 1800/' $UNIT
  else
    sed -i -E 's|(ExecStart=.*gunicorn)([^\n]*)|\1 --timeout 1800\2|' $UNIT
  fi
  systemctl daemon-reload
  echo "[OK] gunicorn --timeout 1800"
fi

# 7) restart
systemctl restart portal-atlas
sleep 2
systemctl is-active portal-atlas
echo "[OK] portal-atlas"
