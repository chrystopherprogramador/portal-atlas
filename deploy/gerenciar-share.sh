#!/usr/bin/env bash
# gerenciar-share.sh - cria/remove compartilhamento Samba gerenciado pelo portal
# Uso:
#   gerenciar-share.sh add <nome> <grupo> [descricao...]
#   gerenciar-share.sh del <nome>
#   gerenciar-share.sh setgroup <nome> <grupo>
#
# Shares gerenciados sao marcados com '# PORTAL_SHARE' no smb.conf.

set -euo pipefail

ACTION="${1:-}"
SMB_CONF="/etc/samba/smb.conf"
SHARES_ROOT="/srv/samba/shares"
MARK="# PORTAL_SHARE"
LOCK_FILE="/var/run/portal-share.lock"

usage() {
    echo "Uso: $0 {add|del|setgroup|list} ..."
    exit 2
}

# ---- Validacao basica ----
valid_name() {
    [[ "$1" =~ ^[A-Za-z0-9_.-]{1,32}$ ]]
}

ensure_group() {
    local grp="$1"
    if ! samba-tool group list 2>/dev/null | grep -Fxq "$grp"; then
        echo "ERRO: grupo '$grp' nao existe no AD" >&2
        return 1
    fi
}

reload_samba() {
    smbcontrol all reload-config >/dev/null 2>&1 || true
    testparm -s "$SMB_CONF" >/dev/null 2>&1
}

# ---- Remove bloco de um share do smb.conf ----
strip_share_block() {
    local name="$1"
    python3 - "$SMB_CONF" "$name" <<'PYEOF'
import sys, re
path, name = sys.argv[1], sys.argv[2]
with open(path) as f:
    lines = f.readlines()
out, skip = [], False
pat = re.compile(r"^\[" + re.escape(name) + r"\]\s*$", re.I)
for ln in lines:
    if ln.strip().startswith("[") and ln.strip().endswith("]"):
        skip = bool(pat.match(ln.strip()))
    if not skip:
        out.append(ln)
# remove blank-line duplicates
final = []
for ln in out:
    if ln.strip() == "" and final and final[-1].strip() == "":
        continue
    final.append(ln)
with open(path, "w") as f:
    f.writelines(final)
PYEOF
}

# ---- Acoes ----
cmd_add() {
    local name="$1" grp="$2"; shift 2
    local desc="${*:-Compartilhamento $name}"
    valid_name "$name"     || { echo "nome invalido"; exit 1; }
    valid_name "$grp"      || { echo "grupo invalido"; exit 1; }
    ensure_group "$grp"

    if grep -qiE "^\[${name}\]" "$SMB_CONF"; then
        echo "ERRO: share [$name] ja existe em smb.conf" >&2
        exit 1
    fi

    local path="$SHARES_ROOT/$name"
    mkdir -p "$path"
    chown "root:${grp}" "$path"
    chmod 2770 "$path"
    # ACL default: herda grupo rw
    setfacl -m "g:${grp}:rwx" "$path"
    setfacl -d -m "u::rwx,g::rwx,g:${grp}:rwx,o::---" "$path"

    cp -a "$SMB_CONF" "${SMB_CONF}.bak.$(date +%s)"
    cat >> "$SMB_CONF" <<EOF

[$name]
    ${MARK}
    comment = $desc
    path = $path
    browseable = Yes
    read only = No
    valid users = @${grp} @"Domain Admins"
    create mask = 0660
    directory mask = 2770
    force create mode = 0660
    force directory mode = 2770
    force group = ${grp}
    vfs objects = acl_xattr
    map acl inherit = Yes
EOF

    if ! testparm -s "$SMB_CONF" >/dev/null 2>&1; then
        echo "ERRO: testparm falhou; revertendo" >&2
        cp -a "${SMB_CONF}.bak."* "$SMB_CONF" 2>/dev/null || true
        exit 1
    fi
    reload_samba
    echo "OK: share [$name] criado em $path (grupo=$grp)"
}

