"""Environment-aware security settings (Phase 15).

Two modes, chosen by the APP_ENV environment variable:

  development (default)  - local demonstration. Behaves exactly as before:
                           debug allowed, fallback SECRET_KEY allowed (with a warning).
  anything else          - treated as PRODUCTION (fail-safe: a typo such as
                           "prodution" is strict, not lax). In production:
                             * the application REFUSES to start with a missing,
                               default or too-short SECRET_KEY;
                             * the application REFUSES to start with debug enabled;
                             * the session cookie is Secure (HTTPS only) unless
                               SESSION_COOKIE_SECURE=false is set explicitly;
                             * HSTS is sent on HTTPS responses.

Security headers (CSP, X-Frame-Options, ...) are added in every mode.
"""
import os
import secrets

from flask import g, request
from werkzeug.routing import IntegerConverter

DEFAULT_SECRET_KEYS = {"", "dev-only-change-me", "change-me", "secret", "changeme"}
MIN_SECRET_KEY_LENGTH = 32
# Largest value SQLite can store in an INTEGER column. Anything bigger can never
# be a real record id, so such URLs are answered with 404 instead of a server error.
SQLITE_MAX_INT = 2 ** 63 - 1

_FALSE = {"0", "false", "no", "off"}
_TRUE = {"1", "true", "yes", "on"}


class SafeIntConverter(IntegerConverter):
    """The <int:...> URL converter, limited to the range SQLite can store."""

    def __init__(self, map, fixed_digits=0, min=None, max=None, signed=False):
        super().__init__(map, fixed_digits, min,
                         SQLITE_MAX_INT if max is None else max, signed)


def environment_name(config=None):
    """'development', 'testing' or 'production' (anything unknown counts as production)."""
    value = None
    if config is not None:
        value = config.get("APP_ENV")
    if not value:
        value = os.environ.get("APP_ENV", "development")
    value = str(value).strip().lower()
    if value in ("", "development", "dev", "local"):
        return "development"
    if value == "testing":
        return "testing"
    return "production"


def env_flag(name, default):
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    value = value.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    return default


def is_production(app):
    return app.config.get("APP_ENV_RESOLVED") == "production"


def debug_allowed(app):
    """Used by run.py: debug only in development, and not when FLASK_DEBUG=0."""
    return (app.config.get("APP_ENV_RESOLVED") == "development"
            and env_flag("FLASK_DEBUG", True))


def configure_security(app):
    """Apply and validate the environment-specific settings. Raises RuntimeError
    when a production configuration is unsafe, so the app never starts that way."""
    env = environment_name(app.config)
    app.config["APP_ENV_RESOLVED"] = env

    if env == "production":
        key = app.config.get("SECRET_KEY") or ""
        if key in DEFAULT_SECRET_KEYS or len(key) < MIN_SECRET_KEY_LENGTH:
            raise RuntimeError(
                "Refusing to start in production: SECRET_KEY is missing, is the "
                "built-in default, or is shorter than %d characters. Set a long "
                "random SECRET_KEY environment variable (for example: "
                "python -c \"import secrets; print(secrets.token_hex(32))\")."
                % MIN_SECRET_KEY_LENGTH)
        if app.config.get("DEBUG") or env_flag("FLASK_DEBUG", False):
            raise RuntimeError(
                "Refusing to start in production: debug mode is enabled "
                "(DEBUG / FLASK_DEBUG). Debug mode exposes an interactive "
                "console and must never run on a public server.")
        app.config["DEBUG"] = False
        # HTTPS-only session cookie unless the operator explicitly opts out.
        app.config["SESSION_COOKIE_SECURE"] = env_flag("SESSION_COOKIE_SECURE", True)
    else:
        # Development / testing: cookie stays HTTP-friendly unless asked otherwise.
        if "SESSION_COOKIE_SECURE" in os.environ:
            app.config["SESSION_COOKIE_SECURE"] = env_flag(
                "SESSION_COOKIE_SECURE", app.config.get("SESSION_COOKIE_SECURE", False))
        if env == "development" and (app.config.get("SECRET_KEY") or "") in DEFAULT_SECRET_KEYS:
            app.logger.warning(
                "Using the built-in development SECRET_KEY. This is fine for a local "
                "demonstration only; set SECRET_KEY before any real deployment.")


def build_csp(nonce):
    """Content-Security-Policy that fits how the pages are built.

    * Scripts: our own files, the two jsDelivr libraries (Bootstrap, Chart.js)
      and inline scripts that carry this request's nonce. Inline event-handler
      attributes are NOT allowed (the confirm dialogs use data-confirm instead).
    * Styles: 'unsafe-inline' is kept because a few templates use style="..."
      for widths and colours; scripts are the high-risk part and stay strict.
    """
    cdn = "https://cdn.jsdelivr.net"
    return "; ".join([
        "default-src 'self'",
        f"script-src 'self' {cdn} 'nonce-{nonce}'",
        f"style-src 'self' {cdn} 'unsafe-inline'",
        "img-src 'self' data:",
        f"font-src 'self' {cdn} data:",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ])


def register_security(app):
    """Wire the URL converter, nonce, template variable and response headers."""

    @app.before_request
    def _make_csp_nonce():
        g.csp_nonce = secrets.token_urlsafe(16)

    @app.context_processor
    def _inject_csp_nonce():
        return {"csp_nonce": getattr(g, "csp_nonce", "")}

    @app.after_request
    def _security_headers(response):
        headers = response.headers
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        headers.setdefault("Permissions-Policy",
                           "camera=(), microphone=(), geolocation=(), payment=()")
        headers.setdefault("Content-Security-Policy",
                           build_csp(getattr(g, "csp_nonce", "")))
        if is_production(app) and request.is_secure:
            headers.setdefault("Strict-Transport-Security",
                               "max-age=31536000; includeSubDomains")
        return response
