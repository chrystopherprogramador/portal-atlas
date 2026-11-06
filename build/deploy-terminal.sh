#!/bin/bash
# Deploy do terminal web (ttyd) no servidor ATLAS.
# Executado como root via plink.
set -euo pipefail

PORTAL=/opt/atlas-portal
NGX_CONF=/etc/nginx/sites-enabled/atlas-portal.conf

echo "=== 1/6 Instalando ttyd ==="
if ! command -v ttyd >/dev/null 2>&1; then
    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ttyd
fi
ttyd --version || true

echo "=== 2/6 Instalando systemd unit do ttyd ==="
install -m 644 /tmp/ttyd-atlas.service /etc/systemd/system/ttyd-atlas.service
systemctl daemon-reload
systemctl enable ttyd-atlas.service
systemctl restart ttyd-atlas.service
sleep 1
systemctl is-active ttyd-atlas.service
ss -tlnp | grep 7681 || true

echo "=== 3/6 Patch nginx (inserindo snippet do terminal) ==="
# Backup
cp -a "$NGX_CONF" "${NGX_CONF}.bak.$(date +%s)"

# Remover bloco antigo se existir (idempotencia)
python3 - <<'PY'
import re, pathlib
p = pathlib.Path("/etc/nginx/sites-enabled/atlas-portal.conf")
s = p.read_text()
# Remove bloco antigo marcado
s = re.sub(r"\n?\s*# >>> ATLAS TERMINAL BEGIN >>>.*?# <<< ATLAS TERMINAL END <<<\n?", "\n", s, flags=re.S)
p.write_text(s)
PY

SNIPPET=$(cat /tmp/nginx-terminal.inc)
MARKER_BEGIN="    # >>> ATLAS TERMINAL BEGIN >>>"
MARKER_END="    # <<< ATLAS TERMINAL END <<<"

# Insere snippet antes da linha 'location / {' dentro do server block do portal
python3 - <<PY
import pathlib, re
p = pathlib.Path("/etc/nginx/sites-enabled/atlas-portal.conf")
s = p.read_text()
snippet = pathlib.Path("/tmp/nginx-terminal.inc").read_text()
block = "\n    # >>> ATLAS TERMINAL BEGIN >>>\n" + snippet.rstrip() + "\n    # <<< ATLAS TERMINAL END <<<\n"
# acha primeira ocorrencia de 'location / {' (com espacos) e insere antes
m = re.search(r"(^\s*location\s*/\s*\{)", s, flags=re.M)
if not m:
    raise SystemExit("Nao achei 'location / {' em atlas-portal.conf")
s2 = s[:m.start()] + block + s[m.start():]
p.write_text(s2)
print("snippet inserido em", m.start())
PY

echo "=== 4/6 Testando + reload nginx ==="
nginx -t
systemctl reload nginx

echo "=== 5/6 Atualizando portal (codigo python/templates) ==="
# Arquivos ja foram enviados para /tmp antes deste script
install -m 644 -o root -g www-data /tmp/app.py                        $PORTAL/app.py
install -m 644 -o root -g www-data /tmp/terminal_bp.py                $PORTAL/blueprints/terminal_bp.py
install -m 644 -o root -g www-data /tmp/base.html                     $PORTAL/templates/base.html
mkdir -p $PORTAL/templates/terminal
install -m 644 -o root -g www-data /tmp/terminal_index.html           $PORTAL/templates/terminal/index.html

echo "=== 6/6 Restart portal-atlas ==="
systemctl restart portal-atlas.service
sleep 2
systemctl is-active portal-atlas.service
systemctl is-active ttyd-atlas.service

echo
echo "=== OK ==="
echo "ttyd:   $(ss -tlnp | grep 7681 || echo OFFLINE)"
echo "Teste:  curl -sI -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/auth-check"
curl -sI -o /dev/null -w 'auth-check sem cookie: HTTP %{http_code} (esperado 401)\n' http://127.0.0.1:8080/auth-check
