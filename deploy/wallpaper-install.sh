#!/usr/bin/env bash
# wallpaper-install.sh - instala helper e roda init da GPO de papel de parede.
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "rode como root"; exit 1; }
SRC="$(cd "$(dirname "$0")" && pwd)"

install -m 750 "$SRC/gerenciar-wallpaper.sh" /usr/local/sbin/gerenciar-wallpaper.sh
install -m 755 "$SRC/wallpaper-pol.py"       /usr/local/sbin/wallpaper-pol.py

mkdir -p /etc/portal-atlas
chmod 755 /etc/portal-atlas

/usr/local/sbin/gerenciar-wallpaper.sh init
