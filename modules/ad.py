"""Wrappers para samba-tool. Retornam texto cru e/ou parseado."""
import subprocess
import re
import os
import json
import config


# ---- mapeamento manual OU -> Grupo (correlato) ----
OU_GROUP_MAP_PATH = "/etc/portal-atlas/ou_groups.json"

def ou_group_map():
    """Le o JSON {OU: Grupo}. Retorna {} se ausente/invalido."""
    try:
        with open(OU_GROUP_MAP_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
            if isinstance(d, dict):
                return {str(k): str(v) for k, v in d.items() if v}
    except FileNotFoundError:
        return {}
    except Exception:
        return {}
    return {}

def ou_group_set(ou, group):
    """Define (ou remove se group vazio) o grupo correlato de uma OU."""
    d = ou_group_map()
    ou = (ou or "").strip()
    group = (group or "").strip()
    if not ou:
        return False
    if group:
        d[ou] = group
    else:
        d.pop(ou, None)
    os.makedirs(os.path.dirname(OU_GROUP_MAP_PATH), exist_ok=True)
    tmp = OU_GROUP_MAP_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp, OU_GROUP_MAP_PATH)
    try:
        os.chmod(OU_GROUP_MAP_PATH, 0o644)
    except Exception:
        pass
    return True

def ou_group_for(ou):
    """Retorna o grupo configurado para a OU, ou None."""
    return ou_group_map().get(ou)


