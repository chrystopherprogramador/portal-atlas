"""Blueprint RustDesk: painel + download de instalador pre-configurado."""
import io
import os
import re
import urllib.parse

from flask import (Blueprint, Response, abort, flash, redirect,
                   render_template, request, send_file, url_for)

from modules.auth import login_required
from modules import rustdesk as rd
from modules import audit

rustdesk_bp = Blueprint("rustdesk", __name__, template_folder="../templates")

HOST_RE = re.compile(r"^[a-zA-Z0-9.\-_:]{1,253}$")


@rustdesk_bp.route("/")
@login_required
def index():
    return render_template(
        "rustdesk/index.html",
        settings=rd.get_settings(),
        pubkey=rd.get_public_key(),
        status=rd.get_status(),
        installer=rd.installer_exists(),
        installer_size=rd.installer_size(),
    )


@rustdesk_bp.route("/save", methods=["POST"])
@login_required
def save():
    public_host = (request.form.get("public_host") or "").strip()
    relay_host = (request.form.get("relay_host") or "").strip()
    api_host = (request.form.get("api_host") or "").strip()
    for h in (public_host, relay_host, api_host):
        if h and not HOST_RE.match(h):
            flash(f"host invalido: {h}", "err")
            return redirect(url_for("rustdesk.index"))
    rd.save_settings(public_host, relay_host, api_host)
    audit.log("rustdesk_save", f"host={public_host}", "", ok=True)
    flash("configuracoes salvas", "ok")
    return redirect(url_for("rustdesk.index"))


@rustdesk_bp.route("/restart", methods=["POST"])
@login_required
def restart():
    ok, msg = rd.restart()
    audit.log("rustdesk_restart", "", msg, ok=ok)
    flash("RustDesk reiniciado" if ok else f"erro: {msg}",
          "ok" if ok else "err")
    return redirect(url_for("rustdesk.index"))


@rustdesk_bp.route("/fetch", methods=["POST"])
@login_required
def fetch():
    ok, msg = rd.download_installer()
    audit.log("rustdesk_fetch_client", "", msg[:300], ok=ok)
    flash("instalador baixado" if ok else f"erro: {msg[:200]}",
          "ok" if ok else "err")
    return redirect(url_for("rustdesk.index"))


@rustdesk_bp.route("/download")
@login_required
def download_installer():
    """Streama o .exe oficial com filename magico para auto-config.

    O RustDesk OSS le o proprio nome do arquivo no primeiro start.
    Formato: rustdesk-host=<server>,key=<pubkey>.exe
    """
    s = rd.get_settings()
    host = s.get("public_host") or ""
    if not host:
        flash("preencha o IP/dominio publico antes de baixar o instalador", "err")
        return redirect(url_for("rustdesk.index"))
    if not rd.installer_exists():
        flash("instalador ainda nao foi baixado para o servidor", "err")
        return redirect(url_for("rustdesk.index"))

    pub = rd.get_public_key()
    if not pub:
        flash("chave publica do hbbs ainda nao foi gerada", "err")
        return redirect(url_for("rustdesk.index"))

    # filename magico — RustDesk parseia ',' e '=' do proprio basename
    fname = f"rustdesk-host={host},key={pub}.exe"
    # alguns chars sao problematicos em headers — usa filename* RFC 5987
    quoted = urllib.parse.quote(fname)
    safe_ascii = re.sub(r"[^A-Za-z0-9._=,\-]", "_", fname)

    audit.log("rustdesk_download", host, f"size={rd.installer_size()}", ok=True)

    def gen():
        with open(rd.installer_path(), "rb") as f:
            while True:
                chunk = f.read(64 * 1024)
                if not chunk:
                    break
                yield chunk

    resp = Response(gen(), mimetype="application/vnd.microsoft.portable-executable")
    resp.headers["Content-Length"] = str(rd.installer_size())
    resp.headers["Content-Disposition"] = (
        f'attachment; filename="{safe_ascii}"; filename*=UTF-8\'\'{quoted}'
    )
    return resp


@rustdesk_bp.route("/script.bat")
@login_required
def install_bat():
    """Gera um .bat que baixa o cliente oficial, instala e grava config."""
    s = rd.get_settings()
    host = s.get("public_host") or ""
    relay = s.get("relay_host") or host
    api = s.get("api_host") or ""
    pub = rd.get_public_key()
    if not host or not pub:
        return Response("preencha o host publico no painel primeiro\n",
                        status=400, mimetype="text/plain")

    bat = f"""@echo off
REM ============================================================
REM   Instalador RustDesk pre-configurado - ATLAS Portal
REM   Servidor: {host}
REM ============================================================
setlocal

set RD_URL=https://github.com/rustdesk/rustdesk/releases/download/1.3.7/rustdesk-1.3.7-x86_64.exe
set RD_FILE=%TEMP%\\rustdesk-installer.exe

echo [1/4] Baixando RustDesk...
powershell -NoProfile -Command "Invoke-WebRequest -Uri '%RD_URL%' -OutFile '%RD_FILE%' -UseBasicParsing"
if errorlevel 1 (
  echo Falha no download
  pause
  exit /b 1
)

echo [2/4] Instalando (silencioso)...
"%RD_FILE%" --silent-install
timeout /t 8 /nobreak >nul

echo [3/4] Aplicando configuracao...
set CFG_DIR=%APPDATA%\\RustDesk\\config
mkdir "%CFG_DIR%" 2>nul

> "%CFG_DIR%\\RustDesk2.toml" (
  echo rendezvous_server = '{host}'
  echo nat_type = 1
  echo serial = 0
  echo.
  echo [options]
  echo custom-rendezvous-server = '{host}'
  echo relay-server = '{relay}'
  echo api-server = '{api}'
  echo key = '{pub}'
)

REM mesma config no ProgramData para todos os usuarios
set GLOBAL_DIR=C:\\ProgramData\\RustDesk\\config
mkdir "%GLOBAL_DIR%" 2>nul
copy /Y "%CFG_DIR%\\RustDesk2.toml" "%GLOBAL_DIR%\\RustDesk2.toml" >nul

echo [4/4] Reiniciando servico...
net stop rustdesk 2>nul
net start rustdesk 2>nul

echo.
echo === OK! RustDesk instalado e configurado ===
echo Servidor: {host}
echo Chave:    {pub[:30]}...
echo.
pause
"""
    audit.log("rustdesk_script_bat", host, "", ok=True)
    return Response(
        bat,
        mimetype="application/bat",
        headers={
            "Content-Disposition":
                'attachment; filename="instalar-rustdesk.bat"'
        },
    )
