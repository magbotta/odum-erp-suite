"""Education SIS hooks — student lifecycle."""
from apps.education_sis.models import Student
from core.numbering.service import get_next_number


def set_student_number(student: Student) -> None:
    if not student.student_number:
        student.student_number = get_next_number("STU", company_id=student.company_id)


def enroll_student(student: Student) -> None:
    student.status = "Enrolled"


def graduate_student(student: Student) -> None:
    student.status = "Graduated"


def withdraw_student(student: Student) -> None:
    student.status = "Withdrawn"
