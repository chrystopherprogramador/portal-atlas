from flask import Blueprint, render_template, request, redirect, url_for, flash
from modules.auth import login_required
from modules import shares, ad, audit

shares_bp = Blueprint("shares", __name__)


@shares_bp.route("/")
@login_required
def index():
    data = shares.list_shares()
    groups = ad.list_groups()
    return render_template("shares/list.html", shares=data, groups=groups)


@shares_bp.route("/novo", methods=["POST"])
@login_required
def new():
    name = request.form["name"].strip()
    group = request.form["group"].strip()
    desc = request.form.get("description", "").strip()
    if not name or not group:
        flash("Nome e grupo sao obrigatorios", "err")
        return redirect(url_for("shares.index"))
    r = shares.add_share(name, group, desc)
    ok = r.returncode == 0
    audit.log("share_create", name, f"group={group}; {r.stdout}{r.stderr}", ok=ok)
    flash(r.stdout + r.stderr if (r.stdout or r.stderr) else ("Criado" if ok else "Erro"),
          "ok" if ok else "err")
    return redirect(url_for("shares.index"))


@shares_bp.route("/<name>/grupo", methods=["POST"])
@login_required
def setgroup(name):
    group = request.form["group"].strip()
    r = shares.set_group(name, group)
    ok = r.returncode == 0
    audit.log("share_setgroup", name, f"group={group}; {r.stdout}{r.stderr}", ok=ok)
    flash(r.stdout + r.stderr, "ok" if ok else "err")
    return redirect(url_for("shares.index"))


@shares_bp.route("/<name>/delete", methods=["POST"])
@login_required
def delete(name):
    r = shares.del_share(name)
    ok = r.returncode == 0
    audit.log("share_delete", name, r.stdout + r.stderr, ok=ok)
    flash(r.stdout + r.stderr, "ok" if ok else "err")
    return redirect(url_for("shares.index"))
