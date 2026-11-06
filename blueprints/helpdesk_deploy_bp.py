"""Blueprint: deploy/rollback do Helpdesk via web (upload .zip)."""
import os
import re
import secrets
import tempfile
import zipfile

from flask import (Blueprint, jsonify, redirect, render_template,
                   request, url_for, flash)

from modules.auth import login_required
from modules import helpdesk_deploy as hd
from modules import audit

helpdesk_deploy_bp = Blueprint("helpdesk_deploy", __name__,
                               template_folder="../templates")

# Limites locais (Flask MAX_CONTENT_LENGTH e nginx ja seguram antes)
MAX_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB
STAMP_RE = re.compile(r"^\d{8}-\d{6}$")
TAG_BAD = re.compile(r"[^A-Za-z0-9._-]")
JOBID_RE = re.compile(r"^[a-zA-Z0-9_-]{4,40}$")


def _new_jobid():
    return secrets.token_hex(8)  # 16 hex chars


def _validate_zip(path):
    """Retorna (ok, msg). Testa CRC e bloqueia paths suspeitos."""
    try:
        with zipfile.ZipFile(path) as z:
            bad = z.testzip()
            if bad:
                return False, f"zip corrompido em: {bad}"
            for n in z.namelist():
                if n.startswith("/") or ".." in n.split("/"):
                    return False, f"path suspeito no zip: {n}"
    except zipfile.BadZipFile:
        return False, "arquivo nao e um .zip valido"
    except Exception as e:
        return False, f"erro lendo zip: {e}"
    return True, ""


@helpdesk_deploy_bp.route("/")
@login_required
def index():
    try:
        st = hd.info()
    except Exception as e:
        st = {"_error": str(e)}
    try:
        versions = hd.list_versions()
    except Exception:
        versions = []
    return render_template("helpdesk_deploy/index.html",
                           state=st, versions=versions,
                           max_bytes=MAX_BYTES)


@helpdesk_deploy_bp.route("/deploy", methods=["POST"])
@login_required
def deploy():
    """Recebe upload do zip, valida e dispara deploy assincrono.
    Retorna JSON {job_id} (frontend faz polling de /deploy/status/<jobid>)."""
    f = request.files.get("zip")
    tag_raw = (request.form.get("tag") or "deploy").strip()
    tag = TAG_BAD.sub("_", tag_raw)[:40] or "deploy"

    if not f or not f.filename:
        return jsonify({"error": "selecione um arquivo .zip"}), 400
    if not f.filename.lower().endswith(".zip"):
        return jsonify({"error": "envie um arquivo .zip"}), 400

    # salva em /var/tmp (root, mode 644)
    fd, tmp = tempfile.mkstemp(prefix="hd_upload_", suffix=".zip", dir="/var/tmp")
    try:
        with os.fdopen(fd, "wb") as out:
            f.save(out)
        os.chmod(tmp, 0o644)
        size = os.path.getsize(tmp)
        if size <= 0:
            return jsonify({"error": "upload vazio"}), 400
        if size > MAX_BYTES:
            return jsonify({"error": f"upload excede {MAX_BYTES} bytes"}), 413

        ok, msg = _validate_zip(tmp)
        if not ok:
            return jsonify({"error": msg}), 400

        jobid = _new_jobid()
        hd.deploy_async(tmp, tag, jobid)
        audit.log("helpdesk_deploy_start", f"tag={tag} job={jobid}",
                  f"size={size}", ok=True)
        return jsonify({"job_id": jobid, "tag": tag, "size": size})
    except Exception as e:
        try:
            os.remove(tmp)
        except Exception:
            pass
        audit.log("helpdesk_deploy_start", "", str(e), ok=False)
        return jsonify({"error": str(e)}), 500


@helpdesk_deploy_bp.route("/rollback", methods=["POST"])
@login_required
def rollback():
    stamp = (request.form.get("stamp") or "").strip()
    if not STAMP_RE.match(stamp):
        return jsonify({"error": "stamp invalido"}), 400
    jobid = _new_jobid()
    try:
        hd.rollback_async(stamp, jobid)
        audit.log("helpdesk_rollback_start", f"stamp={stamp} job={jobid}",
                  "", ok=True)
        return jsonify({"job_id": jobid, "stamp": stamp})
    except Exception as e:
        audit.log("helpdesk_rollback_start", stamp, str(e), ok=False)
        return jsonify({"error": str(e)}), 500


@helpdesk_deploy_bp.route("/status/<jobid>")
@login_required
def deploy_status(jobid):
    if not JOBID_RE.match(jobid):
        return jsonify({"error": "jobid invalido"}), 400
    try:
        offset = int(request.args.get("offset", "0"))
    except ValueError:
        offset = 0
    try:
        text, new_offset, done, rc = hd.status(jobid, offset)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({
        "text": text,
        "offset": new_offset,
        "done": done,
        "rc": rc,
    })


@helpdesk_deploy_bp.route("/delete", methods=["POST"])
@login_required
def delete_version():
    stamp = (request.form.get("stamp") or "").strip()
    if not STAMP_RE.match(stamp):
        flash("stamp invalido", "err")
        return redirect(url_for("helpdesk_deploy.index"))
    try:
        out = hd.delete_version(stamp)
        audit.log("helpdesk_delete", stamp, out.strip(), ok=True)
        flash(f"versao {stamp} removida", "ok")
    except Exception as e:
        audit.log("helpdesk_delete", stamp, str(e), ok=False)
        flash(f"erro: {e}", "err")
    return redirect(url_for("helpdesk_deploy.index"))


@helpdesk_deploy_bp.route("/purge", methods=["POST"])
@login_required
def purge():
    try:
        keep = int(request.form.get("keep", "10"))
    except ValueError:
        keep = 10
    keep = max(1, min(keep, 200))
    try:
        out = hd.purge(keep)
        audit.log("helpdesk_purge", f"keep={keep}", out.strip(), ok=True)
        flash(f"purge ok: {out.strip()}", "ok")
    except Exception as e:
        audit.log("helpdesk_purge", f"keep={keep}", str(e), ok=False)
        flash(f"erro: {e}", "err")
    return redirect(url_for("helpdesk_deploy.index"))
