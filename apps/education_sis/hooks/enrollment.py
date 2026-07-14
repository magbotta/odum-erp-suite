"""Education SIS hooks — enrollment and section management (§7)."""


def enroll_in_section(student, section, enrollment_date) -> None:
    """
    Create an Enrollment record and update the section's enrolled_count.
    Raises ValueError if the section is at capacity or student is already enrolled.
    """
    from apps.education_sis.models import Enrollment

    if section.enrolled_count >= section.capacity:
        raise ValueError("Section {} is at capacity ({}/{}).".format(
            section.section_code, section.enrolled_count, section.capacity))

    existing = Enrollment.objects.filter(
        student=student, section=section, is_deleted=False
    ).first()
    if existing:
        if existing.status == Enrollment.Status.DROPPED:
            existing.status = Enrollment.Status.REGISTERED
            existing.enrollment_date = enrollment_date
            existing.save(update_fields=["status", "enrollment_date"])
            update_section_count(section)
            return
        raise ValueError("Student {} is already enrolled in section {}.".format(
            student.student_number, section.section_code))

    Enrollment.objects.create(
        student=student,
        section=section,
        status=Enrollment.Status.REGISTERED,
        enrollment_date=enrollment_date,
        company_id=student.company_id,
    )
    update_section_count(section)


def drop_from_section(enrollment) -> None:
    """Drop an enrollment and decrement section count."""
    from apps.education_sis.models import Enrollment
    enrollment.status = Enrollment.Status.DROPPED
    enrollment.save(update_fields=["status"])
    update_section_count(enrollment.section)


def complete_enrollment(enrollment) -> None:
    """Mark enrollment as completed."""
    from apps.education_sis.models import Enrollment
    enrollment.status = Enrollment.Status.COMPLETED
    enrollment.save(update_fields=["status"])


def update_section_count(section) -> None:
    """Recount active enrollments for a section and update enrolled_count."""
    from apps.education_sis.models import Enrollment
    count = Enrollment.objects.filter(
        section=section,
        status__in=[Enrollment.Status.REGISTERED, Enrollment.Status.ATTENDING],
        is_deleted=False,
    ).count()
    section.enrolled_count = count
    section.save(update_fields=["enrolled_count"])
