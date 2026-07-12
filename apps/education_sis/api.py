"""Education SIS action endpoints."""
from uuid import UUID

from django.shortcuts import get_object_or_404
from ninja import Router

from apps.education_sis.models import Student, Enrollment
from core.platform_api.security import AuthBearer

router = Router(tags=["Education SIS Actions"], auth=AuthBearer())


@router.post("/students/{student_id}/enroll")
def enroll_student(request, student_id: UUID):
    student = get_object_or_404(Student, pk=student_id)
    if student.status != "Applicant":
        return {"error": "Only Applicant students can be enrolled."}
    from apps.education_sis.hooks.student import enroll_student as do_enroll
    do_enroll(student)
    student.save()
    return {"status": student.status}


@router.post("/students/{student_id}/graduate")
def graduate_student(request, student_id: UUID):
    student = get_object_or_404(Student, pk=student_id)
    if student.status != "Enrolled":
        return {"error": "Only Enrolled students can be graduated."}
    from apps.education_sis.hooks.student import graduate_student as do_graduate
    do_graduate(student)
    student.save()
    return {"status": student.status}


@router.post("/students/{student_id}/withdraw")
def withdraw_student(request, student_id: UUID):
    student = get_object_or_404(Student, pk=student_id)
    if student.status != "Enrolled":
        return {"error": "Only Enrolled students can be withdrawn."}
    from apps.education_sis.hooks.student import withdraw_student as do_withdraw
    do_withdraw(student)
    student.save()
    return {"status": student.status}


@router.post("/enrollments/{enrollment_id}/drop")
def drop_course(request, enrollment_id: UUID):
    enrollment = get_object_or_404(Enrollment, pk=enrollment_id)
    if enrollment.status != "Active":
        return {"error": "Only Active enrollments can be dropped."}
    enrollment.status = "Dropped"
    enrollment.save()
    return {"status": enrollment.status}


@router.post("/enrollments/{enrollment_id}/complete")
def complete_course(request, enrollment_id: UUID):
    enrollment = get_object_or_404(Enrollment, pk=enrollment_id)
    if enrollment.status != "Active":
        return {"error": "Only Active enrollments can be completed."}
    enrollment.status = "Completed"
    enrollment.save()
    return {"status": enrollment.status}
