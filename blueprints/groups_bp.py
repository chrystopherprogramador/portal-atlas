from flask import Blueprint, render_template, request, redirect, url_for, flash
from modules.auth import login_required
from modules import ad, audit

groups_bp = Blueprint("groups", __name__)


@groups_bp.route("/")
@login_required
def index():
    groups = ad.list_groups()
    return render_template("groups/list.html", groups=groups)


@groups_bp.route("/novo", methods=["POST"])
@login_required
def new():
    name = request.form["name"].strip()
    r = ad.group_create(name)
    ok = r.returncode == 0
    audit.log("group_create", name, "", ok=ok)
    flash("Grupo criado" if ok else r.stderr, "ok" if ok else "err")
    return redirect(url_for("groups.index"))


@groups_bp.route("/<name>")
@login_required
def show(name):
    members = ad.group_members(name)
    users = ad.list_users()
    not_members = [u for u in users if u not in members]
    return render_template("groups/show.html", name=name, members=members, candidates=not_members)


@groups_bp.route("/<name>/add", methods=["POST"])
@login_required
def add_member(name):
    u = request.form["user"].strip()
    r = ad.group_add_member(name, u)
    ok = r.returncode == 0
    audit.log("group_add", f"{name}:{u}", "", ok=ok)
    flash("Adicionado" if ok else r.stderr, "ok" if ok else "err")
    return redirect(url_for("groups.show", name=name))


@groups_bp.route("/<name>/remove", methods=["POST"])
@login_required
def rem_member(name):
    u = request.form["user"].strip()
    r = ad.group_remove_member(name, u)
    ok = r.returncode == 0
    audit.log("group_remove", f"{name}:{u}", "", ok=ok)
    flash("Removido" if ok else r.stderr, "ok" if ok else "err")
    return redirect(url_for("groups.show", name=name))


@groups_bp.route("/<name>/delete", methods=["POST"])
@login_required
def delete(name):
    r = ad.group_delete(name)
    ok = r.returncode == 0
    audit.log("group_delete", name, "", ok=ok)
    flash("Excluido" if ok else r.stderr, "ok" if ok else "err")
    return redirect(url_for("groups.index"))