_ADMIN_CACHE = None
def _admin_creds():
    """Le /etc/portal-atlas/admin.conf e retorna (user, pwd) ou (None, None)."""
    global _ADMIN_CACHE
    if _ADMIN_CACHE is not None:
        return _ADMIN_CACHE
    user = pwd = None
    try:
        # cat via sudo (admin.conf e 600 root:root)
        r = subprocess.run(["sudo", "-n", "cat", "/etc/portal-atlas/admin.conf"],
                           capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                line = line.strip()
                if line.startswith("SAMBA_ADMIN_USER"):
                    user = line.split("=", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("SAMBA_ADMIN_PASSWORD"):
                    pwd = line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    _ADMIN_CACHE = (user, pwd)
    return _ADMIN_CACHE


def _with_creds(cmd):
    """Anexa -U user --password=pwd a um cmd samba-tool, se disponivel."""
    user, pwd = _admin_creds()
    if user and pwd:
        return cmd + [f"-U{user}", f"--password={pwd}"]
    return cmd


def run(cmd, check=False, input_=None):
    r = subprocess.run(cmd, capture_output=True, text=True, input=input_, timeout=30)
    if check and r.returncode != 0:
        raise RuntimeError(f"cmd failed: {' '.join(cmd)}\n{r.stderr}")
    # filtra warning de senha na CLI
    if r.stderr and "WARNING: Using password on command line" in r.stderr:
        r.stderr = "\n".join(l for l in r.stderr.splitlines()
                             if "WARNING: Using password" not in l)
    return r


# --------- Users ---------
def list_users():
    r = run(config.SAMBA_TOOL + ["user", "list"])
    if r.returncode != 0:
        return []
    return sorted([u.strip() for u in r.stdout.splitlines() if u.strip()])


def user_show(login):
    r = run(config.SAMBA_TOOL + ["user", "show", login])
    return r.stdout if r.returncode == 0 else ""


def user_create(login, password, fullname, ou="TI", script="logon-vpn.bat"):
    parts = fullname.strip().split(None, 1)
    given = parts[0]
    sur = parts[1] if len(parts) > 1 else "-"
    cmd = config.SAMBA_TOOL + [
        "user", "create", login, password,
        f"--given-name={given}", f"--surname={sur}",
        f"--userou=OU={ou}",
        "--must-change-at-next-login",
    ]
    if script:
        cmd.append(f"--script-path={script}")
    r = run(cmd)
    # Correlato OU<->Grupo (manual): so adiciona se ha mapeamento configurado
    extra = ""
    if r.returncode == 0:
        grp = ou_group_for(ou)
        if grp:
            ge = ensure_group(grp)
            extra += ge
            ga = group_add_member(grp, login)
            if ga.returncode == 0:
                extra += f"\n[OK] usuario {login} adicionado ao grupo {grp}"
            else:
                tail = (ga.stderr or ga.stdout).strip().splitlines()
                tail = tail[-1] if tail else ""
                if "already" not in tail.lower():
                    extra += f"\n[!] nao consegui adicionar {login} ao grupo {grp}: {tail}"
    if extra:
        r.stdout = (r.stdout or "") + extra
    return r


def user_delete(login):
    return run(config.SAMBA_TOOL + ["user", "delete", login])


def user_setpassword(login, password):
    return run(config.SAMBA_TOOL + ["user", "setpassword", login, f"--newpassword={password}"])


def user_enable(login):
    return run(config.SAMBA_TOOL + ["user", "enable", login])


def user_disable(login):
    return run(config.SAMBA_TOOL + ["user", "disable", login])


# --------- Groups ---------
def list_groups():
    r = run(config.SAMBA_TOOL + ["group", "list"])
    return sorted([g.strip() for g in r.stdout.splitlines() if g.strip()])


def group_create(name):
    return run(config.SAMBA_TOOL + ["group", "add", name])


def ensure_group(name):
    """Cria o grupo se nao existir. Retorna string com mensagem (vazia se ja existia)."""
    if name in list_groups():
        return ""
    r = group_create(name)
    if r.returncode == 0:
        return f"\n[OK] grupo {name} criado"
    return f"\n[!] falha ao criar grupo {name}: {(r.stderr or r.stdout).strip()}"


def group_delete(name):
    return run(config.SAMBA_TOOL + ["group", "delete", name])


def group_members(name):
    r = run(config.SAMBA_TOOL + ["group", "listmembers", name])
    return sorted([m.strip() for m in r.stdout.splitlines() if m.strip()])


def group_add_member(group, user):
    return run(config.SAMBA_TOOL + ["group", "addmembers", group, user])


def group_remove_member(group, user):
    return run(config.SAMBA_TOOL + ["group", "removemembers", group, user])


# --------- OUs ---------
def list_ous():
    r = run(config.SAMBA_TOOL + ["ou", "list"])
    return sorted([o.strip() for o in r.stdout.splitlines() if o.strip()])


def ou_create(name):
    # OU criada "vazia": associacao com grupo e manual em /ous (ou_group_set).
    return run(config.SAMBA_TOOL + ["ou", "create", f"OU={name}"])


def ou_users(ou_name):
    """Lista logins de usuarios cuja DN contem OU=<ou_name>.
    Usa ldbsearch via sudo (precisa estar no sudoers)."""
    out = []
    rr = run([
        "sudo", "-n", "ldbsearch",
        "-H", "/var/lib/samba/private/sam.ldb",
        "(&(objectClass=user)(!(objectClass=computer)))",
        "sAMAccountName", "distinguishedName",
    ])
    cur_dn = ""
    cur_sam = ""
    needle = f"OU={ou_name},".lower()
    for line in rr.stdout.splitlines():
        if line.startswith("dn:"):
            cur_dn = line[3:].strip()
            cur_sam = ""
        elif line.lower().startswith("samaccountname:"):
            cur_sam = line.split(":", 1)[1].strip()
        elif not line.strip():
            if cur_sam and needle in cur_dn.lower():
                out.append(cur_sam)
            cur_dn = cur_sam = ""
    if cur_sam and needle in cur_dn.lower():
        out.append(cur_sam)
    return sorted(set(out))


def sync_ou_groups():
    """Para cada OU **com mapeamento manual** OU->Grupo: garante o grupo e
    adiciona todos os usuarios da OU a esse grupo. OUs sem mapeamento sao
    puladas. Retorna lista de tuples (msg_level, texto)."""
    msgs = []
    mp = ou_group_map()
    if not mp:
        msgs.append(("err", "nenhuma OU possui grupo correlato configurado"))
        return msgs
    for o in list_ous():
        name = o.replace("OU=", "").strip()
        if not name:
            continue
        grp = mp.get(name)
        if not grp:
            msgs.append(("ok", f"OU {name}: sem grupo correlato (pulado)"))
            continue
        m = ensure_group(grp)
        if m:
            msgs.append(("ok", m.strip()))
        users = ou_users(name)
        existing = set(group_members(grp))
        added = 0
        for u in users:
            if u in existing:
                continue
            r = group_add_member(grp, u)
            if r.returncode == 0:
                added += 1
            else:
                tail = (r.stderr or r.stdout).strip().splitlines()
                tail = tail[-1] if tail else "falhou"
                msgs.append(("err", f"{u} -> {grp}: {tail}"))
        msgs.append(("ok", f"OU {name} -> grupo {grp}: {len(users)} usuarios, +{added} adicionados"))
    return msgs


# --------- GPO ---------
def list_gpos():
    r = run(config.SAMBA_TOOL + ["gpo", "listall"])
    gpos = []
    block = {}
    for line in r.stdout.splitlines():
        line = line.strip()
        if not line:
            if block:
                gpos.append(block)
                block = {}
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            block[k.strip()] = v.strip()
    if block:
        gpos.append(block)
    return gpos


def gpo_show(guid):
    r = run(config.SAMBA_TOOL + ["gpo", "show", guid])
    info = {}
    for line in r.stdout.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            info[k.strip()] = v.strip()
    return info


def gpo_create(name):
    return run(_with_creds(config.SAMBA_TOOL + ["gpo", "create", name]))


def gpo_delete(guid):
    return run(_with_creds(config.SAMBA_TOOL + ["gpo", "del", guid]))


def gpo_list_containers(gpo_guid):
    """Retorna lista de DNs de OUs/containers onde a GPO esta linkada,
    com flags (enforce/disabled) quando disponivel."""
    r = run(config.SAMBA_TOOL + ["gpo", "listcontainers", gpo_guid])
    out = []
    for line in r.stdout.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("gpo found") or line.lower().startswith("container"):
            continue
        # linha tipica: "    DN: OU=Financeiro,DC=texasco,DC=local"
        if line.startswith("DN:"):
            line = line[3:].strip()
        if line.startswith("CN=") or line.startswith("OU=") or line.startswith("DC="):
            out.append({"dn": line, "options": ""})
    return out


def gpo_get_link_options(container_dn):
    """Retorna dict guid -> {enforce, disabled} via gpo getlink."""
    r = run(config.SAMBA_TOOL + ["gpo", "getlink", container_dn])
    out = {}
    cur = None
    for line in r.stdout.splitlines():
        s = line.strip()
        m = re.search(r"(\{[A-Fa-f0-9-]+\})", s)
        if m:
            cur = m.group(1).upper()
            out[cur] = {"enforce": False, "disabled": False}
        if cur:
            sl = s.lower()
            if "enforce" in sl and "true" in sl:
                out[cur]["enforce"] = True
            if "enable" in sl and "false" in sl:
                out[cur]["disabled"] = True
            if "disabled" in sl and "true" in sl:
                out[cur]["disabled"] = True
    return out


def gpo_link(container_dn, gpo_guid, enforce=False, disable=False):
    cmd = config.SAMBA_TOOL + ["gpo", "setlink", container_dn, gpo_guid]
    if enforce: cmd.append("--enforce")
    if disable: cmd.append("--disable")
    return run(_with_creds(cmd))


def gpo_unlink(container_dn, gpo_guid):
    return run(_with_creds(config.SAMBA_TOOL + ["gpo", "dellink", container_dn, gpo_guid]))


def gpo_get_inheritance(container_dn):
    r = run(config.SAMBA_TOOL + ["gpo", "getinheritance", container_dn])
    return r.stdout.strip()


def gpo_set_inheritance(container_dn, block):
    state = "block" if block else "inherit"
    return run(_with_creds(config.SAMBA_TOOL + ["gpo", "setinheritance", container_dn, state]))


# Containers disponiveis para link: dominio raiz + OUs
def gpo_link_targets():
    base_dn = ",".join("DC=" + p for p in config.LDAP_DOMAIN.split("."))
    targets = [{"dn": base_dn, "label": f"(raiz do dominio) {base_dn}"}]
    for o in list_ous():
        name = o.replace("OU=", "").strip()
        if not name:
            continue
        targets.append({
            "dn": f"OU={name},{base_dn}",
            "label": f"OU={name}",
        })
    return targets


def gpo_set_state(guid, user_enabled=True, computer_enabled=True):
    """Mexe no atributo flags da GPO. 0=ambos on, 1=user off, 2=computer off, 3=ambos off."""
    flags = 0
    if not user_enabled:     flags |= 1
    if not computer_enabled: flags |= 2
    base_dn = ",".join("DC=" + p for p in config.LDAP_DOMAIN.split("."))
    dn = f"CN={guid},CN=Policies,CN=System,{base_dn}"
    ldif = f"dn: {dn}\nchangetype: modify\nreplace: flags\nflags: {flags}\n"
    r = run(["sudo", "-n", "ldbmodify", "-H",
             "/var/lib/samba/private/sam.ldb"], input_=ldif)
    return r


def gpo_get_flags(guid):
    base_dn = ",".join("DC=" + p for p in config.LDAP_DOMAIN.split("."))
    dn = f"CN={guid},CN=Policies,CN=System,{base_dn}"
    r = run(["sudo", "-n", "ldbsearch", "-H",
             "/var/lib/samba/private/sam.ldb",
             "-b", dn, "-s", "base", "(objectClass=*)", "flags"])
    for line in r.stdout.splitlines():
        if line.lower().startswith("flags:"):
            try:
                return int(line.split(":", 1)[1].strip())
            except Exception:
                return 0
    return 0


# --------- Domain info ---------
def domain_info():
    r = run(config.SAMBA_TOOL + ["domain", "info", "127.0.0.1"])
    info = {}
    for line in r.stdout.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            info[k.strip()] = v.strip()
    return info
