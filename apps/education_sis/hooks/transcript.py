"""Transcript generation hooks (§7 — academic transcript)."""
import datetime


def generate_transcript(student, academic_year=None, generated_by_id=None):
    """
    Collect all completed enrollments, compute cumulative GPA, build structured
    transcript_data grouped by academic-year → term → courses, then create or
    update an AcademicTranscript record.

    Returns the AcademicTranscript instance.
    """
    from apps.education_sis.models import Enrollment, AcademicTranscript
    from apps.education_sis.hooks.grade import compute_student_gpa
    from core.numbering.service import get_next_number

    qs = (
        Enrollment.objects
        .filter(student=student, status="completed", is_deleted=False)
        .select_related("section__course", "section__academic_year", "section__term")
    )
    if academic_year:
        qs = qs.filter(section__academic_year=academic_year)

    # Build transcript_data: { year_name: { term_name: [ course_row, ... ] } }
    transcript_data = {}
    total_credit_hours = 0

    for enrollment in qs:
        year_name = str(enrollment.section.academic_year)
        term_name = str(enrollment.section.term) if enrollment.section.term else "Full Year"
        course = enrollment.section.course

        if year_name not in transcript_data:
            transcript_data[year_name] = {}
        if term_name not in transcript_data[year_name]:
            transcript_data[year_name][term_name] = []

        transcript_data[year_name][term_name].append({
            "course_code": course.code,
            "course_name": course.name,
            "credit_hours": course.credit_hours,
            "section_code": enrollment.section.section_code,
            "final_grade": enrollment.final_grade or "N/A",
            "grade_points": float(enrollment.grade_points) if enrollment.grade_points else None,
        })
        total_credit_hours += course.credit_hours

    cumulative_gpa = compute_student_gpa(student)

    now = datetime.datetime.now()
    transcript, _ = AcademicTranscript.objects.get_or_create(
        student=student,
        academic_year=academic_year,
        defaults={
            "transcript_number": get_next_number("TRN", student.company_id),
            "company_id": student.company_id,
        },
    )
    transcript.status = AcademicTranscript.Status.OFFICIAL
    transcript.cumulative_gpa = cumulative_gpa
    transcript.total_credit_hours = total_credit_hours
    transcript.transcript_data = transcript_data
    transcript.generated_at = now
    transcript.generated_by_id = generated_by_id
    transcript.save()
    return transcript


def seal_transcript(transcript, sealed_by_id=None) -> None:
    """Mark a transcript as sealed/certified — immutable after this point."""
    transcript.status = "sealed"
    transcript.sealed_at = datetime.datetime.now()
    transcript.sealed_by_id = sealed_by_id
    transcript.save()
