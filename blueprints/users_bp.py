from flask import Blueprint, render_template, request, redirect, url_for, flash
from modules.auth import login_required
from modules import ad, audit

users_bp = Blueprint("users", __name__)


@users_bp.route("/")
@login_required
def index():
    try:
        users = ad.list_users()
    except Exception as e:
        users = []
        flash(f"Erro ao listar: {e}", "err")
    return render_template("users/list.html", users=users)


@users_bp.route("/novo", methods=["GET", "POST"])
@login_required
def new():
    if request.method == "POST":
        login_ = request.form["login"].strip()
        full = request.form["fullname"].strip()
        ou = request.form.get("ou", "TI").strip() or "TI"
        pwd = request.form.get("password") or "Texasco@2026"
        r = ad.user_create(login_, pwd, full, ou=ou)
        ok = r.returncode == 0
        audit.log("user_create", login_, r.stdout + r.stderr, ok=ok)
        flash(r.stdout + r.stderr, "ok" if ok else "err")
        if ok:
            return redirect(url_for("users.show", login=login_))
    ous = ad.list_ous()
    return render_template("users/new.html", ous=ous)


@users_bp.route("/<login>")
@login_required
def show(login):
    data = ad.user_show(login)
    return render_template("users/show.html", login=login, data=data)


@users_bp.route("/<login>/senha", methods=["POST"])
@login_required
def reset_pw(login):
    pwd = request.form.get("password") or "Texasco@2026"
    r = ad.user_setpassword(login, pwd)
    ok = r.returncode == 0
    audit.log("user_reset_pw", login, "reset", ok=ok)
    flash(f"Senha reiniciada para: {pwd}" if ok else r.stderr, "ok" if ok else "err")
    return redirect(url_for("users.show", login=login))


@users_bp.route("/<login>/enable", methods=["POST"])
@login_required
def enable(login):
    r = ad.user_enable(login)
    ok = r.returncode == 0
    audit.log("user_enable", login, "", ok=ok)
    flash("Habilitado" if ok else r.stderr, "ok" if ok else "err")
    return redirect(url_for("users.show", login=login))


@users_bp.route("/<login>/disable", methods=["POST"])
@login_required
def disable(login):
    r = ad.user_disable(login)
    ok = r.returncode == 0
    audit.log("user_disable", login, "", ok=ok)
    flash("Desabilitado" if ok else r.stderr, "ok" if ok else "err")
    return redirect(url_for("users.show", login=login))


@users_bp.route("/<login>/delete", methods=["POST"])
@login_required
def delete(login):
    r = ad.user_delete(login)
    ok = r.returncode == 0
    audit.log("user_delete", login, "", ok=ok)
    flash("Removido" if ok else r.stderr, "ok" if ok else "err")
    return redirect(url_for("users.index"))
