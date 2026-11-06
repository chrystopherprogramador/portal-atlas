"""Wrapper de gerencia do servidor FTP (vsftpd) via gerenciar-ftp.sh."""
import subprocess
import re
from typing import List, Dict


SCRIPT = ["sudo", "-n", "/usr/local/sbin/gerenciar-ftp.sh"]
USER_RE = re.compile(r"^[a-z_][a-z0-9_-]{1,31}$")


def _run(args, timeout=30):
    return subprocess.run(SCRIPT + args, capture_output=True, text=True, timeout=timeout)


def valid_username(u: str) -> bool:
    return bool(USER_RE.match(u or ""))


def _human_size(kb: int) -> str:
    if kb < 1024:
        return f"{kb} KB"
    mb = kb / 1024
    if mb < 1024:
        return f"{mb:.1f} MB"
    return f"{mb/1024:.2f} GB"


def list_users() -> List[Dict]:
    r = _run(["list"])
    out: List[Dict] = []
    if r.returncode != 0:
        return out
    for line in r.stdout.strip().splitlines():
        parts = line.split("|")
        if len(parts) < 5:
            continue
        user, home, locked, size_kb, last = parts[:5]
        try:
            size_kb_i = int(size_kb)
        except ValueError:
            size_kb_i = 0
        out.append({
            "user": user,
            "home": home,
            "locked": locked == "1",
            "size_kb": size_kb_i,
            "size_h": _human_size(size_kb_i),
            "last_login": last or "-",
        })
    return sorted(out, key=lambda x: x["user"].lower())


def status() -> str:
    r = _run(["status"])
    return (r.stdout or "").strip() or "unknown"


def sessions() -> List[Dict]:
    r = _run(["sessions"])
    out = []
    if r.returncode != 0:
        return out
    for line in r.stdout.strip().splitlines():
        parts = line.split("|")
        if len(parts) < 2:
            continue
        out.append({"peer": parts[0], "local": parts[1]})
    return out


def add_user(user: str, password: str):
    return _run(["add", user, password])


def del_user(user: str):
    return _run(["del", user])


def change_password(user: str, password: str):
    return _run(["passwd", user, password])


def lock(user: str):
    return _run(["lock", user])


def unlock(user: str):
    return _run(["unlock", user])


def restart():
    return _run(["restart"])
