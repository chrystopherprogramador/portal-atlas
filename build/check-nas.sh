#!/bin/bash
set +e
echo "=== Archives no NAS (direto como root, carregando env) ==="
set -a; source /etc/atlas-backup/env; set +a
export BORG_RSH="ssh -i /etc/atlas-backup/id_ed25519 -o StrictHostKeyChecking=accept-new"
echo "REMOTE=$REMOTE_REPO"
borg list --short "$REMOTE_REPO" 2>&1 | tail -15
echo
echo "=== Archives LOCAL ==="
borg list --short "$BORG_REPO" 2>&1 | tail -15
echo
echo "=== Dispara backup via novo run-detached (systemctl) ==="
/usr/local/sbin/atlas-backup.sh run-detached
sleep 2
systemctl is-active atlas-backup.service
echo "--- progress ---"
/usr/local/sbin/atlas-backup.sh progress 5
