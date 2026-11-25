"""Milestone 2 decisions: email normalisation, permanent sessions, logout CSRF."""
import re
from datetime import timedelta

from app import db
from app.models import User, Student, normalize_email, ROLE_TEACHER


# ---- email normalisation ----------------------------------------------------
def test_normalize_email_strips_and_lowercases():
    assert normalize_email("  Mixed.Case@Example.COM  ") == "mixed.case@example.com"
    assert normalize_email(None) is None


def test_user_email_is_normalised_when_saved(app):
    user = User(full_name="X", email="  Teacher.X@College.TEST ", role=ROLE_TEACHER,
                password_hash="fake")
    db.session.add(user)
    db.session.commit()
    assert user.email == "teacher.x@college.test"


def test_student_email_is_normalised_when_saved(build):
    student = build.student(email="  ASHA@College.Test ")
    assert student.email == "asha@college.test"


def test_user_created_with_mixed_case_email_can_log_in(app, client):
    user = User(full_name="Mixed", email="Mixed.Case@Test.Local", role=ROLE_TEACHER)
    user.set_password("MixedPass123")
    db.session.add(user)
    db.session.commit()
    response = client.post("/login", data={"email": "MIXED.case@test.local ",
                                           "password": "MixedPass123"})
    assert response.status_code == 302


# ---- permanent (8 hour) sessions -------------------------------------------
def test_session_lifetime_is_eight_hours(app):
    assert app.permanent_session_lifetime == timedelta(hours=8)


def test_login_makes_the_session_permanent(client):
    client.post("/login", data={"email": "admin@test.local", "password": "AdminPass1"})
    with client.session_transaction() as sess:
        assert sess.permanent is True


def test_login_sets_an_expiring_cookie(client):
    response = client.post("/login", data={"email": "admin@test.local",
                                           "password": "AdminPass1"})
    cookies = response.headers.getlist("Set-Cookie")
    session_cookie = [c for c in cookies if c.startswith("session=")]
    assert session_cookie, "no session cookie was set"
    assert "Expires=" in session_cookie[0]
    assert "HttpOnly" in session_cookie[0]
    assert "SameSite=Lax" in session_cookie[0]


# ---- logout is CSRF protected ----------------------------------------------
def _csrf_token(client, url):
    html = client.get(url).get_data(as_text=True)
    match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert match, "no CSRF token found on " + url
    return match.group(1)


def test_logout_without_csrf_token_is_refused_and_user_stays_logged_in(csrf_app):
    client = csrf_app.test_client()
    token = _csrf_token(client, "/login")
    login = client.post("/login", data={"email": "csrf@test.local",
                                        "password": "CsrfPass123", "csrf_token": token})
    assert login.status_code == 302

    refused = client.post("/logout")                 # no token
    assert refused.status_code == 400

    still_in = client.get("/admin/dashboard")
    assert still_in.status_code == 200


def test_logout_with_csrf_token_works(csrf_app):
    client = csrf_app.test_client()
    token = _csrf_token(client, "/login")
    client.post("/login", data={"email": "csrf@test.local",
                                "password": "CsrfPass123", "csrf_token": token})

    page_token = _csrf_token(client, "/admin/dashboard")   # token from the logout form
    response = client.post("/logout", data={"csrf_token": page_token})
    assert response.status_code == 302

    after = client.get("/admin/dashboard")
    assert after.status_code == 302
    assert "/login" in after.headers["Location"]
