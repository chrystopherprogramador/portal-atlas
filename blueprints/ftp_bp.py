from flask import Blueprint, render_template, request, redirect, url_for, flash
from modules.auth import login_required
from modules import ftp, audit

ftp_bp = Blueprint("ftp", __name__)


@ftp_bp.route("/")
@login_required
def index():
    users = ftp.list_users()
    return render_template(
        "ftp/list.html",
        users=users,
        status=ftp.status(),
        sessions=ftp.sessions(),
    )


@ftp_bp.route("/novo", methods=["POST"])
@login_required
def new():
    user = request.form.get("user", "").strip().lower()
    pwd  = request.form.get("password", "")
    if not ftp.valid_username(user):
        flash("Nome invalido (use letras minusculas, numeros, _ ou -)", "err")
        return redirect(url_for("ftp.index"))
    if len(pwd) < 6:
        flash("Senha precisa ter ao menos 6 caracteres", "err")
        return redirect(url_for("ftp.index"))
    r = ftp.add_user(user, pwd)
    ok = r.returncode == 0
    audit.log("ftp_create", user, (r.stdout + r.stderr).strip(), ok=ok)
    flash((r.stdout + r.stderr).strip() or ("Criado" if ok else "Erro"),
          "ok" if ok else "err")
    return redirect(url_for("ftp.index"))


@ftp_bp.route("/<user>/passwd", methods=["POST"])
@login_required
def passwd(user):
    pwd = request.form.get("password", "")
    if len(pwd) < 6:
        flash("Senha precisa ter ao menos 6 caracteres", "err")
        return redirect(url_for("ftp.index"))
    r = ftp.change_password(user, pwd)
    ok = r.returncode == 0
    audit.log("ftp_passwd", user, (r.stdout + r.stderr).strip(), ok=ok)
    flash((r.stdout + r.stderr).strip(), "ok" if ok else "err")
    return redirect(url_for("ftp.index"))


@ftp_bp.route("/<user>/lock", methods=["POST"])
@login_required
def lock(user):
    r = ftp.lock(user)
    ok = r.returncode == 0
    audit.log("ftp_lock", user, (r.stdout + r.stderr).strip(), ok=ok)
    flash((r.stdout + r.stderr).strip(), "ok" if ok else "err")
    return redirect(url_for("ftp.index"))


@ftp_bp.route("/<user>/unlock", methods=["POST"])
@login_required
def unlock(user):
    r = ftp.unlock(user)
    ok = r.returncode == 0
    audit.log("ftp_unlock", user, (r.stdout + r.stderr).strip(), ok=ok)
    flash((r.stdout + r.stderr).strip(), "ok" if ok else "err")
    return redirect(url_for("ftp.index"))


@ftp_bp.route("/<user>/delete", methods=["POST"])
@login_required
def delete(user):
    r = ftp.del_user(user)
    ok = r.returncode == 0
    audit.log("ftp_delete", user, (r.stdout + r.stderr).strip(), ok=ok)
    flash((r.stdout + r.stderr).strip(), "ok" if ok else "err")
    return redirect(url_for("ftp.index"))


@ftp_bp.route("/restart", methods=["POST"])
@login_required
def restart():
    r = ftp.restart()
    ok = r.returncode == 0
    audit.log("ftp_restart", "vsftpd", (r.stdout + r.stderr).strip(), ok=ok)
    flash((r.stdout + r.stderr).strip() or "Reiniciado", "ok" if ok else "err")
    return redirect(url_for("ftp.index"))