cmd_del() {
    local name="$1"
    valid_name "$name" || { echo "nome invalido"; exit 1; }
    [[ "$name" =~ ^(Arquivos|sysvol|netlogon|IPC\$|print\$|VPN\$)$ ]] \
        && { echo "nao removo share reservado: $name"; exit 1; }

    if ! grep -qiE "^\[${name}\]" "$SMB_CONF"; then
        echo "share [$name] nao existe"; exit 0
    fi

    cp -a "$SMB_CONF" "${SMB_CONF}.bak.$(date +%s)"
    strip_share_block "$name"
    if ! testparm -s "$SMB_CONF" >/dev/null 2>&1; then
        echo "ERRO: testparm falhou; revertendo" >&2
        cp -a "${SMB_CONF}.bak."* "$SMB_CONF" 2>/dev/null || true
        exit 1
    fi
    reload_samba

    local path="$SHARES_ROOT/$name"
    if [[ -d "$path" ]]; then
        mv "$path" "${path}.removed.$(date +%s)"
        echo "OK: share removido; dados movidos para ${path}.removed.*"
    else
        echo "OK: share [$name] removido de smb.conf"
    fi
}

cmd_setgroup() {
    local name="$1" grp="$2"
    valid_name "$name" || { echo "nome invalido"; exit 1; }
    valid_name "$grp"  || { echo "grupo invalido"; exit 1; }
    ensure_group "$grp"

    local path="$SHARES_ROOT/$name"
    [[ -d "$path" ]] || { echo "ERRO: pasta nao existe: $path"; exit 1; }

    chown "root:${grp}" "$path"
    chmod 2770 "$path"
    setfacl -b "$path" || true
    setfacl -m "g:${grp}:rwx" "$path"
    setfacl -d -m "u::rwx,g::rwx,g:${grp}:rwx,o::---" "$path"

    # Substitui a linha valid_users e force group
    python3 - "$SMB_CONF" "$name" "$grp" <<'PYEOF'
import sys, re
path, name, grp = sys.argv[1], sys.argv[2], sys.argv[3]
with open(path) as f:
    txt = f.read()
pat = re.compile(r"(\[" + re.escape(name) + r"\][^\[]*)", re.I)
m = pat.search(txt)
if not m:
    sys.exit("bloco nao encontrado")
block = m.group(1)
block = re.sub(r"(?m)^\s*valid users\s*=.*$",  f"    valid users = @{grp} @\"Domain Admins\"", block)
block = re.sub(r"(?m)^\s*force group\s*=.*$", f"    force group = {grp}", block)
txt = txt[:m.start(1)] + block + txt[m.end(1):]
with open(path, "w") as f:
    f.write(txt)
PYEOF
    reload_samba
    echo "OK: share [$name] agora pertence ao grupo $grp"
}

cmd_list() {
    # Print 1 linha por share: name|path|group|managed(0/1)
    python3 - "$SMB_CONF" <<'PYEOF'
import sys, re
cur = None
shares = {}
with open(sys.argv[1]) as f:
    for line in f:
        s = line.strip()
        m = re.match(r"^\[(.+)\]$", s)
        if m:
            cur = m.group(1)
            shares[cur] = {"name": cur, "path": "", "valid_users": "", "managed": False, "comment": ""}
            continue
        if cur is None: continue
        if s.startswith("#"):
            if "PORTAL_SHARE" in s:
                shares[cur]["managed"] = True
            continue
        if "=" in s:
            k, v = [x.strip() for x in s.split("=", 1)]
            k = k.lower()
            if k == "path": shares[cur]["path"] = v
            elif k == "valid users": shares[cur]["valid_users"] = v
            elif k == "comment": shares[cur]["comment"] = v
for s in shares.values():
    print("|".join([
        s["name"], s["path"] or "-",
        s["valid_users"] or "-",
        "1" if s["managed"] else "0",
        s["comment"] or "-",
    ]))
PYEOF
}

# ---- Main ----
[[ $EUID -eq 0 ]] || { echo "precisa ser root"; exit 1; }
[[ -n "$ACTION" ]] || usage

exec 9>"$LOCK_FILE"
flock -x 9

case "$ACTION" in
    add)       shift; [[ $# -ge 2 ]] || usage; cmd_add "$@" ;;
    del)       shift; [[ $# -ge 1 ]] || usage; cmd_del "$1" ;;
    setgroup)  shift; [[ $# -ge 2 ]] || usage; cmd_setgroup "$1" "$2" ;;
    list)      cmd_list ;;
    *) usage ;;
esac
