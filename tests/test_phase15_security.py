"""Phase 15 regression tests: oversized URL ids, friendly 500 page, environment-aware
SECRET_KEY / debug / cookie settings, and security headers (incl. CSP)."""
import re
from pathlib import Path

import pytest

from app import create_app, db
from app.models import User, ROLE_ADMIN, ROLE_TEACHER
from app.security import (SQLITE_MAX_INT, build_csp, debug_allowed,
                          environment_name)
from config import TestConfig

STRONG_KEY = "k" * 40
TEMPLATES = Path(__file__).resolve().parent.parent / "app" / "templates"
STATIC = Path(__file__).resolve().parent.parent / "app" / "static"


def make_config(**overrides):
    attrs = dict(TESTING=False, APP_ENV="production", SECRET_KEY=STRONG_KEY)
    attrs.update(overrides)
    return type("Phase15Config", (TestConfig,), attrs)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    """The developer's own environment variables must not change these tests."""
    for name in ("APP_ENV", "FLASK_DEBUG", "SESSION_COOKIE_SECURE", "SECRET_KEY"):
        monkeypatch.delenv(name, raising=False)


# ---------------------------------------------------------------- F-01 ids
HUGE = "99999999999999999999999"
OVER = str(SQLITE_MAX_INT + 1)


@pytest.mark.parametrize("path", [
    "/teacher/courses/{n}/risk-report",
    "/teacher/courses/{n}/risk-report/export.pdf",
    "/teacher/courses/{n}/risk-report/export.xlsx",
    "/teacher/courses/{n}/attendance",
    "/teacher/courses/{n}/students/1/risk",
    "/teacher/courses/1/students/{n}/risk",
    "/teacher/assessments/{n}/marks",
    "/teacher/assignments/{n}/submissions",
])
@pytest.mark.parametrize("number", [HUGE, OVER, str(SQLITE_MAX_INT)])
def test_oversized_ids_give_404_for_teacher_routes(teacher_client, path, number):
    assert teacher_client.get(path.format(n=number)).status_code == 404


@pytest.mark.parametrize("path", [
    "/admin/students/{n}", "/admin/students/{n}/edit", "/admin/teachers/{n}/edit",
    "/admin/courses/{n}/edit", "/admin/courses/{n}/enrol",
])
@pytest.mark.parametrize("number", [HUGE, OVER])
def test_oversized_ids_give_404_for_admin_routes(admin_client, path, number):
    assert admin_client.get(path.format(n=number)).status_code == 404


def test_oversized_id_on_post_routes_gives_404_not_500(admin_client):
    assert admin_client.post(f"/admin/students/{HUGE}/delete").status_code == 404
    assert admin_client.post(f"/admin/courses/{HUGE}/delete").status_code == 404


def test_oversized_id_is_404_before_login_check_does_not_leak(client):
    # An anonymous visitor still gets the normal result (not a crash).
    assert client.get(f"/teacher/courses/{HUGE}/risk-report").status_code == 404


def test_normal_ids_and_url_building_still_work(app, admin_client, build):
    student = build.student()
    assert admin_client.get(f"/admin/students/{student.id}").status_code == 200
    with app.test_request_context():
        from flask import url_for
        assert url_for("admin.student_detail", student_id=student.id) == f"/admin/students/{student.id}"


def test_negative_and_non_numeric_ids_are_still_404(admin_client):
    assert admin_client.get("/admin/students/-1").status_code == 404
    assert admin_client.get("/admin/students/abc").status_code == 404


# ------------------------------------------------------- F-01/F-14 500 page
def make_crashing_app():
    app = create_app(type("Crash", (TestConfig,), {"PROPAGATE_EXCEPTIONS": False}))

    @app.route("/_boom")
    def boom():
        raise RuntimeError("super-secret-internal-detail")

    return app


def test_unhandled_error_shows_friendly_500_page():
    app = make_crashing_app()
    with app.app_context():
        db.create_all()
        response = app.test_client().get("/_boom")
        text = response.get_data(as_text=True)
        assert response.status_code == 500
        assert "Something went wrong" in text
        assert "Go to login" in text           # same friendly layout as 403/404
        db.drop_all()


def test_500_page_never_leaks_details():
    app = make_crashing_app()
    with app.app_context():
        db.create_all()
        text = app.test_client().get("/_boom").get_data(as_text=True)
        for secret in ("super-secret-internal-detail", "Traceback", "RuntimeError",
                       "sqlalchemy", ".py"):
            assert secret not in text
        db.drop_all()


def test_500_page_rolls_back_the_database_session():
    app = make_crashing_app()

    @app.route("/_dirty")
    def dirty():
        db.session.add(User(full_name="Ghost", email="ghost@test.local",
                            role=ROLE_TEACHER, password_hash="x"))
        db.session.flush()
        raise RuntimeError("fail after flush")

    with app.app_context():
        db.create_all()
        assert app.test_client().get("/_dirty").status_code == 500
        assert User.query.filter_by(email="ghost@test.local").count() == 0
        db.drop_all()


