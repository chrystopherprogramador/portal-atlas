#!/usr/bin/env python3
"""
gpo-policy.py -- editor de politicas Registry.pol estilo GPMC.

Uso (executar como root via sudo):
    gpo-policy.py list   <gpo_dir>
    gpo-policy.py set    <gpo_dir> <gpo_guid> <scope> <key> <name> <type> <data>
    gpo-policy.py unset  <gpo_dir> <gpo_guid> <scope> <key> <name>
    gpo-policy.py raw    <gpo_dir> <scope>          # imprime PReg cru parseado

scope = user | machine
type  = REG_DWORD | REG_SZ | REG_EXPAND_SZ | REG_QWORD | REG_BINARY
"""
import sys, os, re, json
from pathlib import Path

# carrega o modulo do portal sem precisar instalar pacote
sys.path.insert(0, "/opt/atlas-portal")
from modules.gpo_policy import (parse_pol, write_pol,
                                REG_DWORD, REG_SZ, REG_EXPAND_SZ, REG_QWORD, REG_BINARY,
                                TYPE_NAMES)

TYPE_BY_NAME = {v: k for k, v in TYPE_NAMES.items()}

# Registry.pol CSE GUID + tool GUID (para gPCMachineExtensionNames / gPCUserExtensionNames)
CSE_REG  = "{35378EAC-683F-11D2-A89A-00C04FBBCFA2}"
TOOL_REG = "{0F6B957D-509E-11D1-A7CC-0000F87571E3}"
EXT_VAL  = f"[{CSE_REG}{TOOL_REG}]"


def pol_path(gpo_dir: Path, scope: str) -> Path:
    sub = "Machine" if scope == "machine" else "User"
    return gpo_dir / sub / "Registry.pol"


def load_entries(gpo_dir: Path, scope: str):
    return parse_pol(pol_path(gpo_dir, scope))


def save_entries(gpo_dir: Path, scope: str, entries):
    p = pol_path(gpo_dir, scope)
    write_pol(entries, p)
    try:
        os.chmod(p, 0o664)
    except Exception:
        pass


def bump_gpt_ini(gpo_dir: Path, scope: str, display_name="Atlas - GPO") -> int:
    path = gpo_dir / "GPT.INI"
    version = 0
    if path.exists():
        txt = path.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"^\s*Version\s*=\s*(\d+)", txt, re.M | re.I)
        if m:
            version = int(m.group(1))
    user_part = (version >> 16) & 0xFFFF
    machine_part = version & 0xFFFF
    if scope == "machine":
        machine_part = (machine_part + 1) & 0xFFFF
    else:
        user_part = (user_part + 1) & 0xFFFF
    new = (user_part << 16) | machine_part
    path.write_text(
        "[General]\r\nVersion=" + str(new) + "\r\n"
        f"displayName={display_name}\r\n",
        encoding="utf-8",
    )
    return new


def update_ad(guid: str, version: int, scope: str):
    """Atualiza versionNumber + ext names da GPO via samdb."""
    import ldb
    from samba.samdb import SamDB
    from samba.credentials import Credentials
    from samba.auth import system_session
    from samba import param

    if not guid.startswith("{"):
        guid = "{" + guid.strip("{}").upper() + "}"

    lp = param.LoadParm(); lp.load_default()
    creds = Credentials(); creds.guess(lp)
    user = os.environ.get("SAMBA_ADMIN_USER", "")
    pwd  = os.environ.get("SAMBA_ADMIN_PASSWORD", "")
    if not (user and pwd):
        # fallback: ler /etc/portal-atlas/admin.conf (rodamos como root via sudo)
        try:
            with open("/etc/portal-atlas/admin.conf", "r", encoding="utf-8") as f:
                for ln in f:
                    ln = ln.strip()
                    if ln.startswith("SAMBA_ADMIN_USER"):
                        user = ln.split("=", 1)[1].strip().strip('"').strip("'")
                    elif ln.startswith("SAMBA_ADMIN_PASSWORD"):
                        pwd = ln.split("=", 1)[1].strip().strip('"').strip("'")
        except Exception:
            pass
    if user and pwd:
        creds.set_username(user); creds.set_password(pwd)

    samdb = SamDB(url="ldap://localhost",
                  session_info=system_session(),
                  credentials=creds, lp=lp)
    domain_dn = str(samdb.domain_dn())
    dn = f"CN={guid},CN=Policies,CN=System,{domain_dn}"
    attr = "gPCMachineExtensionNames" if scope == "machine" else "gPCUserExtensionNames"

    res = samdb.search(base=dn, scope=ldb.SCOPE_BASE, attrs=[attr])
    cur = ""
    if res and res[0].get(attr):
        cur = str(res[0][attr][0], "utf-8", "ignore")

    m = ldb.Message()
    m.dn = ldb.Dn(samdb, dn)
    if CSE_REG.upper() not in cur.upper():
        m[attr] = ldb.MessageElement(EXT_VAL, ldb.FLAG_MOD_REPLACE, attr)
    m["versionNumber"] = ldb.MessageElement(str(version), ldb.FLAG_MOD_REPLACE, "versionNumber")
    m["flags"] = ldb.MessageElement("0", ldb.FLAG_MOD_REPLACE, "flags")
    samdb.modify(m)


