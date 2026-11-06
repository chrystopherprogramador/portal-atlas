from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from modules.auth import login_required
from modules import db as dbmod, audit

db_bp = Blueprint("db", __name__)


@db_bp.route("/")
@login_required
def index():
    try:
        databases = dbmod.list_databases()
        roles = dbmod.list_roles()
        version = dbmod.server_version()
        total = dbmod.total_size()
    except Exception as e:
        databases, roles, version, total = [], [], "?", "?"
        flash(f"Erro ao consultar PostgreSQL: {e}", "err")
    return render_template("db/list.html",
                           databases=databases, roles=roles,
                           version=version, total=total)


# ---------- Bancos ----------
@db_bp.route("/novo", methods=["POST"])
@login_required
def new_db():
    name  = (request.form.get("name") or "").strip().lower()
    owner = (request.form.get("owner") or "dbadmin").strip()
    rc, msg = dbmod.db_create(name, owner)
    ok = rc == 0
    audit.log("db_create", name, msg[:200], ok=ok)
    flash(f"Banco '{name}' criado (owner={owner})" if ok else f"Falha: {msg}",
          "ok" if ok else "err")
    return redirect(url_for("db.index"))


@db_bp.route("/<name>/drop", methods=["POST"])
@login_required
def drop_db(name):
    rc, msg = dbmod.db_drop(name)
    ok = rc == 0
    audit.log("db_drop", name, msg[:200], ok=ok)
    flash(f"Banco '{name}' removido" if ok else f"Falha: {msg}",
          "ok" if ok else "err")
    return redirect(url_for("db.index"))


@db_bp.route("/<name>/chown", methods=["POST"])
@login_required
def chown_db(name):
    new_owner = (request.form.get("owner") or "").strip()
    rc, msg = dbmod.db_owner_change(name, new_owner)
    ok = rc == 0
    audit.log("db_chown", f"{name}->{new_owner}", msg[:200], ok=ok)
    flash(f"Owner de '{name}' -> {new_owner}" if ok else f"Falha: {msg}",
          "ok" if ok else "err")
    return redirect(url_for("db.index"))


# ---------- Roles ----------
@db_bp.route("/role/novo", methods=["POST"])
@login_required
def new_role():
    name = (request.form.get("name") or "").strip().lower()
    pw   = request.form.get("password") or ""
    opts = ["LOGIN"]
    if request.form.get("createdb"):   opts.append("CREATEDB")
    if request.form.get("createrole"): opts.append("CREATEROLE")
    if request.form.get("superuser"):  opts.append("SUPERUSER")
    rc, msg = dbmod.role_create(name, pw, opts)
    ok = rc == 0
    audit.log("role_create", name, ",".join(opts), ok=ok)
    flash(f"Role '{name}' criada" if ok else f"Falha: {msg}",
          "ok" if ok else "err")
    return redirect(url_for("db.index"))


@db_bp.route("/role/<name>/password", methods=["POST"])
@login_required
def role_password(name):
    pw = request.form.get("password") or ""
    rc, msg = dbmod.role_set_password(name, pw)
    ok = rc == 0
    audit.log("role_passwd", name, "", ok=ok)
    flash(f"Senha de '{name}' alterada" if ok else f"Falha: {msg}",
          "ok" if ok else "err")
    return redirect(url_for("db.index"))


@db_bp.route("/role/<name>/drop", methods=["POST"])
@login_required
def drop_role(name):
    rc, msg = dbmod.role_drop(name)
    ok = rc == 0
    audit.log("role_drop", name, msg[:200], ok=ok)
    flash(f"Role '{name}' removida" if ok else f"Falha: {msg}",
          "ok" if ok else "err")
    return redirect(url_for("db.index"))
