"""seed.py must be safe to run many times."""
from app import db
from app.models import User
from seed import seed_users, DEMO_USERS


def test_seed_creates_each_demo_account_once(app):
    before = User.query.count()
    seed_users()
    assert User.query.count() == before + len(DEMO_USERS)

    seed_users()                       # run again: nothing may be duplicated
    seed_users()
    assert User.query.count() == before + len(DEMO_USERS)


def test_seeded_accounts_have_correct_role_and_hashed_password(app):
    seed_users()
    for full_name, email, password, role in DEMO_USERS:
        user = User.query.filter_by(email=email).first()
        assert user is not None, email
        assert user.role == role
        assert user.password_hash != password       # never plain text
        assert user.check_password(password)


def test_seed_does_not_overwrite_an_existing_password(app):
    seed_users()
    admin = User.query.filter_by(email="admin@college.test").first()
    admin.set_password("ChangedPass123")
    db.session.commit()

    seed_users()                       # must NOT reset the changed password

    admin = User.query.filter_by(email="admin@college.test").first()
    assert admin.check_password("ChangedPass123")
    assert not admin.check_password("Admin@123")
