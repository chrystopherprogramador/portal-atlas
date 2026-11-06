"""Wrapper para gerenciar a GPO de mapeamento de drives."""
import json
import os
import subprocess
import tempfile
from typing import Dict, List

SCRIPT = ["sudo", "-n", "/usr/local/sbin/gerenciar-drives.sh"]


def _run(args, timeout=120):
    return subprocess.run(SCRIPT + args, capture_output=True, text=True, timeout=timeout)


def info() -> Dict:
    """Retorna estado + config (mappings/ti_group)."""
    r = _run(["info"])
    out: Dict = {"raw": r.stdout, "config": {"mappings": [], "ti_group": "", "domain": ""}}
    if r.returncode != 0:
        return out
    in_cfg = False
    cfg_lines: List[str] = []
    for line in r.stdout.splitlines():
        if line.strip() == "---CONFIG---":
            in_cfg = True
            continue
        if in_cfg:
            cfg_lines.append(line)
        else:
            if "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    if cfg_lines:
        try:
            out["config"] = json.loads("\n".join(cfg_lines))
        except Exception:
            pass
    out["config"].setdefault("mappings", [])
    out["config"].setdefault("ti_group", "")
    out["config"].setdefault("domain", "")
    return out


def init():
    return _run(["init"], timeout=180)


def disable():
    return _run(["disable"])


def list_shares() -> List[str]:
    r = _run(["list-shares"])
    if r.returncode != 0:
        return []
    return [l.strip() for l in r.stdout.splitlines() if l.strip()]


def save_config(ti_group: str, domain: str, mappings: List[Dict]):
    """Persiste config + reaplica."""
    payload = {
        "ti_group": (ti_group or "").strip(),
        "domain":   (domain or "TEXASCO").strip().upper(),
        "mappings": [],
    }
    for m in mappings:
        letter = (m.get("letter") or "").strip().upper().rstrip(":")
        unc    = (m.get("unc") or "").strip()
        if not letter or not unc:
            continue
        payload["mappings"].append({
            "letter": letter,
            "unc": unc,
            "label": (m.get("label") or letter).strip(),
            "groups": [g.strip() for g in m.get("groups", []) if g and g.strip()],
            "action": (m.get("action") or "U").strip().upper(),
        })

    fd, tmp = tempfile.mkstemp(prefix="drives_", suffix=".json", dir="/var/tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        os.chmod(tmp, 0o644)
        return _run(["set-config", tmp], timeout=180)
    finally:
        try: os.unlink(tmp)
        except OSError: pass
