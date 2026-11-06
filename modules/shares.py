"""Wrapper para gerenciar shares Samba (via script com sudo)."""
import subprocess
from typing import List, Dict


SCRIPT = ["sudo", "-n", "/usr/local/sbin/gerenciar-share.sh"]


def _run(args, timeout=30):
    return subprocess.run(SCRIPT + args, capture_output=True, text=True, timeout=timeout)


def list_shares() -> List[Dict]:
    r = _run(["list"])
    if r.returncode != 0:
        return []
    out = []
    for line in r.stdout.strip().splitlines():
        parts = line.split("|")
        if len(parts) < 5:
            continue
        name, path, vu, managed, comment = parts[:5]
        out.append({
            "name": name,
            "path": path,
            "valid_users": vu,
            "managed": managed == "1",
            "comment": comment,
            "system": name.lower() in ("sysvol", "netlogon", "global", "ipc$", "print$"),
        })
    return sorted(out, key=lambda x: (x["system"], x["name"].lower()))


def add_share(name: str, group: str, description: str = ""):
    return _run(["add", name, group, description])


def del_share(name: str):
    return _run(["del", name])


def set_group(name: str, group: str):
    return _run(["setgroup", name, group])
