#!/bin/bash
set +e
systemctl is-active atlas-backup.service
echo "--- progress ---"
/usr/local/sbin/atlas-backup.sh progress 5
echo "--- NAS archives ---"
set -a; source /etc/atlas-backup/env; set +a
export BORG_RSH="ssh -i /etc/atlas-backup/id_ed25519 -o StrictHostKeyChecking=accept-new"
borg list --short "$REMOTE_REPO" 2>&1 | tail -10
echo "--- LOCAL archives ---"
borg list --short "$BORG_REPO" 2>&1 | tail -10
