"""Shared report pages (student risk report, chart data) arrive in Milestone 3.

Both admins and teachers will use these, so the only rule here is "must be
logged in". Each report route must additionally check teacher/course access.
"""
from flask import Blueprint
from flask_login import current_user

from app import login_manager

bp = Blueprint("reports", __name__, url_prefix="/reports")


@bp.before_request
def login_required_for_reports():
    if not current_user.is_authenticated:
        return login_manager.unauthorized()
