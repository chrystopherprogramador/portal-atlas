"""Sysinfo: CPU, RAM, disco, servicos - para dashboard."""
import subprocess
import os
import re
from pathlib import Path


def svc_status(name):
    r = subprocess.run(["systemctl", "is-active", name], capture_output=True, text=True)
    return r.stdout.strip() or "unknown"


def svc_matrix():
    """Lista de servicos monitorados."""
    names = [
        ("Samba AD DC",    "samba-ad-dc"),
        ("WireGuard VPN",  "wg-quick@wg0"),
        ("Nginx",          "nginx"),
        ("Portal ATLAS",   "portal-atlas"),
        ("PHP-FPM 8.0",    "php8.0-fpm"),
        ("PostgreSQL 16",  "postgresql@16-main"),
        ("Cron",           "cron"),
    ]
    return [{"label": l, "unit": u, "status": svc_status(u)} for l, u in names]


def uptime():
    try:
        with open("/proc/uptime") as f:
            s = float(f.read().split()[0])
        d, r = divmod(int(s), 86400)
        h, r = divmod(r, 3600)
        m, _ = divmod(r, 60)
        return f"{d}d {h}h {m}m"
    except Exception:
        return "?"


def loadavg():
    try:
        with open("/proc/loadavg") as f:
            parts = f.read().split()
        return {"1m": parts[0], "5m": parts[1], "15m": parts[2]}
    except Exception:
        return {"1m": "?", "5m": "?", "15m": "?"}


def cpu_count():
    try:
        return os.cpu_count() or 1
    except Exception:
        return 1


def meminfo():
    """Retorna uso de memoria em MB + percentual."""
    try:
        info = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, _, v = line.partition(":")
                m = re.match(r"\s*(\d+)", v)
                if m:
                    info[k.strip()] = int(m.group(1))  # kB
        total = info.get("MemTotal", 0) / 1024
        avail = info.get("MemAvailable", 0) / 1024
        used = total - avail
        pct = int(used / total * 100) if total else 0
        return {
            "total_mb": int(total),
            "used_mb":  int(used),
            "avail_mb": int(avail),
            "pct":      pct,
        }
    except Exception:
        return {"total_mb": 0, "used_mb": 0, "avail_mb": 0, "pct": 0}


def disk_usage(path="/"):
    try:
        r = subprocess.run(["df", "-h", path], capture_output=True, text=True)
        lines = r.stdout.strip().splitlines()
        if len(lines) >= 2:
            parts = lines[1].split()
            return {
                "fs": parts[0],
                "size": parts[1],
                "used": parts[2],
                "avail": parts[3],
                "pct": parts[4],
                "mount": parts[5] if len(parts) > 5 else path,
            }
    except Exception:
        pass
    return {"fs": "?", "size": "?", "used": "?", "avail": "?", "pct": "?", "mount": path}


def shares_sizes():
    """Tamanho das pastas em /srv/samba/shares - rapido (cache timestamp)."""
    root = Path("/srv/samba/shares")
    out = []
    if not root.exists():
        return out
    for d in sorted(root.iterdir()):
        if d.is_dir():
            try:
                r = subprocess.run(["du", "-sh", str(d)], capture_output=True, text=True, timeout=5)
                size = r.stdout.split()[0] if r.stdout else "?"
            except Exception:
                size = "?"
            out.append({"name": d.name, "size": size})
    return out
