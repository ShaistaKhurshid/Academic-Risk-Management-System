"""Create the database tables:  python init_db.py

Safe to run more than once: existing tables and data are left untouched.
Note: create_all() does NOT change a table that already exists. If you edit
models.py during development, delete instance/academic_risk.db and run
init_db.py and seed.py again.
"""
from app import create_app, db

app = create_app()

with app.app_context():
    db.create_all()
    print("Database ready:", db.engine.url.database)
    print("Tables:", ", ".join(sorted(db.metadata.tables)))
