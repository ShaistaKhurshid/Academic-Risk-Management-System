"""Tests for login, logout, role-based access and CSRF protection."""
from app import create_app
from app.models import User
from config import TestConfig


def log_in(client, email, password):
    return client.post("/login", data={"email": email, "password": password})


def test_login_page_loads(client):
    assert client.get("/login").status_code == 200


def test_admin_login_goes_to_admin_dashboard(client):
    response = log_in(client, "admin@test.local", "AdminPass1")
    assert response.status_code == 302
    assert "/admin/dashboard" in response.headers["Location"]


def test_teacher_login_goes_to_teacher_dashboard(client):
    response = log_in(client, "teacher@test.local", "TeacherPass1")
    assert response.status_code == 302
    assert "/teacher/dashboard" in response.headers["Location"]


def test_email_is_not_case_sensitive(client):
    response = log_in(client, "  ADMIN@Test.Local ", "AdminPass1")
    assert response.status_code == 302


def test_wrong_password_is_rejected(client):
    response = log_in(client, "admin@test.local", "wrong-password")
    assert response.status_code == 200
    assert b"Invalid email or password" in response.data


def test_unknown_email_gets_same_message(client):
    response = log_in(client, "nobody@test.local", "whatever")
    assert response.status_code == 200
    assert b"Invalid email or password" in response.data


def test_inactive_user_cannot_log_in(client):
    response = log_in(client, "old@test.local", "OldPass1")
    assert response.status_code == 200
    assert b"Invalid email or password" in response.data


def test_anonymous_user_is_sent_to_login(client):
    for url in ["/admin/dashboard", "/teacher/dashboard"]:
        response = client.get(url)
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]


def test_teacher_cannot_open_admin_pages(client):
    log_in(client, "teacher@test.local", "TeacherPass1")
    assert client.get("/admin/dashboard").status_code == 403


def test_admin_cannot_open_teacher_pages(client):
    log_in(client, "admin@test.local", "AdminPass1")
    assert client.get("/teacher/dashboard").status_code == 403


def test_logged_in_user_sees_own_dashboard(client):
    log_in(client, "teacher@test.local", "TeacherPass1")
    response = client.get("/teacher/dashboard")
    assert response.status_code == 200
    assert b"Teacher Dashboard" in response.data


def test_logout_ends_the_session(client):
    log_in(client, "admin@test.local", "AdminPass1")
    response = client.post("/logout")
    assert response.status_code == 302
    after = client.get("/admin/dashboard")
    assert after.status_code == 302
    assert "/login" in after.headers["Location"]


def test_logout_rejects_get_requests(client):
    log_in(client, "admin@test.local", "AdminPass1")
    assert client.get("/logout").status_code == 405


def test_password_is_stored_hashed(app):
    user = User.query.filter_by(email="admin@test.local").first()
    assert user.password_hash != "AdminPass1"
    assert user.check_password("AdminPass1")
    assert not user.check_password("not-the-password")


def test_login_without_csrf_token_is_rejected():
    """With CSRF switched ON, a POST that has no token must be refused."""
    class CsrfOnConfig(TestConfig):
        WTF_CSRF_ENABLED = True

    app = create_app(CsrfOnConfig)
    client = app.test_client()
    response = client.post("/login", data={"email": "a@b.c", "password": "x"})
    assert response.status_code == 400
