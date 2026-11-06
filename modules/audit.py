"""SQLite audit log."""
import sqlite3
from datetime import datetime
from flask import request, session
import config


def init_db():
    with sqlite3.connect(config.AUDIT_DB) as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                user TEXT,
                ip TEXT,
                action TEXT NOT NULL,
                target TEXT,
                detail TEXT,
                ok INTEGER NOT NULL DEFAULT 1
            )
        """)


def log(action, target="", detail="", ok=True):
    try:
        u = (session.get("user") or {}).get("username", "?")
    except Exception:
        u = "system"
    try:
        ip = request.headers.get("X-Real-IP", request.remote_addr or "?")
    except Exception:
        ip = "?"
    with sqlite3.connect(config.AUDIT_DB) as c:
        c.execute(
            "INSERT INTO audit (ts,user,ip,action,target,detail,ok) VALUES (?,?,?,?,?,?,?)",
            (datetime.utcnow().isoformat(timespec="seconds"), u, ip, action, target, detail, 1 if ok else 0),
        )


def tail(n=50):
    with sqlite3.connect(config.AUDIT_DB) as c:
        c.row_factory = sqlite3.Row
        rows = c.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (n,)).fetchall()
        return [dict(r) for r in rows]
