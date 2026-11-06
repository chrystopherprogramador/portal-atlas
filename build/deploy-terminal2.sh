#!/bin/bash
# Continua deploy: nginx patch + portal files + restart
set -euo pipefail

PORTAL=/opt/atlas-portal
NGX_CONF=/etc/nginx/sites-enabled/atlas-portal.conf

echo "=== Patch nginx ==="
cp -a "$NGX_CONF" "${NGX_CONF}.bak.$(date +%s)"

python3 - <<'PY'
import re, pathlib
p = pathlib.Path("/etc/nginx/sites-enabled/atlas-portal.conf")
s = p.read_text()
s = re.sub(r"\n?\s*# >>> ATLAS TERMINAL BEGIN >>>.*?# <<< ATLAS TERMINAL END <<<\n?", "\n", s, flags=re.S)
snippet = pathlib.Path("/tmp/nginx-terminal.inc").read_text()
block = "\n    # >>> ATLAS TERMINAL BEGIN >>>\n" + snippet.rstrip() + "\n    # <<< ATLAS TERMINAL END <<<\n"
m = re.search(r"(^\s*location\s*/\s*\{)", s, flags=re.M)
if not m:
    raise SystemExit("Nao achei 'location / {'")
s2 = s[:m.start()] + block + s[m.start():]
p.write_text(s2)
print("snippet inserido em offset", m.start())
PY

nginx -t
systemctl reload nginx

echo "=== Portal files ==="
install -m 644 -o root -g www-data /tmp/app.py                  $PORTAL/app.py
install -m 644 -o root -g www-data /tmp/terminal_bp.py          $PORTAL/blueprints/terminal_bp.py
install -m 644 -o root -g www-data /tmp/base.html               $PORTAL/templates/base.html
mkdir -p $PORTAL/templates/terminal
install -m 644 -o root -g www-data /tmp/terminal_index.html     $PORTAL/templates/terminal/index.html

echo "=== Restart portal ==="
systemctl restart portal-atlas.service
sleep 2
systemctl is-active portal-atlas.service
systemctl is-active ttyd-atlas.service

echo
echo "=== Smoke tests ==="
curl -sI -o /dev/null -w 'auth-check sem cookie -> HTTP %{http_code} (esperado 401)\n' http://127.0.0.1:8080/auth-check
curl -skI -o /dev/null -w '/terminal-ws/ sem cookie -> HTTP %{http_code} (esperado 302)\n' https://127.0.0.1/terminal-ws/
curl -skI -o /dev/null -w '/terminal sem cookie -> HTTP %{http_code} (esperado 302)\n' https://127.0.0.1/terminal
echo OK
