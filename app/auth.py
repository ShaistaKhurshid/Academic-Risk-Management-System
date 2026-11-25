"""Authentication: login, logout and the home redirect."""
from flask import Blueprint, render_template, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user

from app import db, login_manager
from app.forms import LoginForm
from app.models import User, ROLE_ADMIN

bp = Blueprint("auth", __name__)


@login_manager.user_loader
def load_user(user_id):
    """Flask-Login calls this on every request to turn the session's user id
    back into a User object. Deactivated users are treated as logged out."""
    user = db.session.get(User, int(user_id))
    if user is not None and user.is_active:
        return user
    return None


def dashboard_endpoint_for(user):
    """Which dashboard belongs to this user's role?"""
    if user.role == ROLE_ADMIN:
        return "admin.dashboard"
    return "teacher.dashboard"


@bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for(dashboard_endpoint_for(current_user)))
    return redirect(url_for("auth.login"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for(dashboard_endpoint_for(current_user)))

    form = LoginForm()
    if form.validate_on_submit():            # true only for a valid POST with a CSRF token
        email = form.email.data.strip().lower()
        user = User.query.filter_by(email=email).first()

        if user is not None and user.is_active and user.check_password(form.password.data):
            login_user(user)
            # Make this a PERMANENT session so the cookie really expires after
            # PERMANENT_SESSION_LIFETIME (8 hours, see config.py). Without this
            # line that setting is ignored.
            session.permanent = True
            return redirect(url_for(dashboard_endpoint_for(user)))

        # Same message for "unknown email" and "wrong password" on purpose,
        # so the page does not reveal which emails exist.
        flash("Invalid email or password.", "danger")

    return render_template("auth/login.html", form=form)


@bp.route("/logout", methods=["POST"])       # POST + CSRF token, so a stray link cannot log you out
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
