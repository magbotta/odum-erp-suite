"""Education SIS hooks — student lifecycle (§7)."""
import datetime

from apps.education_sis.models import Student
from core.numbering.service import get_next_number


def set_student_number(student: Student) -> None:
    if not student.student_number:
        student.student_number = get_next_number("STU", company_id=student.company_id)


def admit_student(student: Student) -> None:
    """Move from applicant to enrolled (admitted)."""
    student.status = Student.Status.ENROLLED
    if not student.enrollment_date:
        student.enrollment_date = datetime.date.today()


def activate_student(student: Student) -> None:
    """Move to Active (first day of classes)."""
    student.status = Student.Status.ACTIVE


def graduate_student(student: Student) -> None:
    student.status = Student.Status.GRADUATED


def withdraw_student(student: Student) -> None:
    student.status = Student.Status.WITHDRAWN


def suspend_student(student: Student) -> None:
    student.status = Student.Status.SUSPENDED


def reinstate_student(student: Student) -> None:
    student.status = Student.Status.ACTIVE
