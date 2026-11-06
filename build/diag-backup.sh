#!/bin/bash
set +e
echo "=== atlas-backup status ==="
systemctl status atlas-backup.service --no-pager -l | head -40
echo
echo "=== progress.json ==="
cat /var/lib/atlas-backup/progress.json 2>/dev/null
echo
echo "=== ultimo log (50 linhas) ==="
tail -80 /var/log/atlas-backup.log 2>/dev/null
echo
echo "=== borg list local ==="
sudo -u backup borg list /var/backups/borg-atlas 2>&1 | tail -10
echo
echo "=== borg list remoto (NAS) ==="
source /etc/atlas-backup/remote.env 2>/dev/null
echo "REMOTE=$BORG_REPO_REMOTE"
sudo -u backup BORG_RSH="ssh -i /var/backups/.ssh/id_ed25519_backup -o StrictHostKeyChecking=accept-new" \
    borg list "$BORG_REPO_REMOTE" 2>&1 | tail -10
echo
echo "=== processos borg ativos ==="
ps -eo pid,stat,etime,cmd | grep -E 'borg|atlas-backup' | grep -v grep
