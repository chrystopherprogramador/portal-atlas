"""Backup Borg - interface para o portal.
Usa /usr/local/sbin/atlas-backup.sh via sudo.
"""
import json
import subprocess
import os
import re
from datetime import datetime, timezone


SCRIPT = ["sudo", "-n", "/usr/local/sbin/atlas-backup.sh"]
ENV_FILE = "/etc/atlas-backup/env"
PUBKEY_FILE = "/etc/atlas-backup/id_ed25519.pub"


def _run(cmd, timeout=30):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except Exception as e:
        return 1, "", str(e)


def status():
    """Retorna dict com status do backup (nunca levanta)."""
    rc, out, err = _run(SCRIPT + ["status"], timeout=10)
    try:
        data = json.loads(out)
    except Exception:
        data = {"running": False, "last": {}, "next": None, "error": err or "parse_failed"}

    # Campos derivados amigaveis
    last = data.get("last") or {}
    finished = last.get("finished")
    age_sec = None
    age_label = "nunca"
    status_label = "indefinido"
    status_color = "grey"
    if finished:
        try:
            dt = datetime.fromisoformat(finished.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            age_sec = int((datetime.now(timezone.utc) - dt).total_seconds())
            age_label = _fmt_age(age_sec)
        except Exception:
            pass

    st = (last.get("status") or "").lower()
    if data.get("running"):
        status_label = "em execucao"
        status_color = "blue"
    elif st == "ok":
        if age_sec is None or age_sec > 72 * 3600:
            status_label, status_color = "atrasado", "red"
        elif age_sec > 36 * 3600:
            status_label, status_color = "atencao", "yel"
        else:
            status_label, status_color = "ok", "green"
    elif st == "running":
        # last.json diz running mas nao tem processo -- travou
        status_label, status_color = "interrompido", "red"
    elif st == "failed":
        status_label, status_color = "falha", "red"
    else:
        status_label, status_color = "nunca rodou", "red"

    data["age_sec"]      = age_sec
    data["age_label"]    = age_label
    data["status_label"] = status_label
    data["status_color"] = status_color
    return data


def archives():
    """Lista archives do repo."""
    rc, out, err = _run(SCRIPT + ["list"], timeout=20)
    if rc != 0:
        return {"archives": [], "error": err[:500]}
    try:
        return json.loads(out)
    except Exception:
        return {"archives": [], "error": "parse_failed"}


def info():
    """Info do repo (stats de storage)."""
    rc, out, err = _run(SCRIPT + ["info"], timeout=20)
    if rc != 0:
        return {"error": err[:500]}
    try:
        return json.loads(out)
    except Exception:
        return {"error": "parse_failed"}


def run_now():
    """Dispara backup em background."""
    rc, out, err = _run(SCRIPT + ["run-detached"], timeout=10)
    return rc == 0, (err or out).strip()


def check():
    """Dispara borg check em background (demora)."""
    try:
        subprocess.Popen(
            ["sudo", "-n", "bash", "-c",
             "nohup /usr/local/sbin/atlas-backup.sh check >>/var/log/atlas-backup.log 2>&1 &"],
            start_new_session=True,
        )
        return True, "check iniciado em background"
    except Exception as e:
        return False, str(e)


def progress():
    """Retorna progresso do backup + tail de log. Nunca levanta."""
    rc, out, err = _run(SCRIPT + ["progress", "60"], timeout=10)
    try:
        return json.loads(out)
    except Exception:
        return {"running": False, "percent": 0, "phase": "", "detail": "",
                "log": [], "error": (err or "parse_failed")[:200]}


def get_schedule():
    """Retorna JSON {hour, minute, oncalendar, next, source}."""
    rc, out, err = _run(SCRIPT + ["get-schedule"], timeout=10)
    try:
        return json.loads(out)
    except Exception:
        return {"hour": None, "minute": None, "oncalendar": "", "next": "", "source": "?"}


def set_schedule(hhmm):
    """Altera a hora do timer. hhmm = 'HH:MM'. Retorna (ok, msg)."""
    rc, out, err = _run(SCRIPT + ["set-schedule", hhmm], timeout=10)
    if rc == 0:
        try:
            return True, json.loads(out)
        except Exception:
            return True, out.strip()
    return False, (err or out).strip()[:300]


# ---------- Helpers ----------
def _fmt_age(s):
    if s is None:
        return "?"
    if s < 60:   return f"{s}s"
    if s < 3600: return f"{s//60}min"
    if s < 86400: return f"{s//3600}h {(s%3600)//60}min"
    return f"{s//86400}d {(s%86400)//3600}h"


def fmt_bytes(n):
    try: n = int(n)
    except Exception: return "?"
    for u in ("B", "KB", "MB", "GB", "TB", "PB"):
        if n < 1024: return f"{n:.1f} {u}" if u != "B" else f"{n} {u}"
        n /= 1024
    return f"{n:.1f} EB"


# ============================================================
# Configuracao automatica do NAS (SSH)
# ============================================================

def remote_config():
    """Le /etc/atlas-backup/env e retorna dict com config remota atual."""
    out = {"configured": False, "remote_repo": None, "host": None, "user": None, "path": None,
           "pubkey": None, "pubkey_exists": False}
    try:
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                v = v.strip().strip('"').strip("'")
                if k.strip() == "REMOTE_REPO" and v:
                    out["remote_repo"] = v
                    out["configured"] = True
                    # ssh://user@host[:port]/path  OR  user@host:/path
                    m = re.match(r"ssh://([^@]+)@([^/:]+)(?::\d+)?(/.+)$", v)
                    if not m:
                        m = re.match(r"([^@]+)@([^:]+):(.+)$", v)
                    if m:
                        out["user"], out["host"], out["path"] = m.group(1), m.group(2), m.group(3)
    except Exception:
        pass
    try:
        if os.path.exists(PUBKEY_FILE):
            with open(PUBKEY_FILE) as f:
                out["pubkey"] = f.read().strip()
                out["pubkey_exists"] = True
    except Exception:
        pass
    return out


def ensure_ssh_key():
    """Garante que /etc/atlas-backup/id_ed25519 existe (chama install-remote)."""
    if os.path.exists(PUBKEY_FILE):
        return True, "ja existe"
    # install-remote gera a key se nao existir
    rc, out, err = _run(SCRIPT + ["install-remote", "dummy@dummy:/dummy"], timeout=30)
    if os.path.exists(PUBKEY_FILE):
        return True, "gerada"
    return False, err or out or "falha ao gerar"


def test_remote(host=None, port=22, user=None, path=None, timeout=15):
    """Testa SSH + borg info no repo remoto. Retorna (ok, msg)."""
    cfg = remote_config()
    host = host or cfg["host"]
    user = user or cfg["user"]
    path = path or cfg["path"]
    if not (host and user and path):
        return False, "repo remoto nao configurado"
    url = f"ssh://{user}@{host}:{port}{path}"
    rc, out, err = _run(SCRIPT + ["remote-test", url], timeout=timeout)
    if rc == 0:
        return True, out.strip() or "ok"
    return False, (err or out).strip()[:500]


def setup_remote(host, port, admin_user, admin_pass, remote_user, remote_path, progress=None):
    """Configura o NAS Debian via SSH usando credenciais de admin.
    Passos:
      1. SSH no NAS com admin_user/admin_pass
      2. apt-get install borgbackup
      3. cria usuario remote_user (se nao existir), home, .ssh/
      4. cria remote_path + chown
      5. adiciona authorized_keys com command="borg serve --restrict-to-path X --append-only",restrict
      6. grava REMOTE_REPO em /etc/atlas-backup/env
      7. roda borg init remoto
    Retorna (ok, log_lines).
    """
    import paramiko  # type: ignore
    log = []
    def P(msg):
        log.append(msg)
        if progress:
            try: progress(msg)
            except Exception: pass

    # Garante chave SSH local
    P("[1/8] Garantindo SSH key do Atlas...")
    ok, msg = ensure_ssh_key()
    if not ok:
        return False, log + [f"ERRO: nao consegui gerar key: {msg}"]
    pubkey = ""
    with open(PUBKEY_FILE) as f:
        pubkey = f.read().strip()
    P(f"  pubkey = {pubkey[:60]}...")

    # Conecta no NAS
    P(f"[2/8] Conectando em {admin_user}@{host}:{port}...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(hostname=host, port=int(port), username=admin_user,
                       password=admin_pass, timeout=15, allow_agent=False, look_for_keys=False)
    except Exception as e:
        return False, log + [f"ERRO SSH: {e}"]
    P("  conectado OK")

    def run_ssh(cmd, sudo=False, check=True):
        if sudo and admin_user != "root":
            # -S le senha do stdin; -p '' sem prompt
            full = f"sudo -S -p '' bash -c {shell_quote(cmd)}"
            stdin, stdout, stderr = client.exec_command(full, timeout=60)
            try:
                stdin.write(admin_pass + "\n")
                stdin.flush()
            except Exception: pass
        else:
            stdin, stdout, stderr = client.exec_command(cmd, timeout=60)
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        rc = stdout.channel.recv_exit_status()
        if check and rc != 0:
            raise RuntimeError(f"cmd falhou (rc={rc}): {cmd}\nSTDERR: {err.strip()[:500]}")
        return rc, out, err

    def shell_quote(s):
        return "'" + s.replace("'", "'\\''") + "'"

    try:
        # 2.5 Detectar sudo (Debian minimal nao tem sudo)
        P("[2.5/8] Verificando privilegios...")
        if admin_user != "root":
            rc, _, _ = run_ssh("command -v sudo", check=False)
            if rc != 0:
                client.close()
                return False, log + [
                    "ERRO: 'sudo' nao esta instalado no NAS.",
                    "OPCOES para resolver:",
                    "  A) No NAS: su - ; apt-get install -y sudo ; "
                    f"usermod -aG sudo {admin_user} ; exit ; exit  (reconecte)",
                    "  B) Use 'root' no campo Admin (com a senha de root).",
                ]
            rc, out, err = run_ssh("id -u", sudo=True, check=False)
            if rc != 0 or out.strip() != "0":
                client.close()
                return False, log + [
                    f"ERRO: usuario '{admin_user}' nao consegue escalar via sudo.",
                    f"STDERR: {err.strip()[:300]}",
                    f"Execute no NAS: su - ; usermod -aG sudo {admin_user}",
                ]
            P("  sudo OK")
        else:
            P("  login como root -> sem sudo")

        # 3. Instalar borg
        P("[3/8] Verificando/instalando borgbackup...")
        rc, out, _ = run_ssh("command -v borg", check=False)
        if rc != 0:
            P("  borg nao encontrado, instalando via apt...")
            run_ssh("export DEBIAN_FRONTEND=noninteractive; apt-get update -qq && apt-get install -y -qq borgbackup", sudo=True)
        rc, out, _ = run_ssh("borg --version")
        P(f"  {out.strip()}")

        # 4. Criar usuario
        P(f"[4/8] Criando usuario '{remote_user}'...")
        rc, out, _ = run_ssh(f"id {shell_quote(remote_user)}", check=False)
        if rc != 0:
            run_ssh(f"useradd -m -d /home/{remote_user} -s /bin/bash {shell_quote(remote_user)}", sudo=True)
            P(f"  usuario {remote_user} criado")
        else:
            P(f"  usuario ja existe (pode ser usuario de sistema)")
        # Destravar conta (useradd -m cria com senha locked '!' -> sshd recusa key via PAM)
        run_ssh(f"usermod -p '*' {shell_quote(remote_user)}", sudo=True)
        # Forcar shell (em alguns Debians o default vem como /usr/sbin/nologin e SSH rejeita)
        run_ssh(f"usermod -s /bin/bash {shell_quote(remote_user)}", sudo=True)

        # Descobre o HOME real do usuario (pode ser /var/backups se for user de sistema)
        rc, out, _ = run_ssh(f"getent passwd {shell_quote(remote_user)} | cut -d: -f6")
        user_home = out.strip() or f"/home/{remote_user}"
        P(f"  home real = {user_home}")

        # 5. Preparar diretorios (home + .ssh + repo path com owner correto)
        P(f"[5/8] Preparando {remote_path} e {user_home}/.ssh ...")
        run_ssh(f"mkdir -p {shell_quote(remote_path)} {shell_quote(user_home)}/.ssh && "
                f"chown {remote_user}:{remote_user} {shell_quote(user_home)} && "
                f"chmod 755 {shell_quote(user_home)} && "
                f"chown -R {remote_user}:{remote_user} {shell_quote(remote_path)} {shell_quote(user_home)}/.ssh && "
                f"chmod 700 {shell_quote(user_home)}/.ssh {shell_quote(remote_path)} && "
                f"touch {shell_quote(user_home)}/.ssh/authorized_keys && "
                f"chown {remote_user}:{remote_user} {shell_quote(user_home)}/.ssh/authorized_keys && "
                f"chmod 600 {shell_quote(user_home)}/.ssh/authorized_keys", sudo=True)

        # 6. Adicionar authorized_keys restrito (append-only)
        P("[6/8] Instalando chave publica restrita (append-only)...")
        entry = (f'command="borg serve --restrict-to-path {remote_path} --append-only",'
                 f'restrict {pubkey}\n')
        # Remove entradas antigas do Atlas (mesma pubkey fingerprint) e adiciona
        key_body = pubkey.split()[1] if len(pubkey.split()) >= 2 else pubkey
        run_ssh(
            f"AK={shell_quote(user_home)}/.ssh/authorized_keys; "
            f"grep -v {shell_quote(key_body)} $AK > ${{AK}}.tmp 2>/dev/null || true; "
            f"mv ${{AK}}.tmp $AK 2>/dev/null || true; "
            f"echo {shell_quote(entry.strip())} >> $AK; "
            f"chown {remote_user}:{remote_user} $AK && chmod 600 $AK",
            sudo=True)
        P("  chave instalada com restricoes")

        # 7. Grava REMOTE_REPO em /etc/atlas-backup/env local (via script)
        P("[7/8] Atualizando /etc/atlas-backup/env local...")
        remote_url = f"ssh://{remote_user}@{host}:{port}{remote_path}"
        rc, out, err = _run(SCRIPT + ["set-remote", remote_url], timeout=10)
        if rc != 0:
            return False, log + [f"ERRO set-remote: {err or out}"]
        P(f"  REMOTE_REPO={remote_url}")

        # 8. Inicializar repo remoto
        P("[8/8] Inicializando repo Borg remoto...")
        rc, out, err = _run(SCRIPT + ["init-remote"], timeout=60)
        combined = (out + "\n" + err).strip()
        if rc != 0 and "already exists" not in combined.lower() and "ja existe" not in combined.lower():
            return False, log + [f"ERRO borg init: {combined[:500]}"]
        P("  repo remoto pronto")

        client.close()
        return True, log + ["", "=== NAS CONFIGURADO COM SUCESSO ===",
                            f"Repositorio remoto: {remote_url}",
                            "Proximo backup replica automaticamente."]
    except Exception as e:
        try: client.close()
        except Exception: pass
        return False, log + [f"ERRO: {e}"]
