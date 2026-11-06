from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, abort
from modules.auth import login_required
from modules import wallpaper, audit
import os

wallpaper_bp = Blueprint("wallpaper", __name__)


@wallpaper_bp.route("/")
@login_required
def index():
    info = wallpaper.info()
    return render_template(
        "wallpaper/index.html",
        info=info,
        styles=wallpaper.STYLES,
    )


@wallpaper_bp.route("/init", methods=["POST"])
@login_required
def init():
    r = wallpaper.init()
    ok = r.returncode == 0
    audit.log("wallpaper_init", "", (r.stdout + r.stderr).strip(), ok=ok)
    flash((r.stdout + r.stderr).strip() or ("Inicializado" if ok else "Erro"),
          "ok" if ok else "err")
    return redirect(url_for("wallpaper.index"))


@wallpaper_bp.route("/upload", methods=["POST"])
@login_required
def upload():
    f = request.files.get("image")
    if not f or not f.filename:
        flash("Selecione uma imagem", "err")
        return redirect(url_for("wallpaper.index"))
    if f.mimetype and not f.mimetype.startswith("image/"):
        flash("Arquivo nao parece ser uma imagem", "err")
        return redirect(url_for("wallpaper.index"))
    r = wallpaper.set_image_from_upload(f)
    ok = r.returncode == 0
    audit.log("wallpaper_set_image", f.filename, (r.stdout + r.stderr).strip(), ok=ok)
    flash((r.stdout + r.stderr).strip() or ("Imagem atualizada" if ok else "Erro"),
          "ok" if ok else "err")
    return redirect(url_for("wallpaper.index"))


@wallpaper_bp.route("/style", methods=["POST"])
@login_required
def style():
    s = request.form.get("style", "").strip()
    if s not in wallpaper.STYLES:
        flash("Estilo invalido", "err")
        return redirect(url_for("wallpaper.index"))
    r = wallpaper.set_style(s)
    ok = r.returncode == 0
    audit.log("wallpaper_set_style", s, (r.stdout + r.stderr).strip(), ok=ok)
    flash((r.stdout + r.stderr).strip(), "ok" if ok else "err")
    return redirect(url_for("wallpaper.index"))


@wallpaper_bp.route("/preview")
@login_required
def preview():
    info = wallpaper.info()
    path = info.get("IMAGE_PATH")
    if not path or not os.path.isfile(path):
        abort(404)
    return send_file(path, mimetype="image/jpeg",
                     last_modified=int(os.path.getmtime(path)))


@wallpaper_bp.route("/disable", methods=["POST"])
@login_required
def disable():
    r = wallpaper.disable()
    ok = r.returncode == 0
    audit.log("wallpaper_disable", "", (r.stdout + r.stderr).strip(), ok=ok)
    flash((r.stdout + r.stderr).strip(), "ok" if ok else "err")
    return redirect(url_for("wallpaper.index"))
