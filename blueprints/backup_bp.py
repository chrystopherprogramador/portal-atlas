from flask import Blueprint, render_template, redirect, url_for, flash, jsonify, request
from modules.auth import login_required
from modules import backup as bk, audit

backup_bp = Blueprint("backup", __name__)


@backup_bp.route("/")
@login_required
def index():
    st = bk.status()
    arc = bk.archives()
    nfo = bk.info()
    remote = bk.remote_config()
    schedule = bk.get_schedule()
    prog = bk.progress()
    return render_template("backup/index.html",
                           st=st, archives=arc.get("archives", []),
                           repo=nfo.get("cache", {}).get("stats", {}) if isinstance(nfo, dict) else {},
                           repo_info=nfo,
                           remote=remote,
                           schedule=schedule,
                           prog=prog,
                           fmt_bytes=bk.fmt_bytes)


@backup_bp.route("/setup-remote", methods=["POST"])
@login_required
def setup_remote():
    """Configura NAS automaticamente via SSH."""
    host = (request.form.get("host") or "").strip()
    port = (request.form.get("port") or "22").strip()
    admin_user = (request.form.get("admin_user") or "root").strip()
    admin_pass = request.form.get("admin_pass") or ""
    remote_user = (request.form.get("remote_user") or "backup").strip()
    remote_path = (request.form.get("remote_path") or "/srv/borg/atlas").strip()
    if not host or not admin_pass:
        return jsonify({"ok": False, "log": ["ERRO: host e senha sao obrigatorios"]}), 400
    try:
        ok, log = bk.setup_remote(host, port, admin_user, admin_pass,
                                  remote_user, remote_path)
    except Exception as e:
        audit.log("backup_setup_remote", host, f"EXCEPTION: {e}", ok=False)
        return jsonify({"ok": False, "log": [f"ERRO: {e}"]}), 500
    audit.log("backup_setup_remote", f"{remote_user}@{host}:{remote_path}",
              "ok" if ok else "FAIL: " + (log[-1] if log else "?"), ok=ok)
    return jsonify({"ok": ok, "log": log})


@backup_bp.route("/test-remote", methods=["POST"])
@login_required
def test_remote():
    ok, msg = bk.test_remote()
    audit.log("backup_test_remote", "", msg[:200], ok=ok)
    return jsonify({"ok": ok, "message": msg})


@backup_bp.route("/run", methods=["POST"])
@login_required
def run():
    ok, msg = bk.run_now()
    audit.log("backup_run", "", msg[:200], ok=ok)
    flash("Backup iniciado em background." if ok else f"Falha: {msg}",
          "ok" if ok else "err")
    return redirect(url_for("backup.index"))


@backup_bp.route("/check", methods=["POST"])
@login_required
def check():
    ok, msg = bk.check()
    audit.log("backup_check", "", msg[:200], ok=ok)
    flash(msg, "ok" if ok else "err")
    return redirect(url_for("backup.index"))


@backup_bp.route("/api/status")
@login_required
def api_status():
    return jsonify(bk.status())


@backup_bp.route("/api/progress")
@login_required
def api_progress():
    """Progresso em tempo real + tail do log. Para o frontend pollar."""
    return jsonify(bk.progress())


@backup_bp.route("/api/schedule")
@login_required
def api_schedule():
    return jsonify(bk.get_schedule())


@backup_bp.route("/schedule", methods=["POST"])
@login_required
def set_schedule():
    hhmm = (request.form.get("time") or "").strip()
    if not hhmm:
        return jsonify({"ok": False, "message": "informe o horario (HH:MM)"}), 400
    ok, res = bk.set_schedule(hhmm)
    audit.log("backup_set_schedule", hhmm, str(res)[:200], ok=ok)
    return jsonify({"ok": ok, "result": res})
