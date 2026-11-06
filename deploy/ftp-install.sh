#!/usr/bin/env bash
# ftp-install.sh - Instala/atualiza o servidor FTP gerenciado pelo Atlas Portal
# Pode ser executado standalone OU pelo install.sh principal.

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "[X] Precisa rodar como root"; exit 1
fi

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
FTP_GROUP="ftpusers"
FTP_ROOT="/srv/ftp"
USERLIST="/etc/vsftpd.userlist"

echo "[FTP 1/6] Pacote vsftpd ..."
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq vsftpd >/dev/null

echo "[FTP 2/6] Estrutura ..."
getent group "$FTP_GROUP" >/dev/null || groupadd "$FTP_GROUP"
mkdir -p "$FTP_ROOT"
chmod 755 "$FTP_ROOT"
[[ -f "$USERLIST" ]] || : > "$USERLIST"
chmod 600 "$USERLIST"

echo "[FTP 3/6] Configuracao /etc/vsftpd.conf ..."
[[ -f /etc/vsftpd.conf ]] && cp -a /etc/vsftpd.conf "/etc/vsftpd.conf.bak.$(date +%s)"
install -m 644 "$SRC_DIR/vsftpd-atlas.conf" /etc/vsftpd.conf

# Detecta IP publico/NAT (best-effort) para pasv_address
PUB_IP="$(curl -fsS --max-time 3 https://api.ipify.org 2>/dev/null || true)"
if [[ -n "$PUB_IP" ]] && ! grep -q '^pasv_address=' /etc/vsftpd.conf; then
    echo "pasv_address=${PUB_IP}" >> /etc/vsftpd.conf
    echo "pasv_addr_resolve=NO"   >> /etc/vsftpd.conf
fi

echo "[FTP 4/6] Script de gerencia ..."
install -m 750 "$SRC_DIR/gerenciar-ftp.sh" /usr/local/sbin/gerenciar-ftp.sh

echo "[FTP 5/6] Firewall (UFW) ..."
# FTP control + passivo somente da LAN e VPN
ufw allow from 172.16.0.0/21 to any port 21          proto tcp comment 'FTP LAN'        >/dev/null 2>&1 || true
ufw allow from 10.8.0.0/24   to any port 21          proto tcp comment 'FTP VPN'        >/dev/null 2>&1 || true
ufw allow from 172.16.0.0/21 to any port 30000:30100 proto tcp comment 'FTP-PASV LAN'   >/dev/null 2>&1 || true
ufw allow from 10.8.0.0/24   to any port 30000:30100 proto tcp comment 'FTP-PASV VPN'   >/dev/null 2>&1 || true

echo "[FTP 6/6] Servico ..."
systemctl enable vsftpd >/dev/null 2>&1 || true
systemctl restart vsftpd
sleep 1
systemctl is-active --quiet vsftpd && echo "  > vsftpd ativo" || { echo "  > vsftpd NAO subiu"; journalctl -u vsftpd -n 30 --no-pager; exit 1; }

echo ""
echo "=============================================="
echo ">> FTP pronto"
echo "=============================================="
echo "  Porta:     21 (TCP) + 30000-30100 (passivo)"
echo "  Conf:      /etc/vsftpd.conf"
echo "  Grupo:     $FTP_GROUP"
echo "  Home:      $FTP_ROOT/<usuario>/files"
echo "  Userlist:  $USERLIST"
echo "  Gerencia:  /usr/local/sbin/gerenciar-ftp.sh"
echo "  Portal:    https://atlas.texasco.local/ftp/"
echo "=============================================="
