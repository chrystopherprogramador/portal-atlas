#!/usr/bin/env bash
# install.sh - Instalador do ATLAS Portal no Atlas
# Executar como root

set -euo pipefail

APP_DIR="/opt/atlas-portal"
LOG_DIR="/var/log/atlas-portal"
DATA_DIR="/var/lib/portal-atlas"
CERT_DIR="/etc/ssl/atlas-portal"
DOMAIN="texasco.local"

echo "=============================================="
echo ">> ATLAS Portal :: Instalador"
echo "=============================================="

if [[ $EUID -ne 0 ]]; then
    echo "[X] Precisa rodar como root"; exit 1
fi

echo "[1/10] Pacotes base ..."
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    python3-venv python3-pip python3-dev \
    libldap2-dev libsasl2-dev \
    libjpeg-dev zlib1g-dev \
    nginx openssl

echo "[2/10] Estrutura de diretorios ..."
mkdir -p "$APP_DIR" "$LOG_DIR" "$DATA_DIR" "$CERT_DIR"

echo "[3/10] Copiando codigo ..."
SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"
rsync -a --delete --exclude 'venv' --exclude '__pycache__' --exclude 'deploy' "$SRC_DIR"/ "$APP_DIR"/
chown -R root:root "$APP_DIR"

echo "[4/10] Virtualenv + dependencias Python ..."
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip -q
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt" -q

echo "[5/10] Certificado auto-assinado ..."
if [[ ! -f "$CERT_DIR/atlas.crt" ]]; then
    openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
        -subj "/CN=atlas.${DOMAIN}/O=TEXASCO/C=BR" \
        -addext "subjectAltName=DNS:atlas,DNS:atlas.${DOMAIN},IP:172.16.3.100,IP:10.8.0.1" \
        -keyout "$CERT_DIR/atlas.key" -out "$CERT_DIR/atlas.crt"
    chmod 600 "$CERT_DIR/atlas.key"
fi

echo "[6/10] Sudoers ..."
install -m 440 "$SRC_DIR/deploy/sudoers.portal" /etc/sudoers.d/portal-atlas
visudo -cf /etc/sudoers.d/portal-atlas

# Scripts de gerencia
install -m 750 "$SRC_DIR/deploy/gerenciar-share.sh" /usr/local/sbin/gerenciar-share.sh
install -m 750 "$SRC_DIR/deploy/gerenciar-ftp.sh"   /usr/local/sbin/gerenciar-ftp.sh
install -m 750 "$SRC_DIR/deploy/gerenciar-wallpaper.sh" /usr/local/sbin/gerenciar-wallpaper.sh
install -m 755 "$SRC_DIR/deploy/wallpaper-pol.py"      /usr/local/sbin/wallpaper-pol.py
install -m 750 "$SRC_DIR/deploy/gerenciar-drives.sh"   /usr/local/sbin/gerenciar-drives.sh
install -m 755 "$SRC_DIR/deploy/drives-builder.py"     /usr/local/sbin/drives-builder.py
mkdir -p /srv/samba/shares /srv/samba/wallpaper /etc/portal-atlas
chmod 755 /srv/samba/shares /srv/samba/wallpaper /etc/portal-atlas

# FTP (vsftpd)
bash "$SRC_DIR/deploy/ftp-install.sh"

# GPO de papel de parede
bash "$SRC_DIR/deploy/wallpaper-install.sh" || echo '[!] wallpaper-install falhou; rode manualmente'

echo "[7/10] nginx ..."
# Desliga default
[[ -f /etc/nginx/sites-enabled/default ]] && rm -f /etc/nginx/sites-enabled/default
install -m 644 "$SRC_DIR/deploy/nginx-portal.conf" /etc/nginx/sites-available/atlas-portal.conf
ln -sf /etc/nginx/sites-available/atlas-portal.conf /etc/nginx/sites-enabled/atlas-portal.conf
nginx -t
systemctl reload nginx || systemctl restart nginx

echo "[8/10] systemd ..."
install -m 644 "$SRC_DIR/deploy/portal-atlas.service" /etc/systemd/system/portal-atlas.service

# Env file (gera SECRET se nao existir)
if [[ ! -f /etc/default/atlas-portal ]]; then
    SECRET=$(openssl rand -hex 32)
    cat > /etc/default/atlas-portal <<EOF
PORTAL_SECRET_KEY=${SECRET}
PORTAL_LDAP_DOMAIN=${DOMAIN}
PORTAL_VPN_ENDPOINT=200.9.18.201
PORTAL_ADMIN_GROUP=PortalAdmins
EOF
    chmod 600 /etc/default/atlas-portal
fi

systemctl daemon-reload
systemctl enable --now portal-atlas

echo "[9/10] UFW ..."
# HTTPS so pela LAN + VPN; bloquear WAN
ufw allow from 172.16.0.0/21 to any port 443 proto tcp comment 'Portal LAN'  >/dev/null
ufw allow from 10.8.0.0/24   to any port 443 proto tcp comment 'Portal VPN'  >/dev/null
ufw allow from 172.16.0.0/21 to any port 80  proto tcp comment 'Portal LAN'  >/dev/null
ufw allow from 10.8.0.0/24   to any port 80  proto tcp comment 'Portal VPN'  >/dev/null

echo "[10/10] Grupo PortalAdmins ..."
if ! samba-tool group list 2>/dev/null | grep -qx "PortalAdmins"; then
    samba-tool group add PortalAdmins --description="Administradores do Portal ATLAS" || true
fi
# Adiciona Administrator
samba-tool group addmembers PortalAdmins Administrator 2>/dev/null || true

echo ""
echo "=============================================="
echo ">> Instalacao concluida!"
echo "=============================================="
echo "  URL:    https://atlas.${DOMAIN}/  (LAN)"
echo "          https://10.8.0.1/         (VPN)"
echo "  Login:  Administrator / (senha do AD)"
echo "          ou qualquer membro de PortalAdmins"
echo ""
echo "  Servico:  systemctl status portal-atlas"
echo "  Logs:     tail -f /var/log/atlas-portal/error.log"
echo "=============================================="
