"""/monitoring blueprint - Grafana embed + alertas + targets."""
from flask import Blueprint, render_template, request, jsonify, abort, session, make_response
from modules.auth import login_required
from modules import monitoring as mon
from modules.audit import log

monitoring_bp = Blueprint("monitoring", __name__, template_folder="../templates")


@monitoring_bp.route("/")
@login_required
def index():
    targets = mon.prom_targets()
    alerts  = mon.active_alerts()
    hist    = mon.history(50)
    summary = mon.summary()
    return render_template(
        "monitoring/index.html",
        targets=targets,
        alerts=alerts,
        history=hist,
        summary=summary,
    )


@monitoring_bp.route("/api/summary")
@login_required
def api_summary():
    return jsonify(mon.summary())


@monitoring_bp.route("/api/alerts")
@login_required
def api_alerts():
    return jsonify({
        "active":  mon.active_alerts(),
        "history": mon.history(50),
    })


@monitoring_bp.route("/api/targets")
@login_required
def api_targets():
    return jsonify(mon.prom_targets())


# --------- Webhook Alertmanager (sem auth, loopback apenas) ---------
@monitoring_bp.route("/api/alerts/webhook", methods=["POST"])
def webhook():
    # Aceita apenas loopback
    remote = request.remote_addr or ""
    fwd    = request.headers.get("X-Forwarded-For", "")
    if remote not in ("127.0.0.1", "::1") or fwd:
        return abort(403)
    try:
        payload = request.get_json(force=True, silent=True) or {}
    except Exception:
        payload = {}
    try:
        res = mon.ingest_webhook(payload)
        count = len(payload.get("alerts", []))
        log("alert_webhook", "alertmanager", f"n={count} active_now={res['active']}")
        return jsonify({"ok": True, **res})
    except Exception as e:
        log("alert_webhook", "alertmanager", f"ERROR: {e}", ok=False)
        return jsonify({"ok": False, "error": str(e)}), 500


# --------- Auth check para nginx auth_request ---------
# Importado no auth_bp via /auth/check (definido em auth_bp tambem, mas aqui por seguranca)
