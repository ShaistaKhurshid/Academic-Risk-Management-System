"""Student management: access control, add/edit validation, deletion rules."""
from app.models import Student, FollowUp

VALID = {"student_id": "S100", "name": "Asha Rao",
         "email": "asha@test.local", "semester": "Semester 3"}


def post_new_student(client, **overrides):
    data = dict(VALID)
    data.update(overrides)
    return client.post("/admin/students/add", data=data)


# ---- access control (enforced on the server) --------------------------------
def test_anonymous_user_is_redirected_from_student_pages(client):
    for url in ["/admin/students", "/admin/students/add"]:
        response = client.get(url)
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]


def test_teacher_gets_403_on_student_pages_and_cannot_add(teacher_client):
    assert teacher_client.get("/admin/students").status_code == 403
    assert teacher_client.get("/admin/students/add").status_code == 403
    assert post_new_student(teacher_client).status_code == 403
    assert Student.query.count() == 0


# ---- list and add -----------------------------------------------------------
def test_student_list_shows_students(admin_client, build):
    build.student(name="Visible Person")
    response = admin_client.get("/admin/students")
    assert response.status_code == 200
    assert b"Visible Person" in response.data


def test_admin_can_add_a_student(admin_client):
    response = post_new_student(admin_client)
    assert response.status_code == 302
    student = Student.query.one()
    assert student.student_id == "S100"
    assert student.name == "Asha Rao"
    assert student.semester == "Semester 3"


def test_added_student_email_is_normalised(admin_client):
    post_new_student(admin_client, email="  ASHA@Test.LOCAL  ")
    assert Student.query.one().email == "asha@test.local"


def test_duplicate_student_id_is_rejected(admin_client, build):
    build.student(student_id="S100")
    response = post_new_student(admin_client, email="other@test.local")
    assert response.status_code == 200
    assert b"already exists" in response.data
    assert Student.query.count() == 1


def test_duplicate_email_is_rejected_even_with_different_case(admin_client, build):
    build.student(email="asha@test.local")
    response = post_new_student(admin_client, student_id="S200", email="ASHA@TEST.LOCAL")
    assert response.status_code == 200
    assert b"already exists" in response.data
    assert Student.query.count() == 1


def test_invalid_email_is_rejected(admin_client):
    response = post_new_student(admin_client, email="not-an-email")
    assert response.status_code == 200
    assert b"valid email" in response.data
    assert Student.query.count() == 0


def test_missing_required_fields_are_rejected(admin_client):
    response = post_new_student(admin_client, name="   ")
    assert response.status_code == 200
    assert Student.query.count() == 0


def test_unknown_student_gives_404(admin_client):
    assert admin_client.get("/admin/students/9999").status_code == 404


def test_student_detail_shows_enrolled_course(admin_client, build):
    student, course = build.student(name="Detail Person"), build.course(code="CS777")
    build.enrol(student, course)
    response = admin_client.get(f"/admin/students/{student.id}")
    assert response.status_code == 200
    assert b"Detail Person" in response.data
    assert b"CS777" in response.data


# ---- edit -------------------------------------------------------------------
def test_admin_can_edit_a_student(admin_client, build, fresh):
    student = build.student()
    student_pk = student.id
    data = dict(VALID, name="New Name", email="  NEW@Test.Local ")
    response = admin_client.post(f"/admin/students/{student_pk}/edit", data=data)
    assert response.status_code == 302
    changed = fresh(Student, student_pk)
    assert changed.name == "New Name"
    assert changed.email == "new@test.local"
    assert changed.student_id == "S100"


def test_editing_without_changing_the_id_is_not_a_duplicate(admin_client, build):
    student = build.student(student_id="S100", email="asha@test.local")
    response = admin_client.post(f"/admin/students/{student.id}/edit", data=dict(VALID))
    assert response.status_code == 302


def test_cannot_edit_a_student_to_use_another_students_id(admin_client, build):
    build.student(student_id="S100")
    other = build.student(student_id="S200", email="s200@test.local")
    data = dict(VALID, student_id="S100", email="s200@test.local")
    response = admin_client.post(f"/admin/students/{other.id}/edit", data=data)
    assert response.status_code == 200
    assert b"already exists" in response.data


# ---- deletion rules ---------------------------------------------------------
def test_student_without_any_records_can_be_deleted(admin_client, build):
    student = build.student()
    response = admin_client.post(f"/admin/students/{student.id}/delete")
    assert response.status_code == 302
    assert Student.query.count() == 0


def test_student_with_an_enrolment_cannot_be_deleted(admin_client, build):
    student, course = build.student(), build.course()
    build.enrol(student, course)
    response = admin_client.post(f"/admin/students/{student.id}/delete",
                                 follow_redirects=True)
    assert b"Cannot delete" in response.data
    assert Student.query.count() == 1


def test_student_with_attendance_cannot_be_deleted(admin_client, build):
    student, course = build.student(), build.course()
    build.attendance(student, course)
    admin_client.post(f"/admin/students/{student.id}/delete")
    assert Student.query.count() == 1


def test_follow_up_history_is_preserved_when_delete_is_refused(admin_client, build):
    teacher = build.teacher()
    course = build.course(teacher=teacher)
    student = build.student()
    build.enrol(student, course)
    build.follow_up(student, course, teacher)

    response = admin_client.post(f"/admin/students/{student.id}/delete",
                                 follow_redirects=True)

    assert b"Cannot delete" in response.data
    assert Student.query.count() == 1
    assert FollowUp.query.count() == 1


def test_teacher_cannot_delete_a_student(teacher_client, build):
    student = build.student()
    assert teacher_client.post(f"/admin/students/{student.id}/delete").status_code == 403
    assert Student.query.count() == 1
