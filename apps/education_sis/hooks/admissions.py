"""
Admissions pipeline lifecycle hooks (§7).
Pipeline: draft → submitted → under_review → offer_made → accepted → (convert_to_student)
                                                         → rejected
                                                         → waitlisted
"""
import datetime


def set_application_number(application) -> None:
    from core.numbering.service import get_next_number
    if not application.application_number:
        application.application_number = get_next_number("APP", application.company_id)


def submit_application(application) -> None:
    set_application_number(application)
    application.status = "submitted"
    application.save()


def start_review(application) -> None:
    application.status = "under_review"
    application.save()


def make_offer(application, offer_expiry_days=30) -> None:
    today = datetime.date.today()
    application.status = "offer_made"
    application.offer_date = today
    application.offer_expiry_date = today + datetime.timedelta(days=offer_expiry_days)
    application.save()


def accept_offer(application) -> None:
    application.status = "accepted"
    application.acceptance_date = datetime.date.today()
    application.save()


def reject_application(application, reason="") -> None:
    application.status = "rejected"
    application.rejection_reason = reason
    application.save()


def waitlist_application(application) -> None:
    application.status = "waitlisted"
    application.save()


def withdraw_application(application) -> None:
    application.status = "withdrawn"
    application.save()


def convert_to_student(application):
    """
    Convert an accepted application into a Student record and link it back.
    Returns the newly created Student.
    """
    from apps.education_sis.models import Student
    from apps.education_sis.hooks.student import set_student_number, admit_student

    if application.status != "accepted":
        raise ValueError(
            "Only an accepted application can be converted to a student "
            "(current status: {}).".format(application.status)
        )

    student = Student(
        first_name=application.applicant_first_name,
        last_name=application.applicant_last_name,
        email=application.email,
        phone=application.phone,
        date_of_birth=application.date_of_birth,
        address=application.address,
        program=application.program,
        company_id=application.company_id,
        student_number="",  # assigned by set_student_number
    )
    set_student_number(student)
    admit_student(student)
    student.save()

    # Link the new student back to the originating application
    application.student = student
    application.save(update_fields=["student_id"])
    return student
