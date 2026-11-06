"""Blueprint Docker: painel completo de containers/imagens/volumes/redes."""
import re

from flask import (Blueprint, Response, flash, jsonify, redirect,
                   render_template, request, url_for)

from modules.auth import login_required
from modules import docker_mgr as dk
from modules import audit

docker_bp = Blueprint("docker", __name__, template_folder="../templates")

ID_RE = re.compile(r"^[a-zA-Z0-9._/:-]{1,128}$")


def _safe(s):
    return bool(s) and bool(ID_RE.match(s))


@docker_bp.route("/")
@login_required
def index():
    try:
        containers = dk.list_containers(all=True)
    except Exception as e:
        containers = []
        flash(f"erro listando containers: {e}", "err")
    try:
        images = dk.list_images()
    except Exception:
        images = []
    try:
        volumes = dk.list_volumes()
    except Exception:
        volumes = []
    try:
        networks = dk.list_networks()
    except Exception:
        networks = []
    try:
        info = dk.system_info()
    except Exception:
        info = {"version": {}, "df": []}
    try:
        stats = {s.get("Name"): s for s in dk.container_stats()}
    except Exception:
        stats = {}

    return render_template(
        "docker/index.html",
        containers=containers, images=images,
        volumes=volumes, networks=networks,
        info=info, stats=stats,
    )


@docker_bp.route("/container/<cid>/<action>", methods=["POST"])
@login_required
def container_act(cid, action):
    if not _safe(cid):
        flash("id invalido", "err")
        return redirect(url_for("docker.index"))
    try:
        ok, msg = dk.container_action(cid, action)
        audit.log(f"docker_{action}", cid, msg[:300], ok=ok)
        flash(f"{action} {cid[:12]}: {'ok' if ok else msg[:200]}",
              "ok" if ok else "err")
    except Exception as e:
        flash(f"erro: {e}", "err")
    return redirect(url_for("docker.index"))


@docker_bp.route("/container/<cid>/logs")
@login_required
def container_logs(cid):
    if not _safe(cid):
        return Response("id invalido", status=400, mimetype="text/plain")
    try:
        tail = int(request.args.get("tail", "300"))
    except ValueError:
        tail = 300
    tail = max(10, min(tail, 5000))
    try:
        text = dk.container_logs(cid, tail=tail)
    except Exception as e:
        text = f"[erro] {e}"
    if request.args.get("raw") == "1":
        return Response(text, mimetype="text/plain")
    return render_template("docker/logs.html", cid=cid, text=text, tail=tail)


@docker_bp.route("/container/<cid>/inspect")
@login_required
def container_inspect(cid):
    if not _safe(cid):
        return jsonify({"error": "id invalido"}), 400
    data = dk.container_inspect(cid)
    return jsonify(data or {})


@docker_bp.route("/image/pull", methods=["POST"])
@login_required
def image_pull():
    img = (request.form.get("image") or "").strip()
    if not _safe(img):
        flash("nome de imagem invalido", "err")
        return redirect(url_for("docker.index"))
    try:
        ok, msg = dk.pull_image(img)
        audit.log("docker_pull", img, msg[-300:], ok=ok)
        flash(f"pull {img}: {'ok' if ok else msg[-200:]}",
              "ok" if ok else "err")
    except Exception as e:
        flash(f"erro: {e}", "err")
    return redirect(url_for("docker.index"))


@docker_bp.route("/image/<iid>/delete", methods=["POST"])
@login_required
def image_delete(iid):
    if not _safe(iid):
        flash("id invalido", "err")
        return redirect(url_for("docker.index"))
    force = request.form.get("force") == "1"
    ok, msg = dk.remove_image(iid, force=force)
    audit.log("docker_rmi", iid, msg[:200], ok=ok)
    flash(f"rmi: {'ok' if ok else msg[:200]}", "ok" if ok else "err")
    return redirect(url_for("docker.index"))


@docker_bp.route("/volume/<name>/delete", methods=["POST"])
@login_required
def volume_delete(name):
    if not _safe(name):
        flash("nome invalido", "err")
        return redirect(url_for("docker.index"))
    ok, msg = dk.remove_volume(name)
    audit.log("docker_volume_rm", name, msg[:200], ok=ok)
    flash(f"volume rm: {'ok' if ok else msg[:200]}", "ok" if ok else "err")
    return redirect(url_for("docker.index"))


@docker_bp.route("/network/<name>/delete", methods=["POST"])
@login_required
def network_delete(name):
    if not _safe(name):
        flash("nome invalido", "err")
        return redirect(url_for("docker.index"))
    ok, msg = dk.remove_network(name)
    audit.log("docker_network_rm", name, msg[:200], ok=ok)
    flash(f"network rm: {'ok' if ok else msg[:200]}", "ok" if ok else "err")
    return redirect(url_for("docker.index"))


@docker_bp.route("/prune", methods=["POST"])
@login_required
def prune():
    volumes = request.form.get("volumes") == "1"
    ok, msg = dk.system_prune(volumes=volumes)
    audit.log("docker_prune", f"volumes={volumes}", msg[-300:], ok=ok)
    flash(f"prune: {'ok' if ok else msg[-200:]}", "ok" if ok else "err")
    return redirect(url_for("docker.index"))
