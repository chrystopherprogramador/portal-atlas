#!/usr/bin/env bash
# gerenciar-drives.sh - administra a GPO de mapeamento de drives.
# Comandos:
#   init                                # cria GPO + linka (idempotente)
#   set-config <arquivo.json>           # salva config + regera Drives.xml
#   apply                               # regera com a config corrente
#   info                                # estado atual (kv) + dump da config
#   list-shares                         # lista shares Samba (atalho)
#   disable                             # remove link da GPO
set -euo pipefail

CONF_DIR="/etc/portal-atlas"
CONF_STATE="$CONF_DIR/drives.state"     # GPO_GUID
CONF_JSON="$CONF_DIR/drives.json"       # config das mapeamentos
ADMIN_CONF="$CONF_DIR/admin.conf"

GPO_NAME="Atlas - Mapeamento de Drives"
DOMAIN="$(hostname -d 2>/dev/null || echo texasco.local)"
NETBIOS="$(echo "$DOMAIN" | cut -d. -f1 | tr '[:lower:]' '[:upper:]')"
SYSVOL="/var/lib/samba/sysvol/${DOMAIN}/Policies"
BUILDER="/usr/local/sbin/drives-builder.py"

mkdir -p "$CONF_DIR"

# Credenciais para samba-tool
SAMBA_ADMIN_USER="Administrator"
SAMBA_ADMIN_PASSWORD=""
[[ -f "$ADMIN_CONF" ]] && . "$ADMIN_CONF" || true
export SAMBA_ADMIN_USER SAMBA_ADMIN_PASSWORD

stool() {
    if [[ -n "$SAMBA_ADMIN_PASSWORD" ]]; then
        samba-tool "$@" -U"$SAMBA_ADMIN_USER" --password="$SAMBA_ADMIN_PASSWORD" 2>&1 \
            | grep -v 'WARNING: Using password on command line'
    else
        samba-tool "$@"
    fi
}

load_state() { [[ -f "$CONF_STATE" ]] && . "$CONF_STATE" || true; }
save_state() {
    cat > "$CONF_STATE" <<EOF
GPO_GUID="${GPO_GUID:-}"
EOF
    chmod 644 "$CONF_STATE"
}

# ---- ensure GPO ----------------------------------------------------------
ensure_gpo() {
    load_state
    if [[ -n "${GPO_GUID:-}" && -d "${SYSVOL}/${GPO_GUID}" ]]; then
        return 0
    fi
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
    save_state
}

ensure_link() {
    local domain_dn="DC=$(echo "$DOMAIN" | sed 's/\./,DC=/g')"
    if ! stool gpo getlink "$domain_dn" 2>/dev/null | grep -q "$GPO_GUID"; then
        stool gpo setlink "$domain_dn" "$GPO_GUID" >/dev/null
        echo "  > GPO linkada em $domain_dn"
    fi
}

apply_xml() {
    [[ -f "$CONF_JSON" ]] || { echo "{\"ti_group\":\"\",\"domain\":\"$NETBIOS\",\"mappings\":[]}" > "$CONF_JSON"; }
    python3 "$BUILDER" write "${SYSVOL}/${GPO_GUID}" "$GPO_GUID" "$CONF_JSON"
    samba-tool ntacl sysvolreset >/dev/null 2>&1 || true
}

# ---- comandos ------------------------------------------------------------
cmd_init() {
    ensure_gpo
    ensure_link
    apply_xml
    echo "OK: GPO de drives pronta (guid=$GPO_GUID)"
}

cmd_set_config() {
    local src="${1:-}"
    [[ -f "$src" ]] || { echo "ERRO: arquivo nao existe: $src" >&2; exit 1; }
    # valida JSON
    python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$src" \
        || { echo "ERRO: JSON invalido" >&2; exit 1; }
    install -m 644 -o root -g root "$src" "$CONF_JSON"
    ensure_gpo
    ensure_link
    apply_xml
    echo "OK: config atualizada"
}

cmd_apply() {
    ensure_gpo
    ensure_link
    apply_xml
    echo "OK: re-aplicada"
}

cmd_info() {
    load_state
    echo "GPO_NAME=${GPO_NAME}"
    echo "GPO_GUID=${GPO_GUID:-}"
    echo "DOMAIN=${DOMAIN}"
    echo "NETBIOS=${NETBIOS}"
    if [[ -n "${GPO_GUID:-}" ]]; then
        local domain_dn="DC=$(echo "$DOMAIN" | sed 's/\./,DC=/g')"
        if stool gpo getlink "$domain_dn" 2>/dev/null | grep -q "$GPO_GUID"; then
            echo "LINKED=1"
        else
            echo "LINKED=0"
        fi
        if [[ -f "${SYSVOL}/${GPO_GUID}/GPT.INI" ]]; then
            echo "GPT_VERSION=$(grep -i '^Version=' "${SYSVOL}/${GPO_GUID}/GPT.INI" \
                | head -n1 | cut -d= -f2 | tr -d '\r')"
        fi
        local xml="${SYSVOL}/${GPO_GUID}/User/Preferences/Drives/Drives.xml"
        echo "XML_EXISTS=$([[ -f "$xml" ]] && echo 1 || echo 0)"
        [[ -f "$xml" ]] && echo "XML_SIZE=$(stat -c%s "$xml")"
    fi
    echo "---CONFIG---"
    if [[ -f "$CONF_JSON" ]]; then
        cat "$CONF_JSON"
    else
        echo "{}"
    fi
}

cmd_list_shares() {
    /usr/local/sbin/gerenciar-share.sh list 2>/dev/null \
        | awk -F'|' '$4=="1" {print $1}' | sort
}

cmd_disable() {
    load_state
    [[ -z "${GPO_GUID:-}" ]] && { echo "ja desabilitado"; exit 0; }
    local domain_dn="DC=$(echo "$DOMAIN" | sed 's/\./,DC=/g')"
    stool gpo dellink "$domain_dn" "$GPO_GUID" >/dev/null 2>&1 || true
    echo "OK: link removido"
}

case "${1:-}" in
    init)        cmd_init;;
    set-config)  shift; cmd_set_config "${1:-}";;
    apply)       cmd_apply;;
    info)        cmd_info;;
    list-shares) cmd_list_shares;;
    disable)     cmd_disable;;
    *) echo "Uso: $0 {init|set-config <json>|apply|info|list-shares|disable}"; exit 2;;
esac
