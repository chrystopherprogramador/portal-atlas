#!/bin/bash
set +e
echo "=== Status service ==="
systemctl is-active atlas-backup.service
systemctl status atlas-backup.service --no-pager -l | tail -15
echo
echo "=== Processos borg ==="
ps -eo pid,stat,etime,rss,cmd | grep -E 'borg|ssh' | grep -v grep
echo
echo "=== Trafego de rede p/ NAS ==="
ss -tnp | grep 172.16.3.200 || echo "sem conexoes p/ 172.16.3.200"
echo
echo "=== Tamanho transferido (netstat stats das conexoes borg) ==="
# ps do borg create remoto
ss -tni | grep -A1 172.16.3.200 | head -20
