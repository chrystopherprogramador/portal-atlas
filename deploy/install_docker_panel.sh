#!/bin/bash
set -e
P=/opt/atlas-portal
install -m 0644 /tmp/app.py $P/app.py
install -m 0644 /tmp/base.html $P/templates/base.html
install -m 0644 /tmp/docker_bp.py $P/blueprints/docker_bp.py
install -m 0644 /tmp/docker_mgr.py $P/modules/docker_mgr.py
mkdir -p $P/templates/docker
install -m 0644 /tmp/docker_index.html $P/templates/docker/index.html
install -m 0644 /tmp/docker_logs.html $P/templates/docker/logs.html
systemctl restart portal-atlas
sleep 2
systemctl is-active portal-atlas
echo "[OK] docker panel"
