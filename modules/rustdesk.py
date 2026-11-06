"""Modulo RustDesk: gerenciar hbbs/hbbr no servidor + credenciais."""
import json
import os
import subprocess

SETTINGS = "/etc/portal-atlas/rustdesk.json"
KEY_DIR = "/var/lib/rustdesk-data"
PUBKEY_FILE = os.path.join(KEY_DIR, "id_ed25519.pub")
COMPOSE_DIR = "/opt/rustdesk"
INSTALLER = "/var/lib/rustdesk-data/rustdesk-original.exe"


def _load():
    if os.path.exists(SETTINGS):
        try:
            with open(SETTINGS) as f:
                return json.load(f)
        except Exception:
            pass
    return {"public_host": "", "relay_host": "", "api_host": ""}


def _save(d):
    os.makedirs(os.path.dirname(SETTINGS), exist_ok=True)
    with open(SETTINGS, "w") as f:
        json.dump(d, f, indent=2)
    os.chmod(SETTINGS, 0o644)


def get_settings():
    return _load()


def save_settings(public_host, relay_host="", api_host=""):
    d = {
        "public_host": (public_host or "").strip(),
        "relay_host": (relay_host or "").strip(),
        "api_host": (api_host or "").strip(),
    }
    _save(d)
    return d


def get_public_key():
    """Le a chave publica gerada pelo hbbs."""
    if os.path.exists(PUBKEY_FILE):
        try:
            with open(PUBKEY_FILE) as f:
                return f.read().strip()
        except Exception as e:
            return f"<erro: {e}>"
    return ""


def get_status():
    """Retorna estado dos containers."""
    try:
        r = subprocess.run(
            ["sudo", "-n", "/usr/bin/docker", "ps",
             "--filter", "name=hbbs", "--filter", "name=hbbr",
             "--format", "{{.Names}}|{{.Status}}|{{.Ports}}"],
            capture_output=True, text=True, timeout=10
        )
        out = (r.stdout or "").strip()
        items = []
        for line in out.splitlines():
            parts = line.split("|", 2)
            if len(parts) == 3:
                items.append({"name": parts[0], "status": parts[1], "ports": parts[2]})
        return items
    except Exception as e:
        return [{"name": "?", "status": f"erro: {e}", "ports": ""}]


def restart():
    r = subprocess.run(
        ["sudo", "-n", "/usr/local/sbin/gerenciar-rustdesk.sh", "restart"],
        capture_output=True, text=True, timeout=60
    )
    return r.returncode == 0, (r.stdout + r.stderr).strip()


def installer_exists():
    return os.path.exists(INSTALLER) and os.path.getsize(INSTALLER) > 1024 * 1024


def installer_path():
    return INSTALLER


def installer_size():
    try:
        return os.path.getsize(INSTALLER)
    except Exception:
        return 0


def download_installer():
    """Baixa o cliente Windows oficial. Retorna (ok, msg)."""
    r = subprocess.run(
        ["sudo", "-n", "/usr/local/sbin/gerenciar-rustdesk.sh", "fetch_client"],
        capture_output=True, text=True, timeout=600
    )
    return r.returncode == 0, (r.stdout + r.stderr).strip()