def test_500_page_has_security_headers():
    app = make_crashing_app()
    with app.app_context():
        db.create_all()
        response = app.test_client().get("/_boom")
        assert response.headers["X-Frame-Options"] == "DENY"
        assert "Content-Security-Policy" in response.headers
        db.drop_all()


def test_existing_403_and_404_pages_unchanged(client, teacher_client):
    assert client.get("/no-such-page").status_code == 404
    assert "Page not found" in client.get("/no-such-page").get_data(as_text=True)
    assert teacher_client.get("/admin/dashboard").status_code == 403


# ----------------------------------------------------- F-07 SECRET_KEY rules
@pytest.mark.parametrize("key", ["", "dev-only-change-me", "change-me", "short-key", "x" * 31])
def test_production_refuses_missing_default_or_short_secret_key(key):
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app(make_config(SECRET_KEY=key))


def test_production_refuses_when_secret_key_is_none():
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app(make_config(SECRET_KEY=None))


def test_production_starts_with_strong_secret_key():
    app = create_app(make_config())
    assert app.config["SECRET_KEY"] == STRONG_KEY
    assert app.config["DEBUG"] is False


def test_unknown_environment_name_is_treated_as_production():
    for name in ("production", "prod", "prodution", "staging", "PRODUCTION"):
        assert environment_name({"APP_ENV": name}) == "production"
        with pytest.raises(RuntimeError):
            create_app(make_config(APP_ENV=name, SECRET_KEY="dev-only-change-me"))


def test_development_still_allows_default_key_with_warning(caplog):
    app = create_app(make_config(APP_ENV="development", SECRET_KEY="dev-only-change-me"))
    assert app.config["APP_ENV_RESOLVED"] == "development"
    assert any("development SECRET_KEY" in r.getMessage() for r in caplog.records)


