"""Application factory: builds and configures the Flask app."""
from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect, CSRFError

from config import Config
from app.security import SafeIntConverter, configure_security, register_security

# Extensions are created here, and connected to the app inside create_app().
db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()          # protects EVERY POST form automatically


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    # Phase 15: validate environment (SECRET_KEY / debug / cookie flags) and
    # limit <int:...> URL ids to what SQLite can store (oversized ids -> 404).
    configure_security(app)
    app.url_map.converters["int"] = SafeIntConverter
    register_security(app)

    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"            # where anonymous users are sent
    login_manager.login_message = "Please log in to continue."
    login_manager.login_message_category = "warning"
    login_manager.session_protection = "strong"

    # Import after the extensions exist (models and blueprints use them).
    from app import models  # noqa: F401  (registers the tables)
    from app import auth, admin, teacher, reports

    app.register_blueprint(auth.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(teacher.bp)
    app.register_blueprint(reports.bp)

    # Friendly error pages
    @app.errorhandler(403)
    def forbidden(error):
        return render_template(
            "error.html", code=403, title="Access denied",
            message="You do not have permission to open this page."), 403

    @app.errorhandler(404)
    def not_found(error):
        return render_template(
            "error.html", code=404, title="Page not found",
            message="The page you asked for does not exist."), 404

    @app.errorhandler(500)
    def server_error(error):
        # Undo any half-finished database work, then show a page that never
        # reveals technical details (Flask has already logged the real error).
        try:
            db.session.rollback()
        except Exception:  # pragma: no cover - the session itself is broken
            pass
        try:
            return render_template(
                "error.html", code=500, title="Something went wrong",
                message="The server could not complete your request. Please go "
                        "back and try again; if it keeps happening, tell your "
                        "administrator."), 500
        except Exception:  # pragma: no cover - last-resort page
            return ("<!doctype html><title>Something went wrong</title>"
                    "<h1>Something went wrong</h1>"
                    "<p>Please go back and try again.</p>"), 500

    @app.errorhandler(CSRFError)
    def csrf_failed(error):
        return render_template(
            "error.html", code=400, title="Form expired",
            message="Your form session expired or was invalid. "
                    "Go back, refresh the page and try again."), 400

    return app
