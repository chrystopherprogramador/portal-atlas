#!/usr/bin/env python3
"""
drives-builder.py -- gera Drives.xml (Group Policy Preferences) + bumpa GPT.INI
+ atualiza atributos AD da GPO de Mapeamento de Drives.

Uso:
    drives-builder.py write   <gpo_dir> <gpo_guid> <mappings.json>
    drives-builder.py info    <gpo_dir>

mappings.json:
{
  "ti_group":  "TI",                    # opcional: grupo que ve TODOS os drives
  "domain":    "TEXASCO",               # netbios
  "mappings": [
     {"letter":"F","unc":"\\\\atlas\\Financeiro","label":"Financeiro","groups":["Financeiro"]},
     {"letter":"C","unc":"\\\\atlas\\Comercial","label":"Comercial","groups":["Comercial"]}
  ]
}
"""
import sys, os, re, json, subprocess, uuid, time
from pathlib import Path

# ----- GUIDs constantes do GPP --------------------------------------------
DRIVES_CLSID  = "{8FDDCC1A-0C3C-43cd-A6B4-71A6DF20DA8C}"
DRIVE_CLSID   = "{935D1B74-9CB8-4e3c-9914-7DD559B7A417}"
FILTER_CLSID  = "{0F3BA08D-6088-441d-8629-3C8A3A0D5141}"  # nao requerido mas comum
CSE_DRIVES    = "{5794DAFD-BE60-433f-88A2-1A31939AC01F}"  # Drive Maps client-side
TOOL_DRIVES   = "{2EA1A81B-48E5-45E9-8BB7-A6E3AC170006}"  # GPP Drive Maps editor
CSE_PREF_WRAP = "{00000000-0000-0000-0000-000000000000}"  # GPP wrapper

# Para o atributo gPCUserExtensionNames (User Configuration)
USER_EXT = f"[{CSE_PREF_WRAP}{TOOL_DRIVES}][{CSE_DRIVES}{TOOL_DRIVES}]"


# ----- helpers ------------------------------------------------------------
def xml_escape(s: str) -> str:
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;")
             .replace("'", "&apos;"))


