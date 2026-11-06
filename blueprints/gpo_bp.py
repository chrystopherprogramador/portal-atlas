from flask import Blueprint, render_template, request, redirect, url_for, flash
from modules.auth import login_required
from modules import ad, audit, gpo_editor
from modules.gpo_policy import CATALOG, catalog_index, TYPE_NAMES

gpo_bp = Blueprint("gpo", __name__)


def _norm_guid(g):
    g = (g or "").strip()
    if not g:
        return ""
    if not g.startswith("{"):
        g = "{" + g
    if not g.endswith("}"):
        g = g + "}"
    return g.upper()


@gpo_bp.route("/")
@login_required
def index():
    gpos = ad.list_gpos()
    return render_template("gpo/list.html", gpos=gpos)


@gpo_bp.route("/novo", methods=["POST"])
@login_required
def new():
    name = request.form["name"].strip()
    r = ad.gpo_create(name)
    ok = r.returncode == 0
    audit.log("gpo_create", name, (r.stdout + r.stderr).strip(), ok=ok)
    flash((r.stdout + r.stderr).strip() or ("OK" if ok else "erro"),
          "ok" if ok else "err")
    return redirect(url_for("gpo.index"))


@gpo_bp.route("/<guid>")
@login_required
def show(guid):
    guid = _norm_guid(guid)
    info = ad.gpo_show(guid)
    if not info:
        flash("GPO nao encontrada", "err")
        return redirect(url_for("gpo.index"))

    containers = ad.gpo_list_containers(guid)
    for c in containers:
        opts = ad.gpo_get_link_options(c["dn"])
        if guid in opts:
            c.update(opts[guid])
        # herança da OU
        c["inheritance"] = ad.gpo_get_inheritance(c["dn"])

    targets = ad.gpo_link_targets()
    linked_dns = {c["dn"].lower() for c in containers}
    avail_targets = [t for t in targets if t["dn"].lower() not in linked_dns]

    flags = ad.gpo_get_flags(guid)
    state = {
        "user_enabled":     not (flags & 1),
        "computer_enabled": not (flags & 2),
        "flags": flags,
    }

    entries = gpo_editor.annotate_with_catalog(gpo_editor.list_entries(guid))
    # ja-aplicadas: set de catalog_ids presentes
    applied_ids = {e["catalog_id"] for e in entries["user"] + entries["machine"]
                   if e.get("catalog_id")}
    catalog_avail = [p for p in CATALOG if p["id"] not in applied_ids]

    return render_template("gpo/show.html",
                           guid=guid, info=info,
                           containers=containers,
                           targets=avail_targets,
                           state=state,
                           entries=entries,
                           catalog_avail=catalog_avail,
                           type_names=TYPE_NAMES)


@gpo_bp.route("/<guid>/link", methods=["POST"])
@login_required
def link(guid):
    guid = _norm_guid(guid)
    container = request.form["container"].strip()
    enforce = request.form.get("enforce") == "1"
    disable = request.form.get("disable") == "1"
    r = ad.gpo_link(container, guid, enforce=enforce, disable=disable)
    ok = r.returncode == 0
    audit.log("gpo_link", guid, f"{container} enforce={enforce} disable={disable}", ok=ok)
    flash((r.stdout + r.stderr).strip() or ("Linkado" if ok else "erro"),
          "ok" if ok else "err")
    return redirect(url_for("gpo.show", guid=guid))


@gpo_bp.route("/<guid>/unlink", methods=["POST"])
@login_required
def unlink(guid):
    guid = _norm_guid(guid)
    container = request.form["container"].strip()
    r = ad.gpo_unlink(container, guid)
    ok = r.returncode == 0
    audit.log("gpo_unlink", guid, container, ok=ok)
    flash((r.stdout + r.stderr).strip() or ("Removido" if ok else "erro"),
          "ok" if ok else "err")
    return redirect(url_for("gpo.show", guid=guid))


@gpo_bp.route("/<guid>/state", methods=["POST"])
@login_required
def state(guid):
    guid = _norm_guid(guid)
    user_on = request.form.get("user_enabled") == "1"
    comp_on = request.form.get("computer_enabled") == "1"
    r = ad.gpo_set_state(guid, user_enabled=user_on, computer_enabled=comp_on)
    ok = r.returncode == 0
    audit.log("gpo_state", guid, f"user={user_on} computer={comp_on}", ok=ok)
    flash((r.stdout + r.stderr).strip() or ("OK" if ok else "erro"),
          "ok" if ok else "err")
    return redirect(url_for("gpo.show", guid=guid))


