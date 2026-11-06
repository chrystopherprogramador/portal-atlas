"""Monitoring module - consulta Prometheus/Alertmanager e gerencia alertas recebidos via webhook."""
import json
import os
import time
import fcntl
import urllib.request
import urllib.parse
from datetime import datetime, timezone

PROM_URL = "http://127.0.0.1:9090/prometheus"
ALERTMANAGER_URL = "http://127.0.0.1:9093/alertmanager"
ALERTS_FILE = "/var/lib/portal-atlas/alerts-state.json"


def _http_get(url, timeout=5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"_error": str(e)}


def prom_query(expr):
    url = f"{PROM_URL}/api/v1/query?query=" + urllib.parse.quote(expr)
    d = _http_get(url)
    if d.get("status") != "success":
        return None
    try:
        r = d["data"]["result"]
        if not r:
            return 0
        return float(r[0]["value"][1])
    except Exception:
        return None


def prom_targets():
    d = _http_get(f"{PROM_URL}/api/v1/targets?state=active")
    if d.get("status") != "success":
        return []
    out = []
    for t in d.get("data", {}).get("activeTargets", []):
        out.append({
            "job":    t.get("labels", {}).get("job"),
            "instance": t.get("labels", {}).get("instance") or t.get("scrapeUrl"),
            "health": t.get("health"),
            "lastError": t.get("lastError") or "",
            "lastScrape": t.get("lastScrape"),
        })
    return out


def prom_alerts():
    """Retorna alertas firing/pending direto do Prometheus."""
    d = _http_get(f"{PROM_URL}/api/v1/alerts")
    if d.get("status") != "success":
        return []
    return d.get("data", {}).get("alerts", [])


def am_alerts():
    """Alertas ativos no Alertmanager (com silenciamentos ja aplicados)."""
    d = _http_get(f"{ALERTMANAGER_URL}/api/v2/alerts?active=true&silenced=false&inhibited=false")
    if isinstance(d, dict) and "_error" in d:
        return []
    return d if isinstance(d, list) else []


# ---------------- Webhook state ----------------

def _load_state():
    try:
        with open(ALERTS_FILE) as f:
            return json.load(f)
    except Exception:
        return {"active": {}, "history": []}


def _save_state(st):
    os.makedirs(os.path.dirname(ALERTS_FILE), exist_ok=True)
    tmp = ALERTS_FILE + ".tmp"
    with open(tmp, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        json.dump(st, f, indent=2, default=str)
    os.replace(tmp, ALERTS_FILE)


def ingest_webhook(payload):
    """Recebe payload Alertmanager v4 e atualiza estado."""
    st = _load_state()
    now = datetime.now(timezone.utc).isoformat()
    for a in payload.get("alerts", []):
        labels = a.get("labels", {})
        fp = a.get("fingerprint") or labels.get("alertname", "?") + "|" + labels.get("instance", "")
        status = a.get("status", "firing")
        rec = {
            "fingerprint": fp,
            "status":      status,
            "alertname":   labels.get("alertname"),
            "severity":    labels.get("severity", "info"),
            "component":   labels.get("component", ""),
            "instance":    labels.get("instance", ""),
            "summary":     (a.get("annotations") or {}).get("summary", ""),
            "description": (a.get("annotations") or {}).get("description", ""),
            "startsAt":    a.get("startsAt"),
            "endsAt":      a.get("endsAt"),
            "received":    now,
        }
        if status == "firing":
            st["active"][fp] = rec
        else:
            st["active"].pop(fp, None)
        # Historico (ultimos 200)
        st.setdefault("history", []).append(rec)
        st["history"] = st["history"][-200:]
    _save_state(st)
    return {"active": len(st["active"])}


def active_alerts():
    st = _load_state()
    alerts = list(st.get("active", {}).values())
    # ordena: critical primeiro, depois por startsAt
    sev_order = {"critical": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda a: (sev_order.get(a.get("severity"), 9), a.get("startsAt") or ""))
    return alerts


def history(n=50):
    st = _load_state()
    return list(reversed(st.get("history", [])[-n:]))


def summary():
    """Resumo para dashboard/API."""
    active = active_alerts()
    crit = sum(1 for a in active if a.get("severity") == "critical")
    warn = sum(1 for a in active if a.get("severity") == "warning")
    if crit > 0:
        color, label = "red",   f"{crit} critico(s)"
    elif warn > 0:
        color, label = "yel",   f"{warn} aviso(s)"
    else:
        color, label = "green", "tudo normal"
    # Status Prometheus/Alertmanager
    pr_up = 1 if _http_get(f"{PROM_URL}/-/ready", timeout=2).get("_error") is None or True else 0
    try:
        with urllib.request.urlopen(f"{PROM_URL}/-/ready", timeout=2) as r:
            pr_up = 1 if r.status == 200 else 0
    except Exception:
        pr_up = 0
    try:
        with urllib.request.urlopen(f"{ALERTMANAGER_URL}/-/ready", timeout=2) as r:
            am_up = 1 if r.status == 200 else 0
    except Exception:
        am_up = 0
    return {
        "active":      len(active),
        "critical":    crit,
        "warning":     warn,
        "status_color": color,
        "status_label": label,
        "prometheus_up":   pr_up,
        "alertmanager_up": am_up,
        "top": active[:5],
    }
