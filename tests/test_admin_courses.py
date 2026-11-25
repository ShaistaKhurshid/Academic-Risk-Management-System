"""Course management, teacher assignment and enrolment (admin side)."""
import pytest

from app.models import Course, Enrolment, User


def conftest_teacher():
    """The active teacher created by conftest.py."""
    return User.query.filter_by(email="teacher@test.local").first()


def conftest_inactive_teacher():
    """The INACTIVE teacher created by conftest.py."""
    return User.query.filter_by(email="old@test.local").first()


def post_new_course(client, **overrides):
    data = {"code": "CS201", "name": "Data Structures", "teacher_id": "0"}
    data.update(overrides)
    return client.post("/admin/courses/add", data=data)


# ---- access control ---------------------------------------------------------
def test_anonymous_user_is_redirected_from_course_pages(client):
    response = client.get("/admin/courses")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_teacher_cannot_use_course_or_enrolment_pages(teacher_client, build):
    course, student = build.course(), build.student()
    assert teacher_client.get("/admin/courses").status_code == 403
    assert teacher_client.get("/admin/courses/add").status_code == 403
    assert post_new_course(teacher_client).status_code == 403
    assert teacher_client.get(f"/admin/courses/{course.id}/enrol").status_code == 403
    response = teacher_client.post(f"/admin/courses/{course.id}/enrol",
                                   data={"student_ids": [str(student.id)]})
    assert response.status_code == 403
    assert Enrolment.query.count() == 0
    assert Course.query.count() == 1


# ---- add / list -------------------------------------------------------------
def test_course_list_shows_course_and_its_teacher(admin_client, build):
    teacher = build.teacher(full_name="Dr. Listed Teacher")
    build.course(teacher=teacher, code="CS555", name="Shown Course")
    response = admin_client.get("/admin/courses")
    assert response.status_code == 200
    assert b"CS555" in response.data
    assert b"Dr. Listed Teacher" in response.data


def test_admin_can_create_a_course_with_a_teacher(admin_client):
    teacher = conftest_teacher()
    response = post_new_course(admin_client, teacher_id=str(teacher.id))
    assert response.status_code == 302
    course = Course.query.one()
    assert course.code == "CS201"
    assert course.teacher_id == teacher.id


def test_course_can_be_created_without_a_teacher(admin_client):
    post_new_course(admin_client, teacher_id="0")
    assert Course.query.one().teacher_id is None


def test_duplicate_course_code_is_rejected(admin_client, build):
    build.course(code="CS201")
    response = post_new_course(admin_client)
    assert response.status_code == 200
    assert b"already exists" in response.data
    assert Course.query.count() == 1


def test_missing_course_name_is_rejected(admin_client):
    response = post_new_course(admin_client, name="")
    assert response.status_code == 200
    assert Course.query.count() == 0


# ---- teacher assignment rules ----------------------------------------------
def test_inactive_teacher_cannot_be_newly_assigned(admin_client):
    inactive = conftest_inactive_teacher()
    response = post_new_course(admin_client, teacher_id=str(inactive.id))
    assert response.status_code == 200
    assert b"active teacher" in response.data
    assert Course.query.count() == 0


def test_an_administrator_cannot_be_assigned_as_course_teacher(admin_client):
    admin_pk = User.query.filter_by(email="admin@test.local").first().id
    response = post_new_course(admin_client, teacher_id=str(admin_pk))
    assert response.status_code == 200          # not a valid choice
    assert Course.query.count() == 0


def test_unknown_teacher_id_is_rejected(admin_client):
    response = post_new_course(admin_client, teacher_id="99999")
    assert response.status_code == 200
    assert Course.query.count() == 0


def test_admin_can_edit_course_and_change_teacher(admin_client, build, fresh):
    old_teacher, new_teacher = build.teacher(), build.teacher()
    course = build.course(teacher=old_teacher)
    course_pk = course.id
    data = {"code": "CS999", "name": "Renamed", "teacher_id": str(new_teacher.id)}
    response = admin_client.post(f"/admin/courses/{course_pk}/edit", data=data)
    assert response.status_code == 302
    changed = fresh(Course, course_pk)
    assert changed.code == "CS999"
    assert changed.name == "Renamed"
    assert changed.teacher_id == new_teacher.id


def test_admin_can_unassign_the_teacher(admin_client, build, fresh):
    teacher = build.teacher()
    course = build.course(teacher=teacher)
    course_pk = course.id
    data = {"code": course.code, "name": course.name, "teacher_id": "0"}
    admin_client.post(f"/admin/courses/{course_pk}/edit", data=data)
    assert fresh(Course, course_pk).teacher_id is None


def test_editing_keeps_an_already_assigned_inactive_teacher(admin_client, build, fresh):
    inactive = conftest_inactive_teacher()
    course = build.course(teacher=inactive)
    course_pk, inactive_pk = course.id, inactive.id
    data = {"code": course.code, "name": "Only The Name Changed",
            "teacher_id": str(inactive_pk)}
    response = admin_client.post(f"/admin/courses/{course_pk}/edit", data=data)
    assert response.status_code == 302
    changed = fresh(Course, course_pk)
    assert changed.name == "Only The Name Changed"
    assert changed.teacher_id == inactive_pk


def test_cannot_switch_a_course_to_an_inactive_teacher(admin_client, build, fresh):
    teacher = build.teacher()
    course = build.course(teacher=teacher)
    course_pk, teacher_pk = course.id, teacher.id
    inactive = conftest_inactive_teacher()
    data = {"code": course.code, "name": course.name, "teacher_id": str(inactive.id)}
    response = admin_client.post(f"/admin/courses/{course_pk}/edit", data=data)
    assert response.status_code == 200
    assert fresh(Course, course_pk).teacher_id == teacher_pk


