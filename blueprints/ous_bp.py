from flask import Blueprint, render_template, request, redirect, url_for, flash
from modules.auth import login_required
from modules import ad, audit

ous_bp = Blueprint("ous", __name__)


@ous_bp.route("/")
@login_required
def index():
    ous = ad.list_ous()
    try:
        groups = ad.list_groups()
    except Exception:
        groups = []
    mapping = ad.ou_group_map()
    return render_template("ous/list.html", ous=ous, groups=groups, mapping=mapping)


@ous_bp.route("/<ou>/grupo", methods=["POST"])
@login_required
def set_group(ou):
    grp = request.form.get("group", "").strip()
    ok = ad.ou_group_set(ou, grp)
    audit.log("ou_set_group", ou, grp or "(removido)", ok=ok)
    if ok:
        flash(f"OU={ou}: grupo correlato = {grp or '(nenhum)'}", "ok")
    else:
        flash("Falha ao salvar mapeamento.", "err")
    return redirect(url_for("ous.index"))


@ous_bp.route("/novo", methods=["POST"])
@login_required
def new():
    name = request.form["name"].strip()
    r = ad.ou_create(name)
    ok = r.returncode == 0
    audit.log("ou_create", name, (r.stdout + r.stderr).strip(), ok=ok)
    flash((r.stdout + r.stderr).strip() or ("OU criada" if ok else "erro"),
          "ok" if ok else "err")
    return redirect(url_for("ous.index"))


@ous_bp.route("/sincronizar-grupos", methods=["POST"])
@login_required
def sync_groups():
    msgs = ad.sync_ou_groups()
    summary = " | ".join(t for _, t in msgs[-8:])
    audit.log("ou_sync_groups", "", summary, ok=True)
    flash("Sincronizado: " + summary, "ok")
    return redirect(url_for("ous.index"))
