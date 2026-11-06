#!/usr/bin/env bash
# gerenciar-wallpaper.sh - administra a GPO de papel de parede do dominio
# Uso:
#   gerenciar-wallpaper.sh init                       # cria share + GPO + linka (idempotente)
#   gerenciar-wallpaper.sh set-image <arquivo>        # copia imagem para o share e bumpa GPO
#   gerenciar-wallpaper.sh set-style <0|2|6|10|22>    # regrava Registry.pol com estilo
#   gerenciar-wallpaper.sh info                       # estado atual (kv)
#   gerenciar-wallpaper.sh disable                    # remove link da GPO no dominio

set -euo pipefail

CONF="/etc/portal-atlas/wallpaper.conf"
ADMIN_CONF="/etc/portal-atlas/admin.conf"
SHARE_NAME="Wallpaper\$"
SHARE_PATH="/srv/samba/wallpaper"
IMAGE_NAME="fundo.jpg"
GPO_NAME="Atlas - Papel de Parede"
NETBIOS_HOST="$(hostname -s | tr '[:upper:]' '[:lower:]')"
DOMAIN="$(hostname -d 2>/dev/null || echo texasco.local)"
SYSVOL="/var/lib/samba/sysvol/${DOMAIN}/Policies"
SMB_CONF="/etc/samba/smb.conf"
HELPER="/usr/local/sbin/wallpaper-pol.py"

mkdir -p "$(dirname "$CONF")"

# Credenciais para samba-tool gpo (precisa de admin do AD)
SAMBA_ADMIN_USER="Administrator"
SAMBA_ADMIN_PASSWORD=""
[[ -f "$ADMIN_CONF" ]] && . "$ADMIN_CONF" || true

stool() {
    # samba-tool com credenciais do AD se disponiveis, senao confia em root
    if [[ -n "$SAMBA_ADMIN_PASSWORD" ]]; then
        samba-tool "$@" -U"$SAMBA_ADMIN_USER" --password="$SAMBA_ADMIN_PASSWORD" 2>&1 \
            | grep -v 'WARNING: Using password on command line'
    else
        samba-tool "$@"
    fi
}

load_conf()  { [[ -f "$CONF" ]] && . "$CONF" || true; }
save_conf()  {
    cat > "$CONF" <<EOF
GPO_GUID="${GPO_GUID:-}"
GPO_NAME="${GPO_NAME}"
SHARE="${SHARE_NAME}"
SHARE_PATH="${SHARE_PATH}"
IMAGE="${IMAGE_NAME}"
STYLE="${STYLE:-2}"
UNC="${UNC}"
EOF
    chmod 644 "$CONF"
}

unc_path() {
    echo "\\\\${NETBIOS_HOST}\\${SHARE_NAME}\\${IMAGE_NAME}"
}

# ---- ensure share -------------------------------------------------------
ensure_share() {
    mkdir -p "$SHARE_PATH"
    chown root:"Domain Users" "$SHARE_PATH" 2>/dev/null || chown root:root "$SHARE_PATH"
    chmod 755 "$SHARE_PATH"
    if ! grep -qiE "^\[${SHARE_NAME//\$/\\\$}\]" "$SMB_CONF"; then
        cp -a "$SMB_CONF" "${SMB_CONF}.bak.$(date +%s)"
        cat >> "$SMB_CONF" <<EOF

[${SHARE_NAME}]
    # PORTAL_WALLPAPER
    comment = Atlas - Papel de parede (somente leitura)
    path = ${SHARE_PATH}
    browseable = No
    read only = Yes
    guest ok = No
    valid users = @"Domain Users" @"Domain Admins"
EOF
        testparm -s "$SMB_CONF" >/dev/null 2>&1 || {
            cp -a "${SMB_CONF}.bak."* "$SMB_CONF" 2>/dev/null || true
            echo "ERRO: testparm falhou ao adicionar share" >&2; exit 1
        }
        smbcontrol all reload-config >/dev/null 2>&1 || true
    fi
}

# ---- ensure gpo ---------------------------------------------------------
ensure_gpo() {
    load_conf
    if [[ -n "${GPO_GUID:-}" && -d "${SYSVOL}/${GPO_GUID}" ]]; then
        return 0
    fi
    # Procura por nome
    local guid
    guid=$(stool gpo listall 2>/dev/null \
            | awk -v n="$GPO_NAME" 'BEGIN{RS=""; FS="\n"} index($0,"display name : "n){
                for(i=1;i<=NF;i++) if($i ~ /^GPO[[:space:]]*:/){gsub(/^GPO[[:space:]]*:[[:space:]]*/,"",$i); print $i}
            }' | head -n1)

    if [[ -z "$guid" ]]; then
        local out
        out=$(stool gpo create "$GPO_NAME")
        guid=$(echo "$out" | grep -oE '\{[A-F0-9-]+\}' | head -n1)
        echo "  > GPO criada: $guid"
    else
        echo "  > GPO existente: $guid"
    fi
    [[ -z "$guid" ]] && { echo "ERRO: nao consegui criar/localizar GPO" >&2; exit 1; }
    GPO_GUID="$guid"
}