# ------------------- comandos --------------------------------------------
def cmd_list(gpo_dir: Path):
    out = {"machine": load_entries(gpo_dir, "machine"),
           "user":    load_entries(gpo_dir, "user")}
    print(json.dumps(out, indent=2, ensure_ascii=False))


def cmd_raw(gpo_dir: Path, scope: str):
    for e in load_entries(gpo_dir, scope):
        t = TYPE_NAMES.get(e["type"], str(e["type"]))
        print(f"{e['key']} :: {e['name']} ({t}) = {e['data']}")


def cmd_set(gpo_dir: Path, guid: str, scope: str, key: str, name: str, vtype: str, data):
    if vtype not in TYPE_BY_NAME:
        print(f"tipo invalido: {vtype}", file=sys.stderr); sys.exit(2)
    t = TYPE_BY_NAME[vtype]
    if t in (REG_DWORD, REG_QWORD):
        data = int(data)
    entries = load_entries(gpo_dir, scope)
    # remove duplicado mesmo key/name
    entries = [e for e in entries
               if not (e["key"].lower() == key.lower() and e["name"].lower() == name.lower())]
    entries.append({"key": key, "name": name, "type": t, "data": data})
    save_entries(gpo_dir, scope, entries)
    v = bump_gpt_ini(gpo_dir, scope)
    ad_err = ""
    try:
        update_ad(guid, v, scope)
    except Exception as e:
        ad_err = f"FALHA AD update: {e}"
    msg = f"OK set {scope} {key}::{name}={data} version={v}"
    if ad_err:
        print(msg + " [" + ad_err + "]")
        sys.exit(3)
    print(msg)


def cmd_unset(gpo_dir: Path, guid: str, scope: str, key: str, name: str):
    entries = load_entries(gpo_dir, scope)
    new = [e for e in entries
           if not (e["key"].lower() == key.lower() and e["name"].lower() == name.lower())]
    if len(new) == len(entries):
        print(f"(nada para remover)"); return
    save_entries(gpo_dir, scope, new)
    v = bump_gpt_ini(gpo_dir, scope)
    ad_err = ""
    try:
        update_ad(guid, v, scope)
    except Exception as e:
        ad_err = f"FALHA AD update: {e}"
    msg = f"OK unset {scope} {key}::{name} version={v}"
    if ad_err:
        print(msg + " [" + ad_err + "]")
        sys.exit(3)
    print(msg)


def main():
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(2)
    action = sys.argv[1]
    gpo_dir = Path(sys.argv[2])
    if not gpo_dir.exists():
        print(f"gpo_dir nao existe: {gpo_dir}", file=sys.stderr); sys.exit(2)
    if action == "list":
        cmd_list(gpo_dir)
    elif action == "raw":
        cmd_raw(gpo_dir, sys.argv[3])
    elif action == "set":
        # set <gpo_dir> <gpo_guid> <scope> <key> <name> <type> <data>
        cmd_set(gpo_dir, sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6], sys.argv[7], sys.argv[8])
    elif action == "unset":
        cmd_unset(gpo_dir, sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6])
    else:
        print(__doc__); sys.exit(2)


if __name__ == "__main__":
    main()
