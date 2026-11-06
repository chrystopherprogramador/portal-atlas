#!/bin/bash
set +e
echo "=== /etc/atlas-backup/ conteudo ==="
ls -la /etc/atlas-backup/
echo
echo "=== remote.env (hex + raw) ==="
wc -c /etc/atlas-backup/remote.env
od -c /etc/atlas-backup/remote.env | head
echo "--- raw ---"
cat /etc/atlas-backup/remote.env
echo "--- fim ---"
echo
echo "=== env principal ==="
cat /etc/atlas-backup/env 2>/dev/null | head -30
echo
echo "=== grep set-remote no atlas-backup.sh ==="
grep -n "set-remote\|remote.env\|REMOTE\|flock" /usr/local/sbin/atlas-backup.sh | head -40
echo
echo "=== tamanho do log (duplicate?) ==="
wc -l /var/log/atlas-backup.log
echo "=== Linhas 'borg create' do log ==="
grep -n "borg create" /var/log/atlas-backup.log | tail -10
echo "=== Linhas run-detached / pid ==="
grep -n "PID\|run-detached\|lock" /var/log/atlas-backup.log | tail -20