@gpo_bp.route("/<guid>/delete", methods=["POST"])
@login_required
def delete(guid):
    guid = _norm_guid(guid)
    r = ad.gpo_delete(guid)
    ok = r.returncode == 0
    audit.log("gpo_delete", guid, (r.stdout + r.stderr).strip(), ok=ok)
    flash((r.stdout + r.stderr).strip() or ("Removida" if ok else "erro"),
          "ok" if ok else "err")
    if ok:
        return redirect(url_for("gpo.index"))
    return redirect(url_for("gpo.show", guid=guid))


@gpo_bp.route("/inheritance", methods=["POST"])
@login_required
def inheritance():
    container = request.form["container"].strip()
    block = request.form.get("block") == "1"
    r = ad.gpo_set_inheritance(container, block=block)
    ok = r.returncode == 0
    audit.log("gpo_inheritance", container, "block" if block else "inherit", ok=ok)
    flash((r.stdout + r.stderr).strip() or ("OK" if ok else "erro"),
          "ok" if ok else "err")
    ref = request.form.get("ref_guid", "").strip()
    if ref:
        return redirect(url_for("gpo.show", guid=_norm_guid(ref)))
    return redirect(url_for("gpo.index"))


@gpo_bp.route("/<guid>/policy/add", methods=["POST"])
@login_required
def policy_add(guid):
    guid = _norm_guid(guid)
    pid = request.form["catalog_id"].strip()
    cat = catalog_index().get(pid)
    if not cat:
        flash("politica desconhecida", "err")
        return redirect(url_for("gpo.show", guid=guid))
    raw = request.form.get("data", "").strip()
    if not raw:
        # se nao veio nada, usa primeira opcao do catalogo
        raw = str(list(cat["options"].values())[0])
    type_name = TYPE_NAMES.get(cat["type"], "REG_DWORD")
    r = gpo_editor.set_value(guid, cat["scope"], cat["key"], cat["value"], type_name, raw)
    ok = r.returncode == 0
    audit.log("gpo_policy_add", guid, f"{pid}={raw}", ok=ok)
    flash((r.stdout + r.stderr).strip() or ("OK" if ok else "erro"),
          "ok" if ok else "err")
    return redirect(url_for("gpo.show", guid=guid))


@gpo_bp.route("/<guid>/policy/remove", methods=["POST"])
@login_required
def policy_remove(guid):
    guid = _norm_guid(guid)
    scope = request.form["scope"].strip()
    key   = request.form["key"].strip()
    name  = request.form["name"].strip()
    r = gpo_editor.unset_value(guid, scope, key, name)
    ok = r.returncode == 0
    audit.log("gpo_policy_remove", guid, f"{scope}:{key}::{name}", ok=ok)
    flash((r.stdout + r.stderr).strip() or ("OK" if ok else "erro"),
          "ok" if ok else "err")
    return redirect(url_for("gpo.show", guid=guid))


@gpo_bp.route("/<guid>/policy/raw-set", methods=["POST"])
@login_required
def policy_raw_set(guid):
    """Insere/atualiza um valor 'avancado' fora do catalogo (modo expert)."""
    guid = _norm_guid(guid)
    scope = request.form["scope"].strip()
    key   = request.form["key"].strip()
    name  = request.form["name"].strip()
    vtype = request.form.get("type", "REG_DWORD").strip()
    data  = request.form.get("data", "").strip()
    if not (key and name):
        flash("chave/nome obrigatorios", "err")
        return redirect(url_for("gpo.show", guid=guid))
    r = gpo_editor.set_value(guid, scope, key, name, vtype, data)
    ok = r.returncode == 0
    audit.log("gpo_policy_raw", guid, f"{scope}:{key}::{name}={data}", ok=ok)
    flash((r.stdout + r.stderr).strip() or ("OK" if ok else "erro"),
          "ok" if ok else "err")
    return redirect(url_for("gpo.show", guid=guid))
