import time, io
import qrcode
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, Response
from modules.auth import login_required
from modules import vpn as vpn_mod, audit

vpn_bp = Blueprint("vpn", __name__)


def _merge_peers():
    """Junta peers do wg0.conf (nome) com dados live do wg dump."""
    confp = {p["public_key"]: p for p in vpn_mod.list_peers_from_conf()}
    live = vpn_mod.wg_dump().get("peers", [])
    merged = []
    seen = set()
    for l in live:
        pk = l["public_key"]
        name = confp.get(pk, {}).get("name", "(desconhecido)")
        seen.add(pk)
        merged.append({**l, "name": name})
    # Peers sem atividade
    for pk, c in confp.items():
        if pk not in seen:
            merged.append({
                "name": c["name"], "public_key": pk,
                "endpoint": "-", "allowed_ips": c.get("ip", "-"),
                "latest_handshake": 0, "rx_bytes": 0, "tx_bytes": 0,
            })
    return sorted(merged, key=lambda x: x["name"])


def _fmt_bytes(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} TB"


def _fmt_handshake(ts):
    if not ts:
        return "nunca"
    delta = int(time.time()) - ts
    if delta < 60: return f"{delta}s atras"
    if delta < 3600: return f"{delta//60}m atras"
    if delta < 86400: return f"{delta//3600}h atras"
    return f"{delta//86400}d atras"


@vpn_bp.route("/")
@login_required
def index():
    peers = _merge_peers()
    return render_template(
        "vpn/list.html",
        peers=peers,
        fmt_bytes=_fmt_bytes,
        fmt_handshake=_fmt_handshake,
    )


@vpn_bp.route("/novo", methods=["POST"])
@login_required
def new():
    name = request.form["name"].strip()
    r = vpn_mod.add_peer(name)
    ok = r.returncode == 0
    audit.log("vpn_create", name, r.stdout + r.stderr, ok=ok)
    flash(f"Peer {name} criado" if ok else (r.stderr or r.stdout), "ok" if ok else "err")
    return redirect(url_for("vpn.index"))


@vpn_bp.route("/<name>/delete", methods=["POST"])
@login_required
def delete(name):
    r = vpn_mod.del_peer(name)
    ok = r.returncode == 0
    audit.log("vpn_delete", name, r.stdout + r.stderr, ok=ok)
    flash(f"Peer {name} removido" if ok else r.stderr, "ok" if ok else "err")
    return redirect(url_for("vpn.index"))


@vpn_bp.route("/<name>/conf")
@login_required
def download_conf(name):
    content = vpn_mod.read_conf(name)
    if not content:
        flash("Conf nao encontrada.", "err")
        return redirect(url_for("vpn.index"))
    audit.log("vpn_download", name)
    return Response(content, mimetype="text/plain",
                    headers={"Content-Disposition": f'attachment; filename="{name}.conf"'})


@vpn_bp.route("/<name>/qr.png")
@login_required
def qr(name):
    content = vpn_mod.read_conf(name)
    if not content:
        return "", 404
    img = qrcode.make(content)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")
