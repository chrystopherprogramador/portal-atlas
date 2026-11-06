import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("PORTAL_DATA_DIR", "/var/lib/portal-atlas"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

SECRET_KEY = os.environ.get("PORTAL_SECRET_KEY") or os.urandom(32).hex()

# AD / LDAP
LDAP_URI    = os.environ.get("PORTAL_LDAP_URI", "ldaps://127.0.0.1")
LDAP_DOMAIN = os.environ.get("PORTAL_LDAP_DOMAIN", "texasco.local")
LDAP_REALM  = LDAP_DOMAIN.upper()
LDAP_BASE   = "dc=" + ",dc=".join(LDAP_DOMAIN.split("."))
NETBIOS     = os.environ.get("PORTAL_NETBIOS", "TEXASCO")

# Grupo que libera acesso ao portal
PORTAL_ADMIN_GROUP = os.environ.get("PORTAL_ADMIN_GROUP", "PortalAdmins")

# Sessao
SESSION_TIMEOUT_MIN = int(os.environ.get("PORTAL_SESSION_TIMEOUT_MIN", "10"))

# VPN
VPN_CLIENTS_DIR = Path("/etc/wireguard/clients")
VPN_SHARE_DIR   = Path("/srv/samba/vpn")
VPN_ENDPOINT    = os.environ.get("PORTAL_VPN_ENDPOINT", "200.9.18.201")

# Audit
AUDIT_DB = DATA_DIR / "audit.db"

# sudo wrappers
SUDO = ["sudo", "-n"]
SAMBA_TOOL = ["sudo", "-n", "samba-tool"]
WG = ["sudo", "-n", "wg"]
