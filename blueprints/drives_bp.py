from flask import Blueprint, render_template, request, redirect, url_for, flash
from modules.auth import login_required
from modules import drives, shares, ad, audit

drives_bp = Blueprint("drives", __name__)


def _suggest_group_for_share(share_name: str, valid_users: str) -> str:
    """Tenta deduzir o grupo principal a partir do nome ou de valid_users."""
    # 1) primeiro grupo em valid_users que nao seja Domain Admins / TI
    if valid_users:
        for tok in valid_users.split():
            tok = tok.strip().strip('"')
            if not tok.startswith("@"):
                continue
            g = tok[1:].strip('"')
            if g.lower() in ("domain admins", "ti", "administradores"):
                continue
            return g
    # 2) fallback: nome do share como nome do grupo
    return share_name


@drives_bp.route("/")
@login_required
def index():
    state = drives.info()
    cfg = state.get("config", {})

    # shares disponiveis (so os "managed" do portal)
    raw_shares = shares.list_shares()
    user_shares = [s for s in raw_shares if not s.get("system")]

    # grupos AD para os dropdowns
    try:
        groups = ad.list_groups()
    except Exception:
        groups = []

    # letras ja usadas (sera evitado nas sugestoes/linha livre)
    used = {(m.get("letter") or "").upper().rstrip(":") for m in cfg.get("mappings", [])}
    all_letters = [chr(c) for c in range(ord("D"), ord("Z") + 1)]
    free_letters = [L for L in all_letters if L not in used]

    # sugestoes para shares ainda nao mapeados (com letra distinta pre-atribuida)
    mapped_uncs = {(m.get("unc") or "").lower() for m in cfg.get("mappings", [])}
    suggestions = []
    fi = 0
    for s in user_shares:
        unc = f"\\\\atlas\\{s['name']}"
        if unc.lower() in mapped_uncs:
            continue
        # pega a proxima letra livre (ou volta para D se acabar)
        L = free_letters[fi] if fi < len(free_letters) else "D"
        fi += 1
        suggestions.append({
            "share": s["name"],
            "unc": unc,
            "label": s["name"],
            "suggested_group": _suggest_group_for_share(s["name"], s.get("valid_users", "")),
            "default_letter": L,
        })

    # letra padrao para a linha livre
    free_default = free_letters[fi] if fi < len(free_letters) else (free_letters[0] if free_letters else "Z")

    return render_template(
        "drives/index.html",
        state=state, cfg=cfg,
        suggestions=suggestions,
        groups=groups,
        letters=all_letters,
        free_default=free_default,
    )


@drives_bp.route("/init", methods=["POST"])
@login_required
def init_route():
    r = drives.init()
    ok = r.returncode == 0
    audit.log("drives_init", "", (r.stdout + r.stderr).strip(), ok=ok)
    flash((r.stdout + r.stderr).strip() or ("OK" if ok else "Erro"),
          "ok" if ok else "err")
    return redirect(url_for("drives.index"))


@drives_bp.route("/save", methods=["POST"])
@login_required
def save_route():
    """Salva apenas a configuracao geral (ti_group / domain)."""
    state = drives.info()
    cfg = state.get("config", {}) or {}
    ti_group = request.form.get("ti_group", cfg.get("ti_group") or "TI").strip()
    domain   = request.form.get("domain", cfg.get("domain") or "TEXASCO").strip()
    mappings = cfg.get("mappings") or []
    r = drives.save_config(ti_group, domain, mappings)
    ok = r.returncode == 0
    audit.log("drives_save_cfg", f"ti={ti_group} dom={domain}",
              (r.stdout + r.stderr).strip(), ok=ok)
    flash((r.stdout + r.stderr).strip() or ("Configuracao salva" if ok else "Erro"),
          "ok" if ok else "err")
    return redirect(url_for("drives.index"))