ensure_link() {
    local domain_dn="DC=$(echo "$DOMAIN" | sed 's/\./,DC=/g')"
    if ! stool gpo getlink "$domain_dn" 2>/dev/null | grep -q "$GPO_GUID"; then
        stool gpo setlink "$domain_dn" "$GPO_GUID" >/dev/null
        echo "  > GPO linkada em $domain_dn"
    fi
}

apply_pol() {
    local style="${1:-${STYLE:-2}}"
    UNC="$(unc_path)"
    STYLE="$style"
    python3 "$HELPER" write "${SYSVOL}/${GPO_GUID}" "$UNC" "$style"

    # Le a versao nova do GPT.INI e atualiza atributos AD da GPO
    local v
    v=$(grep -i '^Version=' "${SYSVOL}/${GPO_GUID}/GPT.INI" \
          | head -n1 | cut -d= -f2 | tr -d '\r')
    SAMBA_ADMIN_USER="$SAMBA_ADMIN_USER" \
    SAMBA_ADMIN_PASSWORD="$SAMBA_ADMIN_PASSWORD" \
    python3 /usr/local/sbin/wallpaper-ad-update.py "$GPO_GUID" "${v:-0}" \
        || echo "  > aviso: nao consegui atualizar atributos AD"

    # ACLs do sysvol (replica permissoes corretas no Registry.pol)
    samba-tool ntacl sysvolreset >/dev/null 2>&1 || true
    save_conf
}

# ---- comandos -----------------------------------------------------------
cmd_init() {
    ensure_share
    ensure_gpo
    ensure_link
    : "${STYLE:=2}"
    apply_pol "$STYLE"
    echo "OK: wallpaper GPO pronta (guid=$GPO_GUID)"
}

cmd_set_image() {
    local src="${1:-}"
    [[ -f "$src" ]] || { echo "ERRO: arquivo nao existe: $src" >&2; exit 1; }
    load_conf
    [[ -z "${GPO_GUID:-}" ]] && { echo "ERRO: rode 'init' antes" >&2; exit 1; }
    install -m 0644 -o root -g root "$src" "${SHARE_PATH}/${IMAGE_NAME}"
    apply_pol "${STYLE:-2}"
    echo "OK: imagem atualizada (size=$(stat -c%s "${SHARE_PATH}/${IMAGE_NAME}") bytes)"
}

cmd_set_style() {
    local s="${1:-}"
    case "$s" in 0|2|6|10|22) ;; *) echo "estilo invalido (use 0,2,6,10,22)"; exit 1;; esac
    load_conf
    [[ -z "${GPO_GUID:-}" ]] && { echo "ERRO: rode 'init' antes" >&2; exit 1; }
    apply_pol "$s"
    echo "OK: estilo=$s"
}

cmd_info() {
    load_conf
    local img_path="${SHARE_PATH}/${IMAGE_NAME}"
    local has_img=0 size=0 mtime=""
    if [[ -f "$img_path" ]]; then
        has_img=1
        size=$(stat -c%s "$img_path")
        mtime=$(stat -c%y "$img_path" | cut -d'.' -f1)
    fi
    echo "GPO_GUID=${GPO_GUID:-}"
    echo "GPO_NAME=${GPO_NAME}"
    echo "SHARE=${SHARE_NAME}"
    echo "UNC=$(unc_path)"
    echo "STYLE=${STYLE:-2}"
    echo "IMAGE_PATH=${img_path}"
    echo "IMAGE_EXISTS=${has_img}"
    echo "IMAGE_SIZE=${size}"
    echo "IMAGE_MTIME=${mtime}"
    if [[ -n "${GPO_GUID:-}" && -f "${SYSVOL}/${GPO_GUID}/GPT.INI" ]]; then
        local v
        v=$(grep -i '^Version=' "${SYSVOL}/${GPO_GUID}/GPT.INI" | head -n1 | cut -d= -f2 | tr -d '\r')
        echo "GPT_VERSION=${v:-0}"
    fi
    local domain_dn="DC=$(echo "$DOMAIN" | sed 's/\./,DC=/g')"
    if [[ -n "${GPO_GUID:-}" ]] && stool gpo getlink "$domain_dn" 2>/dev/null | grep -q "$GPO_GUID"; then
        echo "LINKED=1"
    else
        echo "LINKED=0"
    fi
}

cmd_disable() {
    load_conf
    [[ -z "${GPO_GUID:-}" ]] && { echo "ja desabilitado"; exit 0; }
    local domain_dn="DC=$(echo "$DOMAIN" | sed 's/\./,DC=/g')"
    stool gpo dellink "$domain_dn" "$GPO_GUID" >/dev/null 2>&1 || true
    echo "OK: link removido"
}

case "${1:-}" in
    init)      cmd_init;;
    set-image) shift; cmd_set_image "${1:-}";;
    set-style) shift; cmd_set_style "${1:-}";;
    info)      cmd_info;;
    disable)   cmd_disable;;
    *) echo "Uso: $0 {init|set-image <arq>|set-style <0|2|6|10|22>|info|disable}"; exit 2;;
esac
