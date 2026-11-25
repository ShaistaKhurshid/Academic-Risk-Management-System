"""Add the demo login accounts:  python seed.py

SYNTHETIC DATA FOR LOCAL DEMONSTRATION ONLY. These accounts and passwords are
public (they are written in the README), so never use them for real data.

Safe to run more than once: an account is only created if its email does not
exist yet, so nothing is duplicated and existing passwords are not changed.

Milestone 4 will extend this file with demo students, courses, attendance,
marks and assignments.
"""
from app import create_app, db
from app.models import User, ROLE_ADMIN, ROLE_TEACHER

# (full name, email, password, role)
DEMO_USERS = [
    ("Demo Admin", "admin@college.test", "Admin@123", ROLE_ADMIN),
    ("Dr. Asha Verma", "teacher1@college.test", "Teacher@123", ROLE_TEACHER),
    ("Prof. Rohan Mehta", "teacher2@college.test", "Teacher@123", ROLE_TEACHER),
    ("Dr. Neha Iyer", "teacher3@college.test", "Teacher@123", ROLE_TEACHER),
]


def seed_users():
    for full_name, email, password, role in DEMO_USERS:
        if User.query.filter_by(email=email).first() is not None:
            print("Already exists, skipped:", email)
            continue
        user = User(full_name=full_name, email=email, role=role)
        user.set_password(password)      # stores a hash, never the plain password
        db.session.add(user)
        print("Created:", email, f"({role})")
    db.session.commit()


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        db.create_all()      # harmless if tables already exist
        seed_users()
        print("Seeding finished.")