# ---- course deletion rules --------------------------------------------------
def test_empty_course_can_be_deleted_even_if_it_has_a_teacher(admin_client, build):
    course = build.course(teacher=build.teacher())
    response = admin_client.post(f"/admin/courses/{course.id}/delete")
    assert response.status_code == 302
    assert Course.query.count() == 0


def test_course_with_enrolments_cannot_be_deleted(admin_client, build):
    course, student = build.course(), build.student()
    build.enrol(student, course)
    response = admin_client.post(f"/admin/courses/{course.id}/delete",
                                 follow_redirects=True)
    assert b"Cannot delete" in response.data
    assert Course.query.count() == 1


@pytest.mark.parametrize("kind", ["assessment", "assignment", "follow_up"])
def test_course_with_dependent_records_cannot_be_deleted(admin_client, build, kind):
    teacher = build.teacher()
    course = build.course(teacher=teacher)
    student = build.student()
    if kind == "assessment":
        build.assessment(course)
    elif kind == "assignment":
        build.assignment(course)
    else:
        build.follow_up(student, course, teacher)
    admin_client.post(f"/admin/courses/{course.id}/delete")
    assert Course.query.count() == 1


def test_teacher_cannot_delete_a_course(teacher_client, build):
    course = build.course()
    assert teacher_client.post(f"/admin/courses/{course.id}/delete").status_code == 403
    assert Course.query.count() == 1


# ---- enrolment --------------------------------------------------------------
def test_enrolment_page_lists_available_students(admin_client, build):
    course = build.course(code="CS300")
    build.student(name="Available Person")
    response = admin_client.get(f"/admin/courses/{course.id}/enrol")
    assert response.status_code == 200
    assert b"CS300" in response.data
    assert b"Available Person" in response.data


def test_admin_can_enrol_several_students_at_once(admin_client, build):
    course = build.course()
    first, second = build.student(), build.student()
    response = admin_client.post(f"/admin/courses/{course.id}/enrol",
                                 data={"student_ids": [str(first.id), str(second.id)]})
    assert response.status_code == 302
    assert Enrolment.query.filter_by(course_id=course.id).count() == 2


def test_enrolling_with_nothing_selected_is_rejected(admin_client, build):
    course = build.course()
    build.student()
    response = admin_client.post(f"/admin/courses/{course.id}/enrol", data={})
    assert response.status_code == 200
    assert b"Select at least one student" in response.data
    assert Enrolment.query.count() == 0


def test_already_enrolled_student_cannot_be_enrolled_twice(admin_client, build):
    course, student = build.course(), build.student()
    build.enrol(student, course)
    response = admin_client.post(f"/admin/courses/{course.id}/enrol",
                                 data={"student_ids": [str(student.id)]})
    assert response.status_code == 200          # not an available choice any more
    assert Enrolment.query.count() == 1


def test_unknown_student_id_cannot_be_enrolled(admin_client, build):
    course = build.course()
    response = admin_client.post(f"/admin/courses/{course.id}/enrol",
                                 data={"student_ids": ["99999"]})
    assert response.status_code == 200
    assert Enrolment.query.count() == 0


def test_enrolling_into_unknown_course_gives_404(admin_client):
    assert admin_client.get("/admin/courses/9999/enrol").status_code == 404


# ---- unenrolment rules ------------------------------------------------------
def test_student_without_records_can_be_unenrolled(admin_client, build):
    course, student = build.course(), build.student()
    build.enrol(student, course)
    response = admin_client.post(
        f"/admin/courses/{course.id}/enrolments/{student.id}/remove")
    assert response.status_code == 302
    assert Enrolment.query.count() == 0
    assert Course.query.count() == 1


@pytest.mark.parametrize("kind", ["attendance", "marks", "submission", "follow_up"])
def test_unenrolment_is_blocked_when_records_exist(admin_client, build, kind):
    teacher = build.teacher()
    course = build.course(teacher=teacher)
    student = build.student()
    build.enrol(student, course)
    build.record(kind, student, course, teacher)

    response = admin_client.post(
        f"/admin/courses/{course.id}/enrolments/{student.id}/remove",
        follow_redirects=True)

    assert b"Cannot remove" in response.data
    assert Enrolment.query.count() == 1


def test_records_in_another_course_do_not_block_unenrolment(admin_client, build):
    course_a, course_b = build.course(), build.course()
    student = build.student()
    build.enrol(student, course_a)
    build.enrol(student, course_b)
    build.attendance(student, course_b)               # record only in course B

    response = admin_client.post(
        f"/admin/courses/{course_a.id}/enrolments/{student.id}/remove")

    assert response.status_code == 302
    assert Enrolment.query.filter_by(course_id=course_a.id).count() == 0
    assert Enrolment.query.filter_by(course_id=course_b.id).count() == 1


def test_removing_a_missing_enrolment_gives_404(admin_client, build):
    course, student = build.course(), build.student()
    response = admin_client.post(
        f"/admin/courses/{course.id}/enrolments/{student.id}/remove")
    assert response.status_code == 404


def test_teacher_cannot_remove_an_enrolment(teacher_client, build):
    course, student = build.course(), build.student()
    build.enrol(student, course)
    response = teacher_client.post(
        f"/admin/courses/{course.id}/enrolments/{student.id}/remove")
    assert response.status_code == 403
    assert Enrolment.query.count() == 1
