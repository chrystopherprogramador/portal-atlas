#!/bin/bash
# ATLAS Monitoring installer - Prometheus + Alertmanager + node_exporter + Grafana
# Idempotente: pode rodar multiplas vezes.
set -euo pipefail
STAGE="${STAGE:-/tmp/portal-stage}"
LOG(){ echo "[$(date -u +%FT%TZ)] $*"; }

LOG "=== 1. Pacotes ==="
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
    prometheus prometheus-alertmanager prometheus-node-exporter \
    apt-transport-https software-properties-common curl gnupg || true

if ! command -v grafana-server >/dev/null 2>&1; then
    LOG "Instalando Grafana OSS via repo oficial"
    install -d -m 0755 /etc/apt/keyrings
    curl -fsSL https://apt.grafana.com/gpg.key \
        | gpg --dearmor -o /etc/apt/keyrings/grafana.gpg
    echo "deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main" \
        > /etc/apt/sources.list.d/grafana.list
    apt-get update -qq
    apt-get install -y -qq grafana
fi

LOG "=== 2. Diretorios ==="
install -d -m 0755 -o prometheus -g prometheus /etc/prometheus/rules
install -d -m 0755 -o prometheus -g prometheus /var/lib/prometheus/metrics2
install -d -m 0755 -o root       -g root       /var/lib/node_exporter/textfile
install -d -m 0755 -o root       -g root       /var/lib/grafana/dashboards
install -d -m 0755 -o root       -g grafana    /etc/grafana/provisioning/datasources
install -d -m 0755 -o root       -g grafana    /etc/grafana/provisioning/dashboards

LOG "=== 3. Configs Prometheus ==="
install -o root -g prometheus -m 0640 "$STAGE/deploy/prometheus.yml"    /etc/prometheus/prometheus.yml
install -o root -g prometheus -m 0640 "$STAGE/deploy/alert-rules.yml"   /etc/prometheus/rules/atlas.yml

LOG "=== 4. Config Alertmanager ==="
install -o root -g prometheus -m 0640 "$STAGE/deploy/alertmanager.yml"  /etc/prometheus/alertmanager.yml

LOG "=== 5. Config Grafana ==="
install -o root -g grafana -m 0640 "$STAGE/deploy/grafana.ini" /etc/grafana/grafana.ini
install -o root -g grafana -m 0640 "$STAGE/deploy/grafana-datasource.yml"  /etc/grafana/provisioning/datasources/prometheus.yml
install -o root -g grafana -m 0640 "$STAGE/deploy/grafana-dashboards.yml"  /etc/grafana/provisioning/dashboards/atlas.yml
install -o root -g grafana -m 0644 "$STAGE/deploy/dashboards/atlas-overview.json" /var/lib/grafana/dashboards/atlas-overview.json

LOG "=== 6. node_exporter textfile + binding ==="
# Ajustar ARGS via override para habilitar textfile collector e escutar apenas em localhost
install -d -m 0755 /etc/systemd/system/prometheus-node-exporter.service.d
cat > /etc/systemd/system/prometheus-node-exporter.service.d/override.conf <<'EOF'
[Service]
Environment=
Environment="ARGS=--web.listen-address=127.0.0.1:9100 --collector.textfile.directory=/var/lib/node_exporter/textfile --collector.systemd"
EOF

# Prometheus: bind localhost, sub-path /prometheus/, storage
install -d -m 0755 /etc/systemd/system/prometheus.service.d
cat > /etc/systemd/system/prometheus.service.d/override.conf <<'EOF'
[Service]
Environment=
Environment="ARGS=--web.listen-address=127.0.0.1:9090 --web.external-url=http://atlas/prometheus/ --web.route-prefix=/prometheus/ --storage.tsdb.retention.time=90d --storage.tsdb.retention.size=10GB"
EOF

# Alertmanager: bind localhost, sub-path /alertmanager/
install -d -m 0755 /etc/systemd/system/prometheus-alertmanager.service.d
cat > /etc/systemd/system/prometheus-alertmanager.service.d/override.conf <<'EOF'
[Service]
Environment=
Environment="ARGS=--web.listen-address=127.0.0.1:9093 --web.external-url=http://atlas/alertmanager/ --web.route-prefix=/alertmanager/"
EOF

LOG "=== 7. systemd reload + enable ==="
systemctl daemon-reload
systemctl enable --now prometheus-node-exporter
systemctl enable --now prometheus
systemctl enable --now prometheus-alertmanager
systemctl enable --now grafana-server

sleep 3
LOG "=== 8. Status ==="
for s in prometheus-node-exporter prometheus prometheus-alertmanager grafana-server; do
    printf "  %-30s %s\n" "$s" "$(systemctl is-active "$s")"
done

LOG "=== 9. Health checks ==="
curl -sf http://127.0.0.1:9100/metrics       > /dev/null && echo "  node_exporter  : OK" || echo "  node_exporter  : FAIL"
curl -sf http://127.0.0.1:9090/prometheus/-/ready >/dev/null && echo "  prometheus     : OK" || echo "  prometheus     : FAIL"
curl -sf http://127.0.0.1:9093/alertmanager/-/ready >/dev/null && echo "  alertmanager   : OK" || echo "  alertmanager   : FAIL"
curl -sf http://127.0.0.1:3000/grafana/api/health    >/dev/null && echo "  grafana        : OK" || echo "  grafana        : FAIL"

LOG "=== 10. Nginx integration ==="
NGINX_SITE=""
for c in /etc/nginx/sites-enabled/portal-atlas /etc/nginx/sites-enabled/atlas /etc/nginx/sites-enabled/default; do
    [ -f "$c" ] && NGINX_SITE="$c" && break
done
if [ -n "$NGINX_SITE" ]; then
    install -o root -g root -m 0644 "$STAGE/deploy/nginx-monitoring.conf" /etc/nginx/snippets/atlas-monitoring.conf
    if ! grep -q 'atlas-monitoring.conf' "$NGINX_SITE"; then
        # insere include antes do ultimo } do server block principal
        python3 - "$NGINX_SITE" <<'PY'
import sys, re
p = sys.argv[1]
s = open(p).read()
snip = "    include snippets/atlas-monitoring.conf;\n"
# encontra o ultimo "}" (fim do server{}) e insere antes
idx = s.rfind("}")
if "atlas-monitoring.conf" not in s and idx > 0:
    open(p,"w").write(s[:idx] + snip + s[idx:])
    print("  include inserido em", p)
else:
    print("  include ja presente")
PY
    else
        echo "  include ja presente em $NGINX_SITE"
    fi
    if nginx -t 2>&1 | grep -q 'successful'; then
        systemctl reload nginx && echo "  nginx reloaded OK"
    else
        echo "  !! nginx -t FALHOU, revisar $NGINX_SITE"
        nginx -t
    fi
else
    echo "  AVISO: site nginx nao encontrado, configure manualmente"
fi

LOG "=== 11. Metric inicial atlas_backup ==="
if [[ -f /var/lib/atlas-backup/last.json ]]; then
    /usr/local/sbin/atlas-backup.sh metrics 2>/dev/null || true
fi

LOG "=== OK ==="
