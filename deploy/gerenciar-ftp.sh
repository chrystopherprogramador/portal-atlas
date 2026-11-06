#!/usr/bin/env bash
# gerenciar-ftp.sh - cria/remove/gerencia usuarios FTP locais (vsftpd)
# Uso:
#   gerenciar-ftp.sh add <user> <senha> [quota_mb]
#   gerenciar-ftp.sh del <user>
#   gerenciar-ftp.sh passwd <user> <novasenha>
#   gerenciar-ftp.sh lock <user>
#   gerenciar-ftp.sh unlock <user>
#   gerenciar-ftp.sh list
#   gerenciar-ftp.sh status
#   gerenciar-ftp.sh sessions
#   gerenciar-ftp.sh restart
#
# Convencao: usuarios FTP sao criados no grupo `ftpusers`,
# com home em /srv/ftp/<user>, shell /usr/sbin/nologin, e
# inseridos em /etc/vsftpd.userlist.

set -euo pipefail

ACTION="${1:-}"
FTP_GROUP="ftpusers"
FTP_ROOT="/srv/ftp"
USERLIST="/etc/vsftpd.userlist"

usage() {
    echo "Uso: $0 {add|del|passwd|lock|unlock|list|status|sessions|restart} ..." >&2
    exit 2
}

valid_name() {
    [[ "$1" =~ ^[a-z_][a-z0-9_-]{1,31}$ ]]
}

is_ftp_user() {
    local u="$1"
    id "$u" &>/dev/null || return 1
    id -nG "$u" 2>/dev/null | tr ' ' '\n' | grep -Fxq "$FTP_GROUP"
}

ensure_userlist() {
    [[ -f "$USERLIST" ]] || : > "$USERLIST"
    chmod 600 "$USERLIST"
}

# ---- ACOES -----------------------------------------------------------

cmd_add() {
    local user="$1" pass="$2" quota="${3:-0}"
    valid_name "$user" || { echo "ERRO: nome invalido"; exit 1; }
    if id "$user" &>/dev/null; then
        echo "ERRO: usuario '$user' ja existe no sistema" >&2
        exit 1
    fi

    getent group "$FTP_GROUP" >/dev/null || groupadd "$FTP_GROUP"
    mkdir -p "$FTP_ROOT"
    chmod 755 "$FTP_ROOT"

    local home="$FTP_ROOT/$user"
    useradd -m -d "$home" -s /usr/sbin/nologin -g "$FTP_GROUP" "$user"
    echo "${user}:${pass}" | chpasswd
    chown root:"$FTP_GROUP" "$home"
    chmod 755 "$home"
    # subdir gravavel (porque chroot exige home nao-gravavel? usamos allow_writeable_chroot=YES)
    mkdir -p "$home/files"
    chown "$user":"$FTP_GROUP" "$home/files"
    chmod 750 "$home/files"

    ensure_userlist
    grep -Fxq "$user" "$USERLIST" || echo "$user" >> "$USERLIST"

    echo "OK: usuario FTP '$user' criado em $home"
}

cmd_del() {
    local user="$1"
    valid_name "$user" || { echo "ERRO: nome invalido"; exit 1; }
    is_ftp_user "$user" || { echo "ERRO: '$user' nao e usuario FTP gerenciado"; exit 1; }

    pkill -KILL -u "$user" 2>/dev/null || true
    userdel -r "$user" 2>/dev/null || userdel "$user"

    ensure_userlist
    sed -i "/^${user}\$/d" "$USERLIST"

    # se home sobrou (userdel -r falha se em uso), arquiva
    if [[ -d "$FTP_ROOT/$user" ]]; then
        mv "$FTP_ROOT/$user" "$FTP_ROOT/${user}.removed.$(date +%s)"
    fi
    echo "OK: usuario FTP '$user' removido"
}

cmd_passwd() {
    local user="$1" pass="$2"
    is_ftp_user "$user" || { echo "ERRO: '$user' nao e usuario FTP"; exit 1; }
    echo "${user}:${pass}" | chpasswd
    # destrava se estava bloqueado
    usermod -U "$user" 2>/dev/null || true
    echo "OK: senha de '$user' alterada"
}

cmd_lock() {
    local user="$1"
    is_ftp_user "$user" || { echo "ERRO: '$user' nao e usuario FTP"; exit 1; }
    usermod -L "$user"
    sed -i "/^${user}\$/d" "$USERLIST"
    pkill -KILL -u "$user" 2>/dev/null || true
    echo "OK: '$user' bloqueado"
}

cmd_unlock() {
    local user="$1"
    is_ftp_user "$user" || { echo "ERRO: '$user' nao e usuario FTP"; exit 1; }
    usermod -U "$user"
    ensure_userlist
    grep -Fxq "$user" "$USERLIST" || echo "$user" >> "$USERLIST"
    echo "OK: '$user' liberado"
}

cmd_list() {
    # formato: user|home|locked(0/1)|size_kb|last_login
    getent group "$FTP_GROUP" >/dev/null || { echo ""; return 0; }
    local members
    members=$(getent group "$FTP_GROUP" | awk -F: '{print $4}' | tr ',' '\n' | sort -u)
    [[ -z "$members" ]] && { echo ""; return 0; }
    while IFS= read -r u; do
        [[ -z "$u" ]] && continue
        local home; home=$(getent passwd "$u" | cut -d: -f6)
        local locked=0
        if passwd -S "$u" 2>/dev/null | awk '{print $2}' | grep -qE '^(L|LK)$'; then
            locked=1
        fi
        local size_kb=0
        if [[ -d "$home" ]]; then
            size_kb=$(du -sk "$home" 2>/dev/null | awk '{print $1}')
        fi
        local last
        last=$(lastlog -u "$u" 2>/dev/null | tail -n1 | awk '{ if ($2=="**Never") print "nunca"; else { for(i=4;i<=NF;i++) printf "%s ", $i; print "" } }' | sed 's/ *$//')
        [[ -z "$last" ]] && last="-"
        echo "${u}|${home}|${locked}|${size_kb}|${last}"
    done <<< "$members"
}

cmd_status() {
    systemctl is-active vsftpd 2>/dev/null || echo "inactive"
}

cmd_sessions() {
    # quem esta conectado na 21 ou nas portas passivas
    ss -tnH "( sport = :21 or ( sport >= :30000 and sport <= :30100 ) )" 2>/dev/null \
        | awk '{print $5"|"$4}' | sort -u
}

cmd_restart() {
    systemctl restart vsftpd
    echo "OK: vsftpd reiniciado"
}

# ---- DISPATCHER ------------------------------------------------------

case "$ACTION" in
    add)      [[ $# -ge 3 ]] || usage; cmd_add      "$2" "$3" "${4:-0}";;
    del)      [[ $# -ge 2 ]] || usage; cmd_del      "$2";;
    passwd)   [[ $# -ge 3 ]] || usage; cmd_passwd   "$2" "$3";;
    lock)     [[ $# -ge 2 ]] || usage; cmd_lock     "$2";;
    unlock)   [[ $# -ge 2 ]] || usage; cmd_unlock   "$2";;
    list)     cmd_list;;
    status)   cmd_status;;
    sessions) cmd_sessions;;
    restart)  cmd_restart;;
    *)        usage;;
esac
