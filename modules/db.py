"""PostgreSQL helpers via sudo + psql com peer auth do usuario postgres."""
import subprocess
import json


def _psql(sql, db="postgres", user="postgres", tuples_only=True):
    """Executa SQL como usuario postgres (peer auth, sem senha)."""
    cmd = ["sudo", "-n", "-u", user, "psql", "-d", db, "-X", "-A", "-F", "\x1f"]
    if tuples_only:
        cmd.append("-t")
    cmd += ["-c", sql]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    return r


def list_databases():
    sql = (
        "SELECT d.datname, "
        "       pg_get_userbyid(d.datdba) AS owner, "
        "       pg_encoding_to_char(d.encoding) AS enc, "
        "       pg_size_pretty(pg_database_size(d.datname)) AS size "
        "FROM pg_database d "
        "WHERE d.datistemplate = false "
        "ORDER BY d.datname"
    )
    r = _psql(sql)
    out = []
    if r.returncode != 0:
        return out
    for line in r.stdout.strip().splitlines():
        parts = line.split("\x1f")
        if len(parts) >= 4:
            out.append({
                "name": parts[0].strip(),
                "owner": parts[1].strip(),
                "encoding": parts[2].strip(),
                "size": parts[3].strip(),
            })
    return out


def list_roles():
    sql = (
        "SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolcanlogin "
        "FROM pg_roles WHERE rolname NOT LIKE 'pg\\_%' ESCAPE '\\' "
        "ORDER BY rolname"
    )
    r = _psql(sql)
    out = []
    if r.returncode != 0:
        return out
    for line in r.stdout.strip().splitlines():
        parts = line.split("\x1f")
        if len(parts) >= 5:
            out.append({
                "name": parts[0].strip(),
                "super": parts[1].strip() == "t",
                "createdb": parts[2].strip() == "t",
                "createrole": parts[3].strip() == "t",
                "canlogin": parts[4].strip() == "t",
            })
    return out


def server_version():
    r = _psql("SHOW server_version")
    return r.stdout.strip() if r.returncode == 0 else "?"


def total_size():
    sql = "SELECT pg_size_pretty(SUM(pg_database_size(d.datname))) FROM pg_database d"
    r = _psql(sql)
    return r.stdout.strip() if r.returncode == 0 else "?"


# --- Validacao simples para evitar SQL injection nos nomes ---
import re
_IDENT_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$", re.I)

def _valid_ident(s):
    return bool(_IDENT_RE.match(s or ""))


def db_create(name, owner="dbadmin"):
    if not _valid_ident(name):
        return 1, "Nome invalido (use a-z0-9_)"
    if not _valid_ident(owner):
        return 1, "Owner invalido"
    # Usa createdb wrapper (mais seguro que CREATE DATABASE interpolado)
    cmd = ["sudo", "-n", "-u", "postgres", "createdb", "-O", owner, name]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    return r.returncode, (r.stderr.strip() or r.stdout.strip() or "ok")


def db_drop(name):
    if not _valid_ident(name):
        return 1, "Nome invalido"
    if name in ("postgres", "template0", "template1"):
        return 1, "Banco reservado"
    cmd = ["sudo", "-n", "-u", "postgres", "dropdb", "--if-exists", name]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    return r.returncode, (r.stderr.strip() or r.stdout.strip() or "ok")


def role_create(name, password, options=("LOGIN",)):
    if not _valid_ident(name):
        return 1, "Nome invalido"
    if not password or len(password) < 6:
        return 1, "Senha deve ter >= 6 caracteres"
    opts = " ".join(o for o in options if o in {"LOGIN","CREATEDB","CREATEROLE","SUPERUSER","INHERIT"})
    safe_pass = password.replace("'", "''")
    sql = f"CREATE ROLE {name} WITH {opts} PASSWORD '{safe_pass}'"
    r = _psql(sql, tuples_only=False)
    return r.returncode, (r.stderr.strip() or r.stdout.strip())


def role_set_password(name, password):
    if not _valid_ident(name):
        return 1, "Nome invalido"
    if not password or len(password) < 6:
        return 1, "Senha muito curta"
    safe_pass = password.replace("'", "''")
    sql = f"ALTER ROLE {name} WITH PASSWORD '{safe_pass}'"
    r = _psql(sql, tuples_only=False)
    return r.returncode, (r.stderr.strip() or r.stdout.strip())


def role_drop(name):
    if not _valid_ident(name):
        return 1, "Nome invalido"
    if name in ("postgres", "dbadmin"):
        return 1, "Role protegida"
    sql = f"DROP ROLE IF EXISTS {name}"
    r = _psql(sql, tuples_only=False)
    return r.returncode, (r.stderr.strip() or r.stdout.strip())


def db_owner_change(db, new_owner):
    if not _valid_ident(db) or not _valid_ident(new_owner):
        return 1, "Identificador invalido"
    sql = f'ALTER DATABASE {db} OWNER TO {new_owner}'
    r = _psql(sql, tuples_only=False)
    return r.returncode, (r.stderr.strip() or r.stdout.strip())
