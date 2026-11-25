"""Teacher account management by the administrator."""
from app.models import User, Course

NEW_TEACHER = {"full_name": "New Teacher", "email": "new.teacher@test.local",
               "password": "LongEnough1"}


def post_new_teacher(client, **overrides):
    data = dict(NEW_TEACHER)
    data.update(overrides)
    return client.post("/admin/teachers/add", data=data)


def conftest_teacher():
    """The active teacher created by conftest.py."""
    return User.query.filter_by(email="teacher@test.local").first()


def test_anonymous_user_is_redirected_from_teacher_pages(client):
    response = client.get("/admin/teachers")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_teacher_cannot_open_teacher_management(teacher_client):
    assert teacher_client.get("/admin/teachers").status_code == 403
    assert teacher_client.get("/admin/teachers/add").status_code == 403
    assert post_new_teacher(teacher_client).status_code == 403


def test_teacher_list_shows_teachers_but_not_admin_accounts(admin_client):
    response = admin_client.get("/admin/teachers")
    assert response.status_code == 200
    assert b"teacher@test.local" in response.data
    assert b"admin@test.local" not in response.data


def test_admin_can_add_a_teacher(admin_client):
    response = post_new_teacher(admin_client, email="  NEW.Teacher@Test.LOCAL ")
    assert response.status_code == 302
    teacher = User.query.filter_by(email="new.teacher@test.local").first()
    assert teacher is not None
    assert teacher.role == "teacher"
    assert teacher.is_active is True
    assert teacher.password_hash != "LongEnough1"
    assert teacher.check_password("LongEnough1")


def test_new_teacher_requires_a_password(admin_client):
    response = post_new_teacher(admin_client, password="")
    assert response.status_code == 200
    assert b"password is required" in response.data
    assert User.query.filter_by(email="new.teacher@test.local").first() is None


def test_short_password_is_rejected(admin_client):
    response = post_new_teacher(admin_client, password="short")
    assert response.status_code == 200
    assert b"at least 8" in response.data
    assert User.query.filter_by(email="new.teacher@test.local").first() is None


def test_duplicate_teacher_email_is_rejected(admin_client):
    response = post_new_teacher(admin_client, email="TEACHER@test.local")
    assert response.status_code == 200
    assert b"already exists" in response.data


def test_edit_with_blank_password_keeps_the_old_password(admin_client, fresh):
    teacher = conftest_teacher()
    pk = teacher.id
    data = {"full_name": "Renamed Teacher", "email": "teacher@test.local", "password": ""}
    response = admin_client.post(f"/admin/teachers/{pk}/edit", data=data)
    assert response.status_code == 302
    changed = fresh(User, pk)
    assert changed.full_name == "Renamed Teacher"
    assert changed.check_password("TeacherPass1")


def test_edit_with_new_password_changes_it(admin_client, fresh):
    pk = conftest_teacher().id
    data = {"full_name": "Test Teacher", "email": "teacher@test.local",
            "password": "BrandNewPass9"}
    admin_client.post(f"/admin/teachers/{pk}/edit", data=data)
    changed = fresh(User, pk)
    assert changed.check_password("BrandNewPass9")
    assert not changed.check_password("TeacherPass1")


def test_cannot_edit_a_teacher_to_use_an_existing_email(admin_client):
    pk = conftest_teacher().id
    data = {"full_name": "Test Teacher", "email": "admin@test.local", "password": ""}
    response = admin_client.post(f"/admin/teachers/{pk}/edit", data=data)
    assert response.status_code == 200
    assert b"already exists" in response.data


def test_admin_accounts_cannot_be_edited_or_toggled_here(admin_client):
    admin_pk = User.query.filter_by(email="admin@test.local").first().id
    assert admin_client.get(f"/admin/teachers/{admin_pk}/edit").status_code == 404
    assert admin_client.post(f"/admin/teachers/{admin_pk}/toggle").status_code == 404


def test_teacher_can_be_deactivated_and_reactivated(admin_client, fresh):
    pk = conftest_teacher().id
    admin_client.post(f"/admin/teachers/{pk}/toggle")
    assert fresh(User, pk).is_active is False
    admin_client.post(f"/admin/teachers/{pk}/toggle")
    assert fresh(User, pk).is_active is True


def test_deactivating_a_teacher_keeps_their_course(admin_client, build, fresh):
    teacher = build.teacher()
    course = build.course(teacher=teacher)
    teacher_pk, course_pk = teacher.id, course.id
    admin_client.post(f"/admin/teachers/{teacher_pk}/toggle")
    assert fresh(User, teacher_pk).is_active is False
    assert fresh(Course, course_pk).teacher_id == teacher_pk
