from flask import Blueprint, render_template, request, redirect, url_for, session, flash, make_response
from modules.auth import ldap_authenticate
from modules.audit import log

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "")
        user = ldap_authenticate(u, p)
        if user:
            session.permanent = True
            session["user"] = user
            log("login", u, "ok")
            return redirect(request.args.get("next") or url_for("dashboard.index"))
        log("login", u, "FAIL", ok=False)
        flash("Credenciais invalidas ou usuario sem permissao.", "err")
    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    u = (session.get("user") or {}).get("username", "?")
    session.clear()
    log("logout", u)
    return redirect(url_for("auth.login"))


@auth_bp.route("/auth/check")
def auth_check():
    """Endpoint usado pelo nginx auth_request para validar sessao.
    Retorna 200 se logado, 401 caso contrario. Nunca retorna corpo
    para evitar exposicao via subrequest."""
    if "user" in session:
        resp = make_response("", 200)
        resp.headers["X-Portal-User"] = session["user"].get("username", "")
        return resp
    return ("", 401)
