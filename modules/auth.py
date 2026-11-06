"""LDAP auth contra o proprio Samba AD."""
import ldap
import ldap.filter
import logging
from functools import wraps
from flask import session, redirect, url_for, request, flash, abort
import config

log = logging.getLogger(__name__)


def ldap_authenticate(username: str, password: str):
    """Bind como user@dominio. Retorna dict com info se OK, senao None."""
    if not username or not password:
        return None
    upn = f"{username}@{config.LDAP_DOMAIN}"
    # Samba AD exige TLS para simple bind. Cert self-signed local -> nao validar.
    ldap.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)
    ldap.set_option(ldap.OPT_X_TLS_NEWCTX, 0)
    conn = ldap.initialize(config.LDAP_URI)
    conn.set_option(ldap.OPT_REFERRALS, 0)
    conn.set_option(ldap.OPT_PROTOCOL_VERSION, 3)
    try:
        conn.simple_bind_s(upn, password)
    except ldap.INVALID_CREDENTIALS:
        log.warning("LDAP invalid credentials for %s", upn)
        return None
    except ldap.LDAPError as e:
        log.warning("LDAP bind error for %s: %s", upn, e)
        return None

    # Busca grupos do usuario
    try:
        res = conn.search_s(
            config.LDAP_BASE,
            ldap.SCOPE_SUBTREE,
            f"(sAMAccountName={ldap.filter.escape_filter_chars(username)})",
            ["memberOf", "displayName", "distinguishedName"],
        )
    except Exception as e:
        log.exception("LDAP search failed for %s: %s", username, e)
        res = []
    finally:
        try:
            conn.unbind_s()
        except Exception:
            pass

    if not res:
        log.warning("LDAP: user %s not found after bind", username)
        return None
    # res pode trazer referrals (dn=None). Pega a primeira entrada real.
    attrs = None
    for dn, a in res:
        if dn and isinstance(a, dict):
            attrs = a
            break
    if attrs is None:
        log.warning("LDAP: no usable entry for %s", username)
        return None
    groups = [g.decode(errors="ignore") for g in attrs.get("memberOf", [])]
    display_raw = attrs.get("displayName", [username.encode()])[0]
    display = display_raw.decode(errors="ignore") if isinstance(display_raw, bytes) else str(display_raw)
    is_admin = any(
        f"cn={config.PORTAL_ADMIN_GROUP}".lower() in g.lower() or
        "cn=domain admins" in g.lower()
        for g in groups
    )
    log.info("LDAP auth ok user=%s admin=%s groups=%d", username, is_admin, len(groups))
    if not is_admin:
        return None
    return {"username": username, "display": display, "groups": groups}


def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if "user" not in session:
            return redirect(url_for("auth.login", next=request.path))
        return f(*a, **kw)
    return wrapper


def current_user():
    return session.get("user")
