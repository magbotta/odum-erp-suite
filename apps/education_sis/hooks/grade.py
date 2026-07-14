"""Education SIS hooks — grade calculation and GPA (§7)."""
from decimal import Decimal


def compute_final_grade(enrollment) -> None:
    """
    Computes a weighted final grade from GradeEntry rows and maps to letter/GPA via GradeScale.
    Updates enrollment.final_grade and enrollment.grade_points.
    """
    from apps.education_sis.models import GradeEntry, GradeScale, GradeScaleEntry

    entries = GradeEntry.objects.filter(enrollment=enrollment, is_deleted=False)
    if not entries.exists():
        return

    total_weight = Decimal("0")
    weighted_score = Decimal("0")

    for entry in entries:
        if entry.max_score and entry.max_score > 0:
            pct = (entry.score / entry.max_score) * 100
            weight = entry.weight_pct or Decimal("0")
            weighted_score += pct * weight
            total_weight += weight

    if total_weight == 0:
        return

    final_pct = weighted_score / total_weight

    # Find applicable grade scale: program-specific or default
    section = enrollment.section
    program = section.course.program if section.course else None
    grade_scale = None
    if program:
        grade_scale = GradeScale.objects.filter(
            program=program, is_deleted=False
        ).first()
    if not grade_scale:
        grade_scale = GradeScale.objects.filter(
            is_default=True, is_deleted=False
        ).first()

    if grade_scale:
        scale_entry = GradeScaleEntry.objects.filter(
            grade_scale=grade_scale,
            min_score__lte=final_pct,
            max_score__gte=final_pct,
            is_deleted=False,
        ).first()
        if scale_entry:
            enrollment.final_grade = scale_entry.letter_grade
            enrollment.grade_points = scale_entry.gpa_points
        else:
            enrollment.final_grade = "{:.1f}%".format(float(final_pct))
    else:
        # Fallback: simple letter grade
        pct_float = float(final_pct)
        if pct_float >= 90:
            enrollment.final_grade = "A"
        elif pct_float >= 80:
            enrollment.final_grade = "B"
        elif pct_float >= 70:
            enrollment.final_grade = "C"
        elif pct_float >= 60:
            enrollment.final_grade = "D"
        else:
            enrollment.final_grade = "F"

    enrollment.save(update_fields=["final_grade", "grade_points"])


def compute_student_gpa(student) -> Decimal:
    """Compute overall GPA for a student across completed enrollments."""
    from apps.education_sis.models import Enrollment

    completed = Enrollment.objects.filter(
        student=student,
        status="completed",
        grade_points__isnull=False,
        is_deleted=False,
    )
    if not completed.exists():
        return Decimal("0")

    total_points = sum(e.grade_points for e in completed if e.grade_points)
    return total_points / completed.count()
