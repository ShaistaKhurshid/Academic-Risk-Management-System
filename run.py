"""Start the development server:  python run.py"""
import sys

from app import create_app, db
from app.security import debug_allowed

app = create_app()


def risk_history_table_exists():
    """True when the Phase 12 table is in the database (see migrate_risk_snapshots.py)."""
    from sqlalchemy import inspect
    with app.app_context():
        return inspect(db.engine).has_table("risk_snapshots")


if __name__ == "__main__":
    # Phase 12 added a table. If an existing database has not been migrated yet,
    # stop with a clear message instead of showing server errors on some pages.
    if not risk_history_table_exists():
        print("\nThe database is missing the 'risk_snapshots' table (Phase 12).")
        print("Stop here and run this ONCE, then start the server again:\n")
        print("    python migrate_risk_snapshots.py\n")
        print("It makes a backup first and does not change your existing data.")
        sys.exit(1)

    # Debug mode (helpful error pages, auto-reload) is on ONLY in the default
    # development mode, exactly as before. In production (APP_ENV=production)
    # it is always off, and create_app() refuses to start if debug is forced on.
    # For a real server use a production WSGI server instead of this script.
    app.run(debug=debug_allowed(app))
