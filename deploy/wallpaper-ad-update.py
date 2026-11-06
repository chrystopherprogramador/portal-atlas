#!/usr/bin/env python3
"""
wallpaper-ad-update.py - Atualiza atributos AD da GPO de papel de parede
para que o engine de Group Policy aplique-a nos clientes.

Faz:
  - gPCUserExtensionNames = [{Registry-CSE}{GP-Editor-tool}]
  - versionNumber          = <valor inteiro>
  - flags                  = 0   (Enabled, todos lados)

Uso:
  wallpaper-ad-update.py <gpo_guid_com_chaves> <version>
"""
import sys

# CSE / Tool GUIDs oficiais
REG_CSE   = "{35378EAC-683F-11D2-A89A-00C04FBBCFA2}"   # Registry Settings CSE
GP_TOOL   = "{0F6B957D-509E-11D1-A7CC-0000F87571E3}"   # Group Policy Object Editor
USER_EXT  = f"[{REG_CSE}{GP_TOOL}]"


def main():
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(2)

    guid_in = sys.argv[1].strip()
    version = int(sys.argv[2])
    if not guid_in.startswith("{"):
        guid_in = "{" + guid_in.strip("{}").upper() + "}"

    import os
    import ldb
    from samba.samdb import SamDB
    from samba.credentials import Credentials
    from samba.auth import system_session
    from samba import param

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
                  credentials=creds,
                  lp=lp)

    domain_dn = str(samdb.domain_dn())
    dn = f"CN={guid_in},CN=Policies,CN=System,{domain_dn}"

    res = samdb.search(base=dn, scope=ldb.SCOPE_BASE,
                       attrs=["gPCUserExtensionNames",
                              "versionNumber", "flags"])
    if not res:
        print(f"ERRO: GPO nao encontrada em {dn}", file=sys.stderr)
        sys.exit(1)

    cur_ext = ""
    if res[0].get("gPCUserExtensionNames"):
        cur_ext = str(res[0]["gPCUserExtensionNames"][0], "utf-8", "ignore")

    m = ldb.Message()
    m.dn = ldb.Dn(samdb, dn)

    if REG_CSE not in cur_ext.upper():
        m["gPCUserExtensionNames"] = ldb.MessageElement(
            USER_EXT, ldb.FLAG_MOD_REPLACE, "gPCUserExtensionNames")

    m["versionNumber"] = ldb.MessageElement(
        str(version), ldb.FLAG_MOD_REPLACE, "versionNumber")
    m["flags"] = ldb.MessageElement(
        "0", ldb.FLAG_MOD_REPLACE, "flags")

    samdb.modify(m)
    print(f"OK gPCUserExtensionNames={'set' if REG_CSE not in cur_ext.upper() else 'kept'} "
          f"versionNumber={version}")


if __name__ == "__main__":
    main()
