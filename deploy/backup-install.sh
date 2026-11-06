#!/usr/bin/env bash
# ==============================================================================
# Instala Borg + atlas-backup (servico + timer + primeiro backup opcional)
# Executar como root no Atlas
# ==============================================================================
set -euo pipefail

command -v borg >/dev/null 2>&1 || {
  echo "==> Instalando borgbackup (+ fuse para mount)"
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq borgbackup borgbackup-doc fuse3 rsync
}

# Diretorios
install -d -m 0750 -o root -g root /etc/atlas-backup
install -d -m 0750 -o root -g root /var/lib/atlas-backup
install -d -m 0700 -o root -g root /var/backups
install -d -m 0700 -o root -g root /var/backups/atlas-local
install -d -m 0700 -o root -g root /var/tmp/atlas-backup-stage
touch /var/log/atlas-backup.log
chmod 0640 /var/log/atlas-backup.log

# Passphrase: gera se nao existe
if [ ! -f /etc/atlas-backup/env ]; then
  PASS="$(head -c 48 /dev/urandom | base64 | tr -d '/+=' | head -c 40)"
  cat > /etc/atlas-backup/env <<EOF
# ATLAS Backup -- configuracao
# Gerado em $(date -Is)

# Senha do repo Borg (NAO PERDER! Sem ela, restore impossivel.)
BORG_PASSPHRASE='$PASS'

# Repo local (default)
BORG_REPO='/var/backups/atlas-local'

# Repo remoto (NAS) -- descomentar quando o NAS estiver pronto
# REMOTE_REPO='backup@nas.texasco.local:/srv/borg/atlas'
# REMOTE_SSH_KEY='/etc/atlas-backup/id_ed25519'

# Compressao do Borg: zstd,N (1..22) ou lz4 ou zlib,6 ou none
COMPRESSION='zstd,6'

# Retencao GFS (grandfather-father-son)
RETENTION_DAILY=7
RETENTION_WEEKLY=4
RETENTION_MONTHLY=12
RETENTION_YEARLY=3

# Senha do Administrator do AD (para samba-tool domain backup online)
# SAMBA_ADMIN_PASSWORD='...'
EOF
  chmod 0600 /etc/atlas-backup/env
  echo "==> Passphrase gerada e salva em /etc/atlas-backup/env"
fi

# Instala script e units
install -m 0750 -o root -g root /tmp/portal-stage/deploy/atlas-backup.sh   /usr/local/sbin/atlas-backup.sh
install -m 0644 -o root -g root /tmp/portal-stage/deploy/atlas-backup.service /etc/systemd/system/atlas-backup.service
install -m 0644 -o root -g root /tmp/portal-stage/deploy/atlas-backup.timer   /etc/systemd/system/atlas-backup.timer

systemctl daemon-reload
systemctl enable --now atlas-backup.timer

echo "==> Inicializando repo Borg (se ainda nao existe)"
/usr/local/sbin/atlas-backup.sh init

echo
echo "============================================================"
echo "  INSTALACAO COMPLETA"
echo "============================================================"
echo "  Status timer : $(systemctl is-active atlas-backup.timer)"
echo "  Proxima exec : $(systemctl show atlas-backup.timer -p NextElapseUSecRealtime --value)"
echo "  Repo local   : /var/backups/atlas-local"
echo "  Chave backup : /etc/atlas-backup/key-backup.txt <-- COPIE PARA FORA DO SERVIDOR"
echo "  Passphrase   : /etc/atlas-backup/env             <-- COPIE PARA FORA DO SERVIDOR"
echo
echo "  Para rodar agora:   sudo /usr/local/sbin/atlas-backup.sh run"
echo "  Quando tiver NAS:   sudo /usr/local/sbin/atlas-backup.sh install-remote backup@nas:/srv/borg/atlas"
echo "============================================================"
