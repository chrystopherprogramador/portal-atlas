#!/bin/bash
# gerenciar-rustdesk.sh — controle dos containers hbbs/hbbr e do instalador
set -e

COMPOSE_DIR=/opt/rustdesk
DATA_DIR=/var/lib/rustdesk-data
INSTALLER=$DATA_DIR/rustdesk-original.exe
RUSTDESK_VERSION="1.3.7"
RUSTDESK_URL="https://github.com/rustdesk/rustdesk/releases/download/${RUSTDESK_VERSION}/rustdesk-${RUSTDESK_VERSION}-x86_64.exe"

case "${1:-}" in
  up)
    cd "$COMPOSE_DIR"
    docker compose up -d
    sleep 3
    ls -la "$DATA_DIR" 2>/dev/null || true
    ;;
  down)
    cd "$COMPOSE_DIR"
    docker compose down
    ;;
  restart)
    cd "$COMPOSE_DIR"
    docker compose restart
    sleep 2
    docker ps --filter name=hbb
    ;;
  status)
    docker ps --filter name=hbb --format "{{.Names}}|{{.Status}}|{{.Ports}}"
    ;;
  logs)
    cd "$COMPOSE_DIR"
    docker compose logs --tail=100 ${2:-}
    ;;
  fetch_client)
    mkdir -p "$DATA_DIR"
    echo "Baixando $RUSTDESK_URL ..."
    if command -v curl >/dev/null 2>&1; then
      curl -fL --progress-bar -o "$INSTALLER.tmp" "$RUSTDESK_URL"
    else
      wget -O "$INSTALLER.tmp" "$RUSTDESK_URL"
    fi
    SIZE=$(stat -c%s "$INSTALLER.tmp" 2>/dev/null || echo 0)
    if [ "$SIZE" -lt 1000000 ]; then
      echo "ERRO: download muito pequeno ($SIZE bytes)" >&2
      rm -f "$INSTALLER.tmp"
      exit 2
    fi
    mv "$INSTALLER.tmp" "$INSTALLER"
    chmod 644 "$INSTALLER"
    echo "OK $INSTALLER ($SIZE bytes)"
    ;;
  *)
    echo "uso: $0 {up|down|restart|status|logs|fetch_client}"
    exit 2
    ;;
esac
