"""Terminal web - pagina que embute ttyd via iframe + endpoint auth-check para nginx."""
from flask import Blueprint, render_template, session, jsonify, make_response
from modules.auth import login_required

terminal_bp = Blueprint("terminal", __name__)


@terminal_bp.route("/terminal")
@login_required
def terminal():
    """Pagina com iframe fullscreen apontando para /terminal-ws/ (proxy nginx->ttyd)."""
    return render_template("terminal/index.html", user=session.get("user", "?"))


# NOTA: o endpoint /auth-check e registrado em app.py (nao aqui) porque
# precisa responder SEM o prefixo do blueprint e sem @login_required
# (nginx auth_request chama direto).
