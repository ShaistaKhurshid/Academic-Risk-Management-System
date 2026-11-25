"""Configuration for the Academic Risk & Student Performance Intelligence System."""
import os
from datetime import timedelta


class Config:
    # Used to sign the session cookie and CSRF tokens.
    # For local demonstration the fallback is fine (APP_ENV unset = development).
    # In production (APP_ENV=production) the app refuses to start unless a long
    # random SECRET_KEY environment variable (32+ characters) is set. See
    # app/security.py and docs/PHASE15_SECURITY.md.
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")

    # A relative sqlite path is created inside the "instance" folder
    # (instance/academic_risk.db). That folder is ignored by Git.
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///academic_risk.db")

    # Session cookie safety
    SESSION_COOKIE_HTTPONLY = True      # JavaScript cannot read the cookie
    SESSION_COOKIE_SAMESITE = "Lax"     # extra protection against cross-site requests
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    # SESSION_COOKIE_SECURE is off for local HTTP use. In production it is switched
    # on automatically (override with the SESSION_COOKIE_SECURE environment variable).


class TestConfig(Config):
    """Used by pytest: throw-away in-memory database, CSRF off for easy form posts."""
    TESTING = True
    APP_ENV = "testing"   # pinned so a developer's APP_ENV variable cannot affect the tests
    SECRET_KEY = "test-secret-key"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
