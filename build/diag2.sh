#!/bin/bash
set +e
echo "=== SUDOERS p/ backup ==="
sudo -l -U backup 2>&1 | head -20
echo
echo "=== borg list LOCAL (como backup) ==="
sudo -u backup borg list /var/backups/borg-atlas 2>&1 | tail -15
echo
echo "=== remote.env ==="
cat /etc/atlas-backup/remote.env 2>/dev/null
echo
echo "=== borg list REMOTO (NAS) ==="
sudo -u backup bash -c '
  source /etc/atlas-backup/remote.env 2>/dev/null
  export BORG_RSH="ssh -i /var/backups/.ssh/id_ed25519_backup -o StrictHostKeyChecking=accept-new"
  echo "REMOTE=$BORG_REPO_REMOTE"
  borg list "$BORG_REPO_REMOTE" 2>&1 | tail -15
' 2>&1
echo
echo "=== flock / lockfiles ==="
ls -la /var/lib/atlas-backup/ /var/run/atlas-backup* 2>/dev/null
ls -la /var/backups/borg-atlas/lock.* 2>/dev/null
echo
echo "=== ps borg ==="
ps -eo pid,stat,etime,cmd | grep -E 'borg|atlas-backup' | grep -v grep
echo
echo "=== ultimas 40 linhas do log completo ==="
tail -40 /var/log/atlas-backup.log