@drives_bp.route("/row", methods=["POST"])
@login_required
def row_save():
    """Salva (cria/atualiza) UM mapeamento e re-aplica a GPO.

    Form fields: letter, unc, label, groups (CSV), original_letter (opcional,
    para alterar a letra de um mapeamento existente).
    """
    letter   = (request.form.get("letter") or "").strip().upper().rstrip(":")
    unc      = (request.form.get("unc") or "").strip()
    label    = (request.form.get("label") or letter).strip()
    gcsv     = request.form.get("groups", "")
    original = (request.form.get("original_letter") or "").strip().upper().rstrip(":")
    gs       = [g.strip() for g in gcsv.replace(";", ",").split(",") if g.strip()]

    if not letter or not unc:
        flash("Letra e UNC sao obrigatorios.", "err")
        return redirect(url_for("drives.index"))

    state = drives.info()
    cfg = state.get("config", {}) or {}
    ti_group = cfg.get("ti_group") or "TI"
    domain   = cfg.get("domain") or "TEXASCO"
    mappings = list(cfg.get("mappings") or [])

    # Detecta colisao: se nao foi enviado original_letter (= adicao), mas a
    # letra ja existe num mapeamento diferente (UNC diferente), aborta.
    overwrite_ok = (request.form.get("overwrite") == "1")
    for m in mappings:
        ml = (m.get("letter") or "").upper().rstrip(":")
        if ml == letter and (m.get("unc") or "").lower() != unc.lower():
            if not original and not overwrite_ok:
                flash(f"Letra {letter}: ja esta em uso por {m.get('unc')}. "
                      f"Escolha outra letra (a proxima livre eh sugerida no dropdown).",
                      "err")
                return redirect(url_for("drives.index"))

    # remove a entrada antiga (pela letra original ou pela letra atual)
    keys_to_remove = {letter}
    if original:
        keys_to_remove.add(original)
    mappings = [m for m in mappings
                if (m.get("letter") or "").upper().rstrip(":") not in keys_to_remove]
    mappings.append({
        "letter": letter, "unc": unc, "label": label,
        "groups": gs, "action": "U",
    })

    r = drives.save_config(ti_group, domain, mappings)
    ok = r.returncode == 0
    audit.log("drives_row_save", f"{letter}={unc}",
              (r.stdout + r.stderr).strip(), ok=ok)
    flash((f"{letter}: -> {unc} salvo e aplicado" if ok else
           ((r.stdout + r.stderr).strip() or "Erro")),
          "ok" if ok else "err")
    return redirect(url_for("drives.index"))


@drives_bp.route("/row/delete", methods=["POST"])
@login_required
def row_delete():
    """Remove UM mapeamento (pela letra) e re-aplica a GPO."""
    letter = (request.form.get("letter") or "").strip().upper().rstrip(":")
    if not letter:
        flash("Letra ausente.", "err")
        return redirect(url_for("drives.index"))

    state = drives.info()
    cfg = state.get("config", {}) or {}
    ti_group = cfg.get("ti_group") or "TI"
    domain   = cfg.get("domain") or "TEXASCO"
    mappings = [m for m in (cfg.get("mappings") or [])
                if (m.get("letter") or "").upper().rstrip(":") != letter]

    r = drives.save_config(ti_group, domain, mappings)
    ok = r.returncode == 0
    audit.log("drives_row_delete", letter, (r.stdout + r.stderr).strip(), ok=ok)
    flash((f"{letter}: removido" if ok else
           ((r.stdout + r.stderr).strip() or "Erro")),
          "ok" if ok else "err")
    return redirect(url_for("drives.index"))


@drives_bp.route("/disable", methods=["POST"])
@login_required
def disable_route():
    r = drives.disable()
    ok = r.returncode == 0
    audit.log("drives_disable", "", (r.stdout + r.stderr).strip(), ok=ok)
    flash((r.stdout + r.stderr).strip() or ("OK" if ok else "Erro"),
          "ok" if ok else "err")
    return redirect(url_for("drives.index"))
