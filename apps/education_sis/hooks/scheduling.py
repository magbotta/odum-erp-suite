"""
Conflict-free scheduling enforcement (§7 — 'Conflict-free Course/Class/Room Scheduling').
Call check_scheduling_conflicts() before saving a CourseSection where start/end times are set.
"""


def _effective_days(section):
    """Return the de-duplicated day list for a section."""
    days = list(section.days_of_week or [])
    if section.day_of_week and section.day_of_week not in days:
        days.append(section.day_of_week)
    return days


def _times_overlap(a_start, a_end, b_start, b_end):
    """True when two time intervals overlap (exclusive at endpoints)."""
    return a_start < b_end and a_end > b_start


def check_scheduling_conflicts(section) -> None:
    """
    Raises ValueError if the section's room or instructor is already booked in an
    overlapping time slot on the same day(s) within the same academic year.
    """
    if not section.start_time or not section.end_time:
        return

    days = _effective_days(section)
    if not days:
        return

    from apps.education_sis.models import CourseSection

    candidates = CourseSection.objects.filter(
        academic_year=section.academic_year,
        is_deleted=False,
        start_time__isnull=False,
        end_time__isnull=False,
    ).exclude(pk=section.pk)

    for other in candidates:
        other_days = _effective_days(other)
        # No day overlap → no conflict possible
        if not set(days) & set(other_days):
            continue
        # Time overlap check
        if not _times_overlap(section.start_time, section.end_time,
                              other.start_time, other.end_time):
            continue

        # Room conflict
        if section.room_link_id and section.room_link_id == other.room_link_id:
            raise ValueError(
                "Room {} is already booked for {} {} on {} at {}-{}. "
                "Please choose a different room or time slot.".format(
                    section.room_link,
                    other.course.code,
                    other.section_code,
                    ", ".join(days),
                    section.start_time.strftime("%H:%M"),
                    section.end_time.strftime("%H:%M"),
                )
            )

        # Instructor conflict
        if (section.instructor_employee_id
                and section.instructor_employee_id == other.instructor_employee_id):
            raise ValueError(
                "Instructor {} is already scheduled for {} {} on {} at {}-{}. "
                "Please resolve the schedule conflict before saving.".format(
                    section.instructor_employee_id,
                    other.course.code,
                    other.section_code,
                    ", ".join(days),
                    section.start_time.strftime("%H:%M"),
                    section.end_time.strftime("%H:%M"),
                )
            )
