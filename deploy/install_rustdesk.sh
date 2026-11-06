#!/bin/bash
# install_rustdesk.sh — instala docker (se preciso), sobe hbbs/hbbr e
# instala o modulo no portal-atlas
set -e

PORTAL=/opt/atlas-portal

echo "==== [1/7] Verificando Docker ===="
if ! command -v docker >/dev/null 2>&1; then
  echo "Instalando Docker..."
  apt-get update -qq
  apt-get install -y -qq ca-certificates curl gnupg
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg 2>/dev/null \
    || curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/${ID} ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
docker --version
docker compose version
echo "[OK] docker"

echo "==== [2/7] Instalando docker-compose do RustDesk ===="
mkdir -p /opt/rustdesk /var/lib/rustdesk-data
install -m 0644 -o root -g root /tmp/rustdesk-compose.yml /opt/rustdesk/docker-compose.yml
echo "[OK] compose"

echo "==== [3/7] Instalando script de gerencia ===="
install -m 0755 -o root -g root /tmp/gerenciar-rustdesk.sh /usr/local/sbin/gerenciar-rustdesk.sh
echo "[OK] script"

echo "==== [4/7] Subindo containers ===="
cd /opt/rustdesk
docker compose pull
docker compose up -d
sleep 5
docker ps --filter name=hbb
ls -la /var/lib/rustdesk-data/ 2>/dev/null || true
echo "[OK] containers up"

echo "==== [5/7] Liberando portas no firewall (se ufw ativo) ===="
if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
  for p in 21115 21116 21117 21118 21119; do
    ufw allow $p/tcp || true
  done
  ufw allow 21116/udp || true
  echo "[OK] ufw"
else
  echo "(ufw inativo - libere portas no firewall externo manualmente: 21115-21119/tcp + 21116/udp)"
fi

echo "==== [6/7] Instalando arquivos do portal ===="
install -m 0644 -o root -g root /tmp/rustdesk_bp.py $PORTAL/blueprints/rustdesk_bp.py
install -m 0644 -o root -g root /tmp/rustdesk.py    $PORTAL/modules/rustdesk.py
mkdir -p $PORTAL/templates/rustdesk
install -m 0644 -o root -g root /tmp/rustdesk_index.html $PORTAL/templates/rustdesk/index.html
install -m 0644 -o root -g root /tmp/app.py         $PORTAL/app.py
install -m 0644 -o root -g root /tmp/base.html      $PORTAL/templates/base.html

# sudoers
install -m 0440 -o root -g root /tmp/sudoers.portal /etc/sudoers.d/portal
visudo -c -f /etc/sudoers.d/portal
echo "[OK] portal files"

echo "==== [7/7] Reiniciando portal ===="
systemctl restart portal-atlas
sleep 2
systemctl is-active portal-atlas
echo "[OK] portal"

echo
echo "===================================================================="
echo "RustDesk Server pronto. Acesse https://atlas.local/rustdesk/"
echo "Chave publica gerada:"
cat /var/lib/rustdesk-data/id_ed25519.pub 2>/dev/null || echo "  (aguarde alguns segundos e atualize o painel)"
echo "===================================================================="
