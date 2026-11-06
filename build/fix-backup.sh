#!/bin/bash
# Patches:
#  1) run-detached -> systemctl start --no-block (cgroup independente do portal)
#  2) log() -> sem >&2 (evita duplicacao quando systemd/nohup redireciona stderr)
#  3) testa replicate manual pra saber se NAS recebe archive
set -euo pipefail

SCRIPT=/usr/local/sbin/atlas-backup.sh
cp -a "$SCRIPT" "${SCRIPT}.bak.$(date +%s)"

echo "=== 1) Patch log() (remove duplicacao) ==="
# linha 47: log() { echo "[$(date -Is)] $*" | tee -a "$LOG_FILE" >&2; }
sed -i 's|log()  { echo "\[\$(date -Is)\] \$\*" | tee -a "\$LOG_FILE" >\&2; }|log()  { echo "[$(date -Is)] $*" >> "$LOG_FILE"; }|' "$SCRIPT" || true
# Sed com escape eh chato, usa python
python3 - <<'PY'
import pathlib
p = pathlib.Path("/usr/local/sbin/atlas-backup.sh")
s = p.read_text()
old = 'log()  { echo "[$(date -Is)] $*" | tee -a "$LOG_FILE" >&2; }'
new = 'log()  { echo "[$(date -Is)] $*" >> "$LOG_FILE"; }'
if old in s:
    s = s.replace(old, new)
    print("log() patched")
else:
    print("log() old pattern NOT FOUND - checking current")
    for ln in s.splitlines():
        if ln.startswith("log()"):
            print("CURRENT:", ln)
p.write_text(s)
PY

echo "=== 2) Patch run-detached -> systemctl start ==="
python3 - <<'PY'
import pathlib
p = pathlib.Path("/usr/local/sbin/atlas-backup.sh")
s = p.read_text()
old = '''cmd_run_detached() {
  # Dispara em background para o portal poder retornar rapido
  nohup "$0" run >>"$LOG_FILE" 2>&1 &
  echo "{\\"started\\":true,\\"pid\\":$!}"
}'''
new = '''cmd_run_detached() {
  # Dispara via systemd (cgroup independente do portal) - evita que reinicio
  # do portal-atlas.service mate o backup no meio.
  if systemctl is-active --quiet atlas-backup.service; then
    echo "{\\"started\\":false,\\"reason\\":\\"ja em execucao\\"}"
    return 0
  fi
  systemctl start --no-block atlas-backup.service
  echo "{\\"started\\":true,\\"via\\":\\"systemctl\\"}"
}'''
if old in s:
    s = s.replace(old, new)
    print("run-detached patched")
else:
    print("run-detached pattern NOT FOUND")
p.write_text(s)
PY

echo "=== 3) Reload daemon e checar ==="
systemctl daemon-reload
grep -n "^log()\|cmd_run_detached" "$SCRIPT"

echo
echo "=== 4) archive no NAS? ==="
sudo -u backup bash -c '
  source /etc/atlas-backup/env
  export BORG_RSH="ssh -i /etc/atlas-backup/id_ed25519 -o StrictHostKeyChecking=accept-new"
  echo "REMOTE=$REMOTE_REPO"
  borg list --short "$REMOTE_REPO" 2>&1
' 2>&1
