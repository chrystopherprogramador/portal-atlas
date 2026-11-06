from flask import Flask, redirect, url_for, session, make_response
from datetime import timedelta
import config

from blueprints.auth_bp import auth_bp
from blueprints.dashboard_bp import dashboard_bp
from blueprints.users_bp import users_bp
from blueprints.groups_bp import groups_bp
from blueprints.ous_bp import ous_bp
from blueprints.gpo_bp import gpo_bp
from blueprints.vpn_bp import vpn_bp
from blueprints.shares_bp import shares_bp
from blueprints.ftp_bp import ftp_bp
from blueprints.wallpaper_bp import wallpaper_bp
from blueprints.drives_bp import drives_bp
from blueprints.db_bp import db_bp
from blueprints.backup_bp import backup_bp
from blueprints.monitoring_bp import monitoring_bp
from blueprints.terminal_bp import terminal_bp
from blueprints.helpdesk_deploy_bp import helpdesk_deploy_bp
from blueprints.rustdesk_bp import rustdesk_bp
from blueprints.docker_bp import docker_bp
from modules.audit import init_db


def create_app():
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config["SECRET_KEY"] = config.SECRET_KEY
    app.permanent_session_lifetime = timedelta(minutes=config.SESSION_TIMEOUT_MIN)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    # Upload do helpdesk pode chegar a ~200MB
    # 2 GB para upload do helpdesk (.zip)
    app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024 * 1024 + 64 * 1024 * 1024

    init_db()

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(users_bp,  url_prefix="/usuarios")
    app.register_blueprint(groups_bp, url_prefix="/grupos")
    app.register_blueprint(ous_bp,    url_prefix="/ous")
    app.register_blueprint(gpo_bp,    url_prefix="/gpo")
    app.register_blueprint(vpn_bp,    url_prefix="/vpn")
    app.register_blueprint(shares_bp, url_prefix="/pastas")
    app.register_blueprint(ftp_bp,    url_prefix="/ftp")
    app.register_blueprint(wallpaper_bp, url_prefix="/wallpaper")
    app.register_blueprint(drives_bp,    url_prefix="/drives")
    app.register_blueprint(db_bp,     url_prefix="/bancos")
    app.register_blueprint(backup_bp, url_prefix="/backup")
    app.register_blueprint(monitoring_bp, url_prefix="/monitoring")
    app.register_blueprint(terminal_bp)
    app.register_blueprint(helpdesk_deploy_bp, url_prefix="/helpdesk-update")
    app.register_blueprint(rustdesk_bp, url_prefix="/rustdesk")
    app.register_blueprint(docker_bp, url_prefix="/docker")

    @app.route("/auth-check")
    def auth_check():
        """Endpoint usado pelo nginx auth_request para gatear /terminal-ws/."""
        if "user" in session:
            return make_response("", 200)
        return make_response("", 401)

    @app.route("/")
    def root():
        return redirect(url_for("dashboard.index"))

    import time as _time
    @app.context_processor
    def inject_globals():
        return {
            "APP_NAME": "ATLAS Portal",
            "DOMAIN": config.LDAP_DOMAIN,
            "now": lambda: int(_time.time()),
        }

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=8080, debug=False)
