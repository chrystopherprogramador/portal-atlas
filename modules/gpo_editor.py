"""Wrapper Python para gpo-policy.py (root via sudo)."""
import json
import subprocess
from typing import List, Dict
from modules.gpo_policy import CATALOG, find_in_catalog, TYPE_NAMES

SCRIPT = ["sudo", "-n", "/usr/local/sbin/gpo-policy.py"]


def _gpo_dir(guid: str) -> str:
    """Retorna o caminho no SYSVOL para esse GUID."""
    import config
    domain = config.LDAP_DOMAIN
    return f"/var/lib/samba/sysvol/{domain}/Policies/{guid}"


def list_entries(guid: str) -> Dict[str, List[Dict]]:
    r = subprocess.run(SCRIPT + ["list", _gpo_dir(guid)],
                       capture_output=True, text=True, timeout=15)
    if r.returncode != 0:
        return {"machine": [], "user": []}
    try:
        return json.loads(r.stdout)
    except Exception:
        return {"machine": [], "user": []}


def set_value(guid: str, scope: str, key: str, name: str, vtype: str, data: str):
    return subprocess.run(SCRIPT + ["set", _gpo_dir(guid), guid, scope,
                                    key, name, vtype, str(data)],
                          capture_output=True, text=True, timeout=30)


def unset_value(guid: str, scope: str, key: str, name: str):
    return subprocess.run(SCRIPT + ["unset", _gpo_dir(guid), guid, scope, key, name],
                          capture_output=True, text=True, timeout=30)


def annotate_with_catalog(entries_by_scope: Dict[str, List[Dict]]) -> Dict[str, List[Dict]]:
    """Adiciona campo 'catalog' (id e title) quando achar match."""
    out = {"machine": [], "user": []}
    for scope, lst in entries_by_scope.items():
        for e in lst:
            cat = find_in_catalog(scope, e["key"], e["name"])
            new = dict(e)
            new["type_name"] = TYPE_NAMES.get(e["type"], str(e["type"]))
            new["catalog_id"] = cat["id"] if cat else None
            new["catalog_title"] = cat["title"] if cat else None
            out[scope].append(new)
    return out
