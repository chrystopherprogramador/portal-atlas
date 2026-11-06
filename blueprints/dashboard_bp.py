from flask import Blueprint, render_template, jsonify
from modules.auth import login_required
from modules import ad, vpn, audit, sysinfo, backup as bk, monitoring as mon

dashboard_bp = Blueprint("dashboard", __name__)


def _collect():
    services = sysinfo.svc_matrix()
    mem      = sysinfo.meminfo()
    load     = sysinfo.loadavg()
    ncpu     = sysinfo.cpu_count()
    try:
        load_pct = min(100, int(float(load["1m"]) / ncpu * 100))
    except Exception:
        load_pct = 0
    try:
        bk_st = bk.status()
    except Exception:
        bk_st = {"status_label": "?", "status_color": "grey", "age_label": "?", "running": False, "last": {}}
    try:
        mon_st = mon.summary()
    except Exception as e:
        mon_st = {"active": 0, "critical": 0, "warning": 0,
                  "status_color": "grey", "status_label": "indisponivel",
                  "prometheus_up": 0, "alertmanager_up": 0, "top": []}
    return {
        "services": services,
        "mem":      mem,
        "load":     load,
        "load_pct": load_pct,
        "ncpu":     ncpu,
        "uptime":   sysinfo.uptime(),
        "disk":     sysinfo.disk_usage("/"),
        "disk_srv": sysinfo.disk_usage("/srv"),
        "shares":   sysinfo.shares_sizes(),
        "backup":   bk_st,
        "monitoring": mon_st,
    }


def _audit_rows(n=20):
    out = []
    for a in audit.tail(n):
        try:
            keys = a.keys()
        except Exception:
            keys = []
        def g(k, default=""):
            try:
                return a[k] if k in keys else default
            except Exception:
                return default
        out.append({
            "ts":     g("ts"),
            "actor":  g("user") or "",
            "action": g("action") or "",
            "target": g("target") or "",
            "ok":     bool(g("ok", 1)),
        })
    return out


@dashboard_bp.route("/")
@login_required
def index():
    data   = _collect()
    domain = ad.domain_info()
    peers  = vpn.list_peers_from_conf()
    users  = ad.list_users()
    return render_template(
        "dashboard.html",
        domain      = domain,
        peers       = peers,
        users_count = len(users),
        audit_tail  = audit.tail(20),
        **data
    )


@dashboard_bp.route("/api/stats")
@login_required
def api_stats():
    data = _collect()
    data["audit_tail"] = _audit_rows(20)
    try:
        data["peers_count"] = len(vpn.list_peers_from_conf())
    except Exception:
        data["peers_count"] = 0
    try:
        data["users_count"] = len(ad.list_users())
    except Exception:
        data["users_count"] = 0
    return jsonify(data)