def test_environment_is_read_from_APP_ENV_variable(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    cfg = type("NoEnvInConfig", (TestConfig,), {"TESTING": False, "APP_ENV": None,
                                                "SECRET_KEY": "dev-only-change-me"})
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app(cfg)


def test_default_environment_is_development():
    assert environment_name({}) == "development"
    assert create_app(TestConfig).config["APP_ENV_RESOLVED"] == "testing"


def test_testing_config_is_not_affected_by_developer_APP_ENV(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    assert create_app(TestConfig).config["APP_ENV_RESOLVED"] == "testing"


# --------------------------------------------------------------- F-06 debug
def test_production_refuses_debug_in_config():
    with pytest.raises(RuntimeError, match="debug"):
        create_app(make_config(DEBUG=True))


def test_production_refuses_FLASK_DEBUG_variable(monkeypatch):
    monkeypatch.setenv("FLASK_DEBUG", "1")
    with pytest.raises(RuntimeError, match="debug"):
        create_app(make_config())


def test_debug_allowed_only_in_development(monkeypatch):
    dev = create_app(make_config(APP_ENV="development"))
    prod = create_app(make_config())
    assert debug_allowed(dev) is True            # unchanged local-demo behaviour
    assert debug_allowed(prod) is False
    monkeypatch.setenv("FLASK_DEBUG", "0")
    assert debug_allowed(dev) is False           # developer can still switch it off


def test_run_py_uses_debug_allowed_and_not_hardcoded_true():
    source = (Path(__file__).resolve().parent.parent / "run.py").read_text()
    assert "debug=True" not in source
    assert "app.run(debug=debug_allowed(app))" in source


# ------------------------------------------------------ F-09 cookie Secure
def login_cookie(config):
    app = create_app(config)
    with app.app_context():
        db.create_all()
        user = User(full_name="Cookie Admin", email="cookie@test.local", role=ROLE_ADMIN)
        user.set_password("CookiePass123")
        db.session.add(user)
        db.session.commit()
        response = app.test_client().post(
            "/login", data={"email": "cookie@test.local", "password": "CookiePass123"})
        assert response.status_code == 302
        cookie = response.headers.get("Set-Cookie", "")
        db.session.remove()
        db.drop_all()
    return cookie


def test_production_session_cookie_is_secure_httponly_samesite():
    cookie = login_cookie(make_config())
    assert "Secure" in cookie and "HttpOnly" in cookie and "SameSite=Lax" in cookie


def test_development_session_cookie_is_not_secure_so_http_demo_works():
    cookie = login_cookie(make_config(APP_ENV="development"))
    assert "Secure" not in cookie and "HttpOnly" in cookie


def test_cookie_secure_can_be_turned_off_explicitly_in_production(monkeypatch):
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    assert "Secure" not in login_cookie(make_config())


def test_cookie_secure_can_be_turned_on_in_development(monkeypatch):
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "true")
    assert "Secure" in login_cookie(make_config(APP_ENV="development"))


# ------------------------------------------------------- F-10 headers / CSP
def test_security_headers_present_on_pages_redirects_and_static(client):
    for response in (client.get("/login"), client.get("/"), client.get("/missing"),
                     client.get("/static/css/style.css")):
        h = response.headers
        assert h["X-Content-Type-Options"] == "nosniff"
        assert h["X-Frame-Options"] == "DENY"
        assert h["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert "camera=()" in h["Permissions-Policy"]
        assert "Content-Security-Policy" in h


def test_csp_is_strict_for_scripts_and_allows_only_the_needed_cdn(client):
    csp = client.get("/login").headers["Content-Security-Policy"]
    directives = {d.split()[0]: d for d in csp.split("; ")}
    script = directives["script-src"]
    assert "'unsafe-inline'" not in script and "'unsafe-eval'" not in script
    assert "https://cdn.jsdelivr.net" in script and "'self'" in script
    assert re.search(r"'nonce-[\w-]{16,}'", script)
    assert directives["object-src"] == "object-src 'none'"
    assert directives["frame-ancestors"] == "frame-ancestors 'none'"
    assert directives["base-uri"] == "base-uri 'self'"
    assert directives["form-action"] == "form-action 'self'"
    assert directives["default-src"] == "default-src 'self'"
    assert "*" not in csp.replace("'self'", "")


def test_csp_nonce_is_different_for_every_request(client):
    nonces = {re.search(r"nonce-([\w-]+)", client.get("/login").headers["Content-Security-Policy"]).group(1)
              for _ in range(5)}
    assert len(nonces) == 5


def test_every_external_host_used_by_templates_is_allowed_by_csp():
    csp = build_csp("x")
    hosts = set()
    for path in TEMPLATES.rglob("*.html"):
        hosts |= set(re.findall(r"https://([\w.-]+)/", path.read_text(encoding="utf-8")))
    assert hosts, "expected the CDN links to be found"
    for host in hosts:
        assert "https://" + host in csp, host


def test_no_template_has_inline_event_handlers():
    pattern = re.compile(r"\son[a-z]+\s*=", re.I)
    for path in TEMPLATES.rglob("*.html"):
        assert not pattern.search(path.read_text(encoding="utf-8")), path.name


def test_every_inline_script_template_tag_has_a_nonce():
    for path in TEMPLATES.rglob("*.html"):
        for tag in re.findall(r"<script\b[^>]*>", path.read_text(encoding="utf-8")):
            if "src=" in tag:
                continue
            assert 'nonce="{{ csp_nonce }}"' in tag, (path.name, tag)


def test_rendered_inline_scripts_carry_the_request_nonce(teacher_client, build):
    teacher = build.teacher()
    from app.models import User as U
    owner = U.query.filter_by(email="teacher@test.local").one()
    course = build.course(teacher=owner)
    student = build.student()
    build.enrol(student, course)
    build.attendance(student, course)
    for url in (f"/teacher/courses/{course.id}/risk-report",
                f"/teacher/courses/{course.id}/students/{student.id}/risk"):
        response = teacher_client.get(url)
        assert response.status_code == 200
        nonce = re.search(r"nonce-([\w-]+)", response.headers["Content-Security-Policy"]).group(1)
        html = response.get_data(as_text=True)
        inline = [t for t in re.findall(r"<script\b[^>]*>", html) if "src=" not in t]
        assert inline, url
        assert all(f'nonce="{nonce}"' in t for t in inline), (url, inline)


def test_confirm_dialogs_use_data_confirm_and_script_is_served(client):
    expected = {
        "admin/student_detail.html": "Delete this student permanently?",
        "admin/course_enrol.html": "Remove this student from the course?",
        "admin/courses.html": "Delete this course? Only courses with no records can be deleted.",
        "teacher/risk_report.html": "Record a risk assessment snapshot for every enrolled student?",
    }
    for name, message in expected.items():
        assert f'data-confirm="{message}' in (TEMPLATES / name).read_text(encoding="utf-8"), name
    response = client.get("/static/js/confirm.js")
    assert response.status_code == 200 and b"data-confirm" in response.data
    assert "confirm.js" in client.get("/login").get_data(as_text=True)


def test_confirm_script_cancel_stops_submission_before_other_handlers():
    js = (STATIC / "js" / "confirm.js").read_text()
    assert "addEventListener(\"submit\"" in js and "}, true)" in js    # capture phase
    assert "preventDefault()" in js and "stopPropagation()" in js


def test_hsts_only_on_https_in_production():
    prod = create_app(make_config())
    dev = create_app(make_config(APP_ENV="development"))
    assert "Strict-Transport-Security" in prod.test_client().get(
        "/login", base_url="https://localhost").headers
    assert "Strict-Transport-Security" not in prod.test_client().get("/login").headers
    assert "Strict-Transport-Security" not in dev.test_client().get(
        "/login", base_url="https://localhost").headers