def get_sid(name: str, domain: str) -> str:
    """Retorna SID do grupo via wbinfo. Retorna '' se nao encontrar."""
    full = f"{domain}\\{name}"
    try:
        r = subprocess.run(["wbinfo", "-n", full],
                           capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            return r.stdout.strip().split()[0]
    except Exception:
        pass
    # fallback: tenta sem dominio
    try:
        r = subprocess.run(["wbinfo", "-n", name],
                           capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            return r.stdout.strip().split()[0]
    except Exception:
        pass
    return ""


def build_drives_xml(spec: dict) -> bytes:
    domain = spec.get("domain", "TEXASCO")
    ti_group = spec.get("ti_group", "").strip() or None
    changed = time.strftime("%Y-%m-%d %H:%M:%S")

    out = []
    out.append('<?xml version="1.0" encoding="utf-8"?>')
    out.append(f'<Drives clsid="{DRIVES_CLSID}">')

    for m in spec.get("mappings", []):
        letter = (m.get("letter") or "").strip().upper().rstrip(":")
        if not re.match(r"^[A-Z]$", letter):
            continue
        unc = (m.get("unc") or "").strip()
        if not unc:
            continue
        label  = m.get("label") or letter
        action = (m.get("action") or "U").strip().upper()
        if action not in ("C", "U", "R", "D"):
            action = "U"
        groups = list(m.get("groups", []))

        # TI ganha todos os drives (OR no filtro)
        if ti_group and ti_group not in groups:
            groups.append(ti_group)

        drive_uid = "{" + str(uuid.uuid4()).upper() + "}"
        out.append(
            f'\t<Drive clsid="{DRIVE_CLSID}" name="{letter}:" status="{letter}:" '
            f'image="2" changed="{changed}" uid="{drive_uid}" bypassErrors="1">'
        )
        out.append(
            f'\t\t<Properties action="{action}" thisDrive="NOCHANGE" allDrives="NOCHANGE" '
            f'userName="" path="{xml_escape(unc)}" label="{xml_escape(label)}" '
            f'persistent="1" useLetter="1" letter="{letter}"/>'
        )

        if groups:
            out.append('\t\t<Filters>')
            for i, g in enumerate(groups):
                sid = get_sid(g, domain)
                bool_op = "AND" if i == 0 else "OR"
                out.append(
                    f'\t\t\t<FilterGroup bool="{bool_op}" not="0" '
                    f'name="{domain}\\{xml_escape(g)}" sid="{sid}" '
                    f'userContext="1" primaryGroup="0" localGroup="0"/>'
                )
            out.append('\t\t</Filters>')

        out.append('\t</Drive>')

    out.append('</Drives>')
    return ("\r\n".join(out) + "\r\n").encode("utf-8")


def bump_gpt_ini(path: Path, display_name="Atlas - Mapeamento de Drives") -> int:
    """Incrementa a parte 'User' (high 16 bits) do Version em GPT.INI."""
    version = 0
    if path.exists():
        txt = path.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"^\s*Version\s*=\s*(\d+)", txt, re.M | re.I)
        if m:
            version = int(m.group(1))
    user_part = (version >> 16) & 0xFFFF
    machine_part = version & 0xFFFF
    user_part = (user_part + 1) & 0xFFFF
    new_version = (user_part << 16) | machine_part
    path.write_text(
        "[General]\r\nVersion=" + str(new_version) + "\r\n"
        f"displayName={display_name}\r\n",
        encoding="utf-8",
    )
    return new_version


def update_ad(guid: str, version: int):
    """Garante gPCUserExtensionNames + versionNumber na GPO no AD."""
    import ldb
    from samba.samdb import SamDB
    from samba.credentials import Credentials
    from samba.auth import system_session
    from samba import param

    if not guid.startswith("{"):
        guid = "{" + guid.strip("{}").upper() + "}"

    lp = param.LoadParm()
    lp.load_default()
    creds = Credentials()
    creds.guess(lp)
    user = os.environ.get("SAMBA_ADMIN_USER", "")
    pwd  = os.environ.get("SAMBA_ADMIN_PASSWORD", "")
    if user and pwd:
        creds.set_username(user)
        creds.set_password(pwd)

    samdb = SamDB(url="ldap://localhost",
                  session_info=system_session(),
                  credentials=creds, lp=lp)
    domain_dn = str(samdb.domain_dn())
    dn = f"CN={guid},CN=Policies,CN=System,{domain_dn}"

    res = samdb.search(base=dn, scope=ldb.SCOPE_BASE,
                       attrs=["gPCUserExtensionNames"])
    cur_ext = ""
    if res and res[0].get("gPCUserExtensionNames"):
        cur_ext = str(res[0]["gPCUserExtensionNames"][0], "utf-8", "ignore")

    m = ldb.Message()
    m.dn = ldb.Dn(samdb, dn)
    if CSE_DRIVES not in cur_ext.upper():
        m["gPCUserExtensionNames"] = ldb.MessageElement(
            USER_EXT, ldb.FLAG_MOD_REPLACE, "gPCUserExtensionNames")
    m["versionNumber"] = ldb.MessageElement(
        str(version), ldb.FLAG_MOD_REPLACE, "versionNumber")
    m["flags"] = ldb.MessageElement("0", ldb.FLAG_MOD_REPLACE, "flags")
    samdb.modify(m)


# ----- comandos -----------------------------------------------------------
def cmd_write(gpo_dir: Path, guid: str, json_path: Path):
    spec = json.loads(json_path.read_text(encoding="utf-8"))

    user_dir = gpo_dir / "User"
    pref_dir = user_dir / "Preferences" / "Drives"
    pref_dir.mkdir(parents=True, exist_ok=True)

    xml_bytes = build_drives_xml(spec)
    xml_path = pref_dir / "Drives.xml"
    xml_path.write_bytes(xml_bytes)
    os.chmod(xml_path, 0o664)

    new_v = bump_gpt_ini(gpo_dir / "GPT.INI",
                         display_name="Atlas - Mapeamento de Drives")
    print(f"OK xml={xml_path} version={new_v} mappings={len(spec.get('mappings', []))}")

    try:
        update_ad(guid, new_v)
        print("OK ad-attrs atualizados")
    except Exception as e:
        print(f"AVISO: nao consegui atualizar atributos AD: {e}", file=sys.stderr)


def cmd_info(gpo_dir: Path):
    pref = gpo_dir / "User" / "Preferences" / "Drives" / "Drives.xml"
    print(f"xml_exists={pref.exists()}")
    if pref.exists():
        print(f"xml_size={pref.stat().st_size}")
    gpt = gpo_dir / "GPT.INI"
    if gpt.exists():
        print("gpt=" + gpt.read_text(errors="ignore").replace("\n", "|").replace("\r", ""))


def main():
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(2)
    action = sys.argv[1]
    gpo_dir = Path(sys.argv[2])
    if action == "write":
        if len(sys.argv) < 5:
            print(__doc__); sys.exit(2)
        cmd_write(gpo_dir, sys.argv[3], Path(sys.argv[4]))
    elif action == "info":
        cmd_info(gpo_dir)
    else:
        print(__doc__); sys.exit(2)


if __name__ == "__main__":
    main()
