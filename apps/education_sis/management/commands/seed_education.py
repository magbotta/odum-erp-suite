"""Seed command for Education SIS module (§7) — full implementation."""
import datetime
import uuid

from django.core.management.base import BaseCommand

COMPANY_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class Command(BaseCommand):
    help = "Seed Education SIS: Years, Terms, Rooms, Programs, Courses, Students, Admissions, Grades, IEPs, Scholarships, Fees, Transcripts"

    def handle(self, *args, **options):
        from apps.education_sis.models import (
            AcademicYear, Term, Room, Program, Course, CourseSection, CoursePrerequisite,
            Student, AdmissionApplication, Enrollment, ClassAttendance,
            GradeEntry, GradeScale, GradeScaleEntry, LearningStandard, StandardsGradeEntry,
            FeeSchedule, StudentFeeInvoice, FeePaymentPlan, FeePaymentPlanInstalment,
            Scholarship, ScholarshipAward, IEPCase, StudentDocument, ComplianceReport,
            AcademicTranscript,
        )

        self.stdout.write("Seeding Education SIS module...")

        # ── Academic Years ────────────────────────────────────────────────────
        ay_2425, _ = AcademicYear.objects.get_or_create(
            name="2024-2025", company_id=COMPANY_ID,
            defaults={
                "start_date": datetime.date(2024, 9, 1),
                "end_date": datetime.date(2025, 6, 30),
                "is_active": False,
                "company_id": COMPANY_ID,
            }
        )
        ay_2526, _ = AcademicYear.objects.get_or_create(
            name="2025-2026", company_id=COMPANY_ID,
            defaults={
                "start_date": datetime.date(2025, 9, 1),
                "end_date": datetime.date(2026, 6, 30),
                "is_active": True,
                "company_id": COMPANY_ID,
            }
        )
        self.stdout.write("  2 Academic Years")

        # ── Terms ─────────────────────────────────────────────────────────────
        term_fall25, _ = Term.objects.get_or_create(
            academic_year=ay_2526, name="Fall 2025", company_id=COMPANY_ID,
            defaults={
                "term_type": "fall",
                "start_date": datetime.date(2025, 9, 1),
                "end_date": datetime.date(2025, 12, 20),
                "registration_open_date": datetime.date(2025, 7, 1),
                "registration_close_date": datetime.date(2025, 8, 31),
                "grade_submission_deadline": datetime.date(2026, 1, 10),
                "is_active": False,
                "company_id": COMPANY_ID,
            }
        )
        term_spring26, _ = Term.objects.get_or_create(
            academic_year=ay_2526, name="Spring 2026", company_id=COMPANY_ID,
            defaults={
                "term_type": "spring",
                "start_date": datetime.date(2026, 1, 12),
                "end_date": datetime.date(2026, 5, 31),
                "registration_open_date": datetime.date(2025, 11, 1),
                "registration_close_date": datetime.date(2026, 1, 5),
                "grade_submission_deadline": datetime.date(2026, 6, 15),
                "is_active": True,
                "company_id": COMPANY_ID,
            }
        )
        self.stdout.write("  2 Terms (Fall 2025, Spring 2026)")

        # ── Rooms ─────────────────────────────────────────────────────────────
        rooms = {}
        room_data = [
            ("101", "Main Building", "1", "lecture", 60, True),
            ("102", "Main Building", "1", "lecture", 50, True),
            ("203", "Main Building", "2", "seminar", 30, True),
            ("304", "Main Building", "3", "seminar", 25, True),
            ("LAB-1", "Science Block", "1", "lab", 24, True),
            ("305", "Main Building", "3", "lecture", 30, True),
        ]
        for rnum, bldg, flr, rtype, cap, accessible in room_data:
            r, _ = Room.objects.get_or_create(
                room_number=rnum, building=bldg, company_id=COMPANY_ID,
                defaults={
                    "floor": flr,
                    "room_type": rtype,
                    "capacity": cap,
                    "has_projector": True,
                    "has_whiteboard": True,
                    "is_accessible": accessible,
                    "is_active": True,
                    "company_id": COMPANY_ID,
                }
            )
            rooms[rnum] = r
        self.stdout.write("  {} Rooms".format(len(rooms)))

        # ── Programs ──────────────────────────────────────────────────────────
        programs = {}
        prog_data = [
            ("BSc Computer Science", "BSC-CS", 4),
            ("BSc Business Administration", "BSC-BA", 4),
            ("Diploma in Engineering Technology", "DIP-ET", 2),
            ("Certificate in Accounting", "CERT-ACC", 1),
        ]
        for name, code, years in prog_data:
            p, _ = Program.objects.get_or_create(
                code=code, company_id=COMPANY_ID,
                defaults={
                    "name": name,
                    "duration_years": years,
                    "is_active": True,
                    "company_id": COMPANY_ID,
                }
            )
            programs[code] = p
        self.stdout.write("  {} Programs".format(len(programs)))

        # ── Grade Scale ───────────────────────────────────────────────────────
        gs, created = GradeScale.objects.get_or_create(
            name="Standard 4.0 Scale", company_id=COMPANY_ID,
            defaults={"is_default": True, "company_id": COMPANY_ID}
        )
        if created:
            scale_entries = [
                ("A+", 97, 100, 4.0), ("A", 93, 96.99, 4.0), ("A-", 90, 92.99, 3.7),
                ("B+", 87, 89.99, 3.3), ("B", 83, 86.99, 3.0), ("B-", 80, 82.99, 2.7),
                ("C+", 77, 79.99, 2.3), ("C", 73, 76.99, 2.0), ("C-", 70, 72.99, 1.7),
                ("D+", 67, 69.99, 1.3), ("D", 60, 66.99, 1.0), ("F", 0, 59.99, 0.0),
            ]
            for letter, lo, hi, gpa in scale_entries:
                GradeScaleEntry.objects.create(
                    grade_scale=gs, letter_grade=letter,
                    min_score=lo, max_score=hi, gpa_points=gpa,
                    company_id=COMPANY_ID,
                )
        self.stdout.write("  Grade Scale: {} entries".format(gs.entries.count()))

        # ── Courses ───────────────────────────────────────────────────────────
        courses = {}
        course_data = [
            ("Introduction to Programming", "CS101", 3, "BSC-CS"),
            ("Data Structures & Algorithms", "CS201", 3, "BSC-CS"),
            ("Database Systems", "CS301", 3, "BSC-CS"),
            ("Software Engineering", "CS401", 3, "BSC-CS"),
            ("Principles of Management", "BA101", 3, "BSC-BA"),
            ("Financial Accounting", "BA201", 3, "BSC-BA"),
            ("Marketing Management", "BA301", 3, "BSC-BA"),
            ("Engineering Mathematics", "ET101", 3, "DIP-ET"),
            ("Introductory Accounting", "ACC101", 3, "CERT-ACC"),
            ("Cost & Management Accounting", "ACC201", 3, "CERT-ACC"),
        ]
        for name, code, credits, prog_code in course_data:
            c, _ = Course.objects.get_or_create(
                code=code, company_id=COMPANY_ID,
                defaults={
                    "name": name,
                    "credit_hours": credits,
                    "program": programs.get(prog_code),
                    "is_active": True,
                    "company_id": COMPANY_ID,
                }
            )
            courses[code] = c
        self.stdout.write("  {} Courses".format(len(courses)))

        CoursePrerequisite.objects.get_or_create(
            course=courses["CS201"], prerequisite_course=courses["CS101"],
            company_id=COMPANY_ID,
            defaults={"minimum_grade": "C", "is_mandatory": True, "company_id": COMPANY_ID}
        )
        CoursePrerequisite.objects.get_or_create(
            course=courses["CS301"], prerequisite_course=courses["CS201"],
            company_id=COMPANY_ID,
            defaults={"minimum_grade": "C", "is_mandatory": True, "company_id": COMPANY_ID}
        )
        CoursePrerequisite.objects.get_or_create(
            course=courses["ACC201"], prerequisite_course=courses["ACC101"],
            company_id=COMPANY_ID,
            defaults={"minimum_grade": "D", "is_mandatory": True, "company_id": COMPANY_ID}
        )
        self.stdout.write("  3 Course Prerequisites")

        # ── Learning Standards ────────────────────────────────────────────────
        std_data = [
            ("CS-STD-01", "Demonstrate understanding of fundamental data structures",
             "Computer Science", "Year 2", "BSC-CS"),
            ("CS-STD-02", "Design and implement relational database schemas",
             "Computer Science", "Year 3", "BSC-CS"),
            ("BA-STD-01", "Apply financial accounting principles to produce accurate statements",
             "Business", "Year 2", "BSC-BA"),
        ]
        standards = {}
        for code, desc, subject, level, prog_code in std_data:
            s, _ = LearningStandard.objects.get_or_create(
                code=code, company_id=COMPANY_ID,
                defaults={
                    "description": desc,
                    "subject_area": subject,
                    "grade_level": level,
                    "program": programs.get(prog_code),
                    "is_active": True,
                    "company_id": COMPANY_ID,
                }
            )
            standards[code] = s
        self.stdout.write("  {} Learning Standards".format(len(standards)))

        # ── Course Sections ───────────────────────────────────────────────────
        instr_id = uuid.UUID("aaaaaaaa-0001-0001-0001-000000000001")
        instr2_id = uuid.UUID("aaaaaaaa-0001-0001-0001-000000000002")
        sections = {}
        # (course, sec, room_key, day, start, end, cap, instr, term, days_list)
        section_data = [
            ("CS101", "A", "101", "mon", "08:00", "09:30", 40, instr_id,
             term_fall25, ["mon", "wed"]),
            ("CS101", "B", "102", "tue", "10:00", "11:30", 35, instr2_id,
             term_fall25, ["tue", "thu"]),
            ("CS201", "A", "203", "mon", "10:00", "11:30", 30, instr_id,
             term_fall25, ["mon", "wed"]),
            ("CS301", "A", "304", "mon", "12:00", "13:30", 25, instr_id,
             term_spring26, ["mon", "wed"]),
            ("BA101", "A", "102", "tue", "08:00", "09:30", 45, instr2_id,
             term_fall25, ["tue", "thu"]),
            ("BA201", "A", "203", "wed", "14:00", "15:30", 40, instr2_id,
             term_spring26, ["wed", "fri"]),
            ("ACC101", "A", "203", "fri", "09:00", "12:00", 25, instr2_id,
             term_fall25, ["fri"]),
            ("CS401", "A", "305", "wed", "08:00", "11:00", 25, instr_id,
             term_spring26, ["wed"]),
        ]
        for (ccode, sec_code, rkey, day, start_t, end_t, cap, inst_id,
             term, days_list) in section_data:
            key = "{}-{}".format(ccode, sec_code)
            sec, _ = CourseSection.objects.get_or_create(
                course=courses[ccode],
                academic_year=ay_2526,
                section_code=sec_code,
                company_id=COMPANY_ID,
                defaults={
                    "instructor_employee_id": inst_id,
                    "room": "{} Room {}".format(
                        term.name if term else "", rkey
                    ),
                    "room_link": rooms.get(rkey),
                    "term": term,
                    "capacity": cap,
                    "enrolled_count": 0,
                    "day_of_week": day,
                    "days_of_week": days_list,
                    "start_time": datetime.time(*[int(x) for x in start_t.split(":")]),
                    "end_time": datetime.time(*[int(x) for x in end_t.split(":")]),
                    "company_id": COMPANY_ID,
                }
            )
            sections[key] = sec
        self.stdout.write("  {} Course Sections".format(len(sections)))

        # ── Fee Schedules ─────────────────────────────────────────────────────
        fee_cs, _ = FeeSchedule.objects.get_or_create(
            name="BSc CS Fees 2025-2026", company_id=COMPANY_ID,
            defaults={
                "program": programs["BSC-CS"], "academic_year": ay_2526,
                "tuition_amount": 4500, "other_fees": 350, "currency": "USD",
                "company_id": COMPANY_ID,
            }
        )
        fee_ba, _ = FeeSchedule.objects.get_or_create(
            name="BSc BA Fees 2025-2026", company_id=COMPANY_ID,
            defaults={
                "program": programs["BSC-BA"], "academic_year": ay_2526,
                "tuition_amount": 4200, "other_fees": 300, "currency": "USD",
                "company_id": COMPANY_ID,
            }
        )
        fee_acc, _ = FeeSchedule.objects.get_or_create(
            name="Certificate Accounting Fees 2025-2026", company_id=COMPANY_ID,
            defaults={
                "program": programs["CERT-ACC"], "academic_year": ay_2526,
                "tuition_amount": 1800, "other_fees": 150, "currency": "USD",
                "company_id": COMPANY_ID,
            }
        )
        self.stdout.write("  3 Fee Schedules")

        # ── Scholarships ──────────────────────────────────────────────────────
        scholarships = {}
        sch_data = [
            ("Vice Chancellor's Merit Award", "VCA-MERIT", "merit", 1000, False, "BSC-CS",
             "Minimum GPA 3.8 in preceding year"),
            ("Government Bursary Scheme", "GOV-BURSARY", "government_grant", 500, False, None,
             "Household income below threshold; submitted means-test form"),
            ("CS Departmental Scholarship", "CS-DEPT", "departmental", 20, True, "BSC-CS",
             "Top 5% in CS cohort; renewed if GPA >= 3.5"),
        ]
        for sname, scode, stype, amount, is_pct, prog_code, criteria in sch_data:
            sch, _ = Scholarship.objects.get_or_create(
                code=scode, company_id=COMPANY_ID,
                defaults={
                    "name": sname,
                    "scholarship_type": stype,
                    "amount": amount,
                    "currency": "USD",
                    "is_percentage": is_pct,
                    "program": programs.get(prog_code) if prog_code else None,
                    "eligibility_criteria": criteria,
                    "renewable": True,
                    "is_active": True,
                    "company_id": COMPANY_ID,
                }
            )
            scholarships[scode] = sch
        self.stdout.write("  {} Scholarships".format(len(scholarships)))

        # ── Students ──────────────────────────────────────────────────────────
        students_data = [
            {
                "student_number": "STU-0001",
                "first_name": "Abena", "last_name": "Sarkodie",
                "email": "abena.sarkodie@student.edu",
                "date_of_birth": datetime.date(2002, 4, 12),
                "program": programs["BSC-CS"], "status": "active",
                "enrollment_date": datetime.date(2022, 9, 5),
                "expected_graduation_date": datetime.date(2026, 6, 30),
                "guardian_name": "Emmanuel Sarkodie",
                "guardian_email": "e.sarkodie@yahoo.com",
            },
            {
                "student_number": "STU-0002",
                "first_name": "Kwabena", "last_name": "Ofosu",
                "email": "kwabena.ofosu@student.edu",
                "date_of_birth": datetime.date(2001, 11, 8),
                "program": programs["BSC-CS"], "status": "active",
                "enrollment_date": datetime.date(2021, 9, 6),
                "expected_graduation_date": datetime.date(2025, 6, 30),
                "guardian_name": "Patricia Ofosu",
                "guardian_email": "p.ofosu@gmail.com",
            },
            {
                "student_number": "STU-0003",
                "first_name": "Efua", "last_name": "Boampong",
                "email": "efua.boampong@student.edu",
                "date_of_birth": datetime.date(2003, 7, 22),
                "program": programs["BSC-BA"], "status": "active",
                "enrollment_date": datetime.date(2023, 9, 4),
                "expected_graduation_date": datetime.date(2027, 6, 30),
                "guardian_name": "Yaw Boampong",
                "guardian_email": "yaw.b@outlook.com",
            },
            {
                "student_number": "STU-0004",
                "first_name": "Kofi", "last_name": "Darko",
                "email": "kofi.darko@student.edu",
                "date_of_birth": datetime.date(2004, 2, 28),
                "program": programs["CERT-ACC"], "status": "enrolled",
                "enrollment_date": datetime.date(2025, 9, 8),
                "expected_graduation_date": datetime.date(2026, 6, 30),
                "guardian_name": "Mrs. Darko",
                "guardian_email": "darko.family@gmail.com",
            },
            {
                "student_number": "STU-0005",
                "first_name": "Akosua", "last_name": "Mensah",
                "email": "akosua.mensah@student.edu",
                "date_of_birth": datetime.date(2000, 9, 3),
                "program": programs["BSC-BA"], "status": "graduated",
                "enrollment_date": datetime.date(2020, 9, 7),
                "expected_graduation_date": datetime.date(2024, 6, 30),
                "actual_graduation_date": datetime.date(2024, 6, 15),
                "cumulative_gpa": "3.72",
            },
            {
                "student_number": "STU-0006",
                "first_name": "James", "last_name": "Owusu",
                "email": "james.owusu@student.edu",
                "date_of_birth": datetime.date(2003, 5, 15),
                "program": programs["BSC-CS"], "status": "active",
                "enrollment_date": datetime.date(2022, 9, 5),
                "expected_graduation_date": datetime.date(2026, 6, 30),
                "has_iep": True,
                "guardian_name": "Richard Owusu",
                "guardian_email": "r.owusu@gmail.com",
            },
            {
                "student_number": "STU-0007",
                "first_name": "Ama", "last_name": "Asamoah",
                "email": "ama.asamoah@student.edu",
                "date_of_birth": datetime.date(2002, 12, 6),
                "program": programs["BSC-CS"], "status": "applicant",
                "guardian_name": "Nana Asamoah",
                "guardian_email": "nana.asamoah@hotmail.com",
            },
        ]
        students = {}
        for sd in students_data:
            s, created = Student.objects.get_or_create(
                student_number=sd["student_number"], company_id=COMPANY_ID,
                defaults={
                    "first_name": sd["first_name"],
                    "last_name": sd["last_name"],
                    "email": sd.get("email", ""),
                    "date_of_birth": sd.get("date_of_birth"),
                    "program": sd.get("program"),
                    "status": sd["status"],
                    "enrollment_date": sd.get("enrollment_date"),
                    "expected_graduation_date": sd.get("expected_graduation_date"),
                    "actual_graduation_date": sd.get("actual_graduation_date"),
                    "cumulative_gpa": sd.get("cumulative_gpa"),
                    "guardian_name": sd.get("guardian_name", ""),
                    "guardian_email": sd.get("guardian_email", ""),
                    "has_iep": sd.get("has_iep", False),
                    "company_id": COMPANY_ID,
                }
            )
            students[sd["student_number"]] = s
        self.stdout.write("  {} Students".format(len(students)))

        # ── Admission Applications ────────────────────────────────────────────
        app_data = [
            # Already-accepted → linked to STU-0001 (Abena, came through admissions 2022)
            {
                "app_number": "APP-0001",
                "first_name": "Abena", "last_name": "Sarkodie",
                "email": "abena.sarkodie@student.edu",
                "status": "accepted",
                "program": programs["BSC-CS"],
                "previous_institution": "Achimota School",
                "gpa": "3.85",
                "student": students["STU-0001"],
            },
            # Under review
            {
                "app_number": "APP-0002",
                "first_name": "Kojo", "last_name": "Ampofo",
                "email": "kojo.ampofo@gmail.com",
                "status": "under_review",
                "program": programs["BSC-CS"],
                "previous_institution": "Prempeh College",
                "gpa": "3.40",
                "student": None,
            },
            # Offer made — pending response
            {
                "app_number": "APP-0003",
                "first_name": "Esi", "last_name": "Nyarko",
                "email": "esi.nyarko@outlook.com",
                "status": "offer_made",
                "program": programs["BSC-BA"],
                "previous_institution": "Wesley Girls High School",
                "gpa": "3.60",
                "student": None,
            },
            # Rejected
            {
                "app_number": "APP-0004",
                "first_name": "Yaw", "last_name": "Barimah",
                "email": "yaw.barimah@yahoo.com",
                "status": "rejected",
                "program": programs["DIP-ET"],
                "previous_institution": "Takoradi Technical Institute",
                "gpa": "2.10",
                "student": None,
            },
        ]
        app_count = 0
        for ad in app_data:
            _, created = AdmissionApplication.objects.get_or_create(
                application_number=ad["app_number"], company_id=COMPANY_ID,
                defaults={
                    "status": ad["status"],
                    "applicant_first_name": ad["first_name"],
                    "applicant_last_name": ad["last_name"],
                    "email": ad["email"],
                    "program": ad["program"],
                    "academic_year": ay_2526,
                    "previous_institution": ad.get("previous_institution", ""),
                    "gpa_at_previous_institution": ad.get("gpa"),
                    "offer_date": (
                        datetime.date(2025, 8, 1) if ad["status"] == "offer_made" else None
                    ),
                    "offer_expiry_date": (
                        datetime.date(2025, 8, 31) if ad["status"] == "offer_made" else None
                    ),
                    "acceptance_date": (
                        datetime.date(2022, 8, 20) if ad["status"] == "accepted" else None
                    ),
                    "rejection_reason": (
                        "Academic requirements not met for the selected programme."
                        if ad["status"] == "rejected" else ""
                    ),
                    "student": ad.get("student"),
                    "company_id": COMPANY_ID,
                }
            )
            if created:
                app_count += 1
        self.stdout.write("  {} Admission Applications".format(app_count))

        # ── Enrollments ───────────────────────────────────────────────────────
        enroll_data = [
            ("STU-0001", "CS301-A", datetime.date(2025, 9, 8), "attending", "B+", 3.3),
            ("STU-0002", "CS401-A", datetime.date(2025, 9, 8), "attending", None, None),
            ("STU-0003", "BA201-A", datetime.date(2025, 9, 9), "attending", None, None),
            ("STU-0004", "ACC101-A", datetime.date(2025, 9, 10), "registered", None, None),
            ("STU-0006", "CS301-A", datetime.date(2025, 9, 8), "attending", "C+", 2.3),
        ]
        enroll_count = 0
        for stu_num, sec_key, enroll_date, status, grade, gpa in enroll_data:
            student = students[stu_num]
            section = sections.get(sec_key)
            if not section:
                self.stdout.write("  WARNING: section {} not found".format(sec_key))
                continue
            enr, created = Enrollment.objects.get_or_create(
                student=student, section=section, company_id=COMPANY_ID,
                defaults={
                    "status": status,
                    "enrollment_date": enroll_date,
                    "final_grade": grade or "",
                    "grade_points": gpa,
                    "company_id": COMPANY_ID,
                }
            )
            if created:
                enroll_count += 1
                section.enrolled_count = Enrollment.objects.filter(
                    section=section, status__in=["registered", "attending"], is_deleted=False,
                ).count()
                section.save(update_fields=["enrolled_count"])
        self.stdout.write("  {} Enrollments".format(enroll_count))

        # ── Grade Entries ─────────────────────────────────────────────────────
        abena_enr = Enrollment.objects.filter(
            student=students["STU-0001"],
            section__course=courses["CS301"],
            is_deleted=False
        ).first()
        if abena_enr:
            for aname, max_s, score, weight in [
                ("Midterm Exam", 100, 78, 30),
                ("Assignment 1", 50, 45, 10),
                ("Assignment 2", 50, 48, 10),
                ("Final Exam", 100, 85, 50),
            ]:
                GradeEntry.objects.get_or_create(
                    enrollment=abena_enr, assessment_name=aname, company_id=COMPANY_ID,
                    defaults={
                        "max_score": max_s, "score": score, "weight_pct": weight,
                        "graded_by_employee_id": instr_id,
                        "company_id": COMPANY_ID,
                    }
                )
            self.stdout.write("  4 Grade Entries for Abena (CS301)")

        # ── Standards-Based Grade Entries ─────────────────────────────────────
        if abena_enr and "CS-STD-02" in standards:
            StandardsGradeEntry.objects.get_or_create(
                enrollment=abena_enr, standard=standards["CS-STD-02"],
                company_id=COMPANY_ID,
                defaults={
                    "proficiency_level": "meeting",
                    "evidence": "Successfully designed normalized schema for mid-term project",
                    "assessed_date": datetime.date(2026, 3, 15),
                    "company_id": COMPANY_ID,
                }
            )
            self.stdout.write("  1 Standards Grade Entry for Abena")

        # ── Attendance Records ────────────────────────────────────────────────
        if abena_enr:
            att_data = [
                (datetime.date(2026, 1, 5), "present"),
                (datetime.date(2026, 1, 7), "present"),
                (datetime.date(2026, 1, 12), "absent"),
                (datetime.date(2026, 1, 14), "present"),
                (datetime.date(2026, 1, 19), "late"),
                (datetime.date(2026, 1, 21), "present"),
            ]
            att_count = 0
            for att_date, att_status in att_data:
                _, created = ClassAttendance.objects.get_or_create(
                    enrollment=abena_enr, date=att_date, company_id=COMPANY_ID,
                    defaults={"status": att_status, "company_id": COMPANY_ID}
                )
                if created:
                    att_count += 1
            self.stdout.write("  {} Attendance records".format(att_count))

        # ── IEP Cases ─────────────────────────────────────────────────────────
        james = students["STU-0006"]
        iep, created = IEPCase.objects.get_or_create(
            student=james, plan_type="iep", company_id=COMPANY_ID,
            defaults={
                "case_number": "IEP-0001",
                "status": "active",
                "primary_disability": "Specific Learning Disability (Dyslexia)",
                "eligibility_date": datetime.date(2022, 7, 15),
                "plan_start_date": datetime.date(2022, 9, 1),
                "plan_end_date": datetime.date(2026, 8, 31),
                "annual_review_date": datetime.date(2026, 9, 1),
                "case_manager_name": "Mrs. Ama Tetteh",
                "annual_goals": [
                    {
                        "goal": "Improve reading fluency to grade-level by year end",
                        "objectives": [
                            "Use text-to-speech tools for all reading assignments",
                            "Complete guided reading sessions twice weekly",
                        ],
                        "progress": "on_track",
                    }
                ],
                "accommodations": [
                    "Extended time (150%) on all assessments",
                    "Text-to-speech software for exams",
                    "Preferential seating",
                    "Digital note-taking permitted",
                ],
                "parent_consent_obtained": True,
                "parent_consent_date": datetime.date(2022, 8, 20),
                "last_meeting_date": datetime.date(2025, 9, 15),
                "next_meeting_date": datetime.date(2026, 9, 1),
                "company_id": COMPANY_ID,
            }
        )
        if created:
            self.stdout.write("  IEP Case IEP-0001 for James Owusu")

        # ── Student Documents ─────────────────────────────────────────────────
        doc_count = 0
        for student, doc_type, title, confidential in [
            (students["STU-0001"], "id_document", "National ID Card", False),
            (students["STU-0001"], "admission", "Offer Letter 2022", False),
            (students["STU-0002"], "transcript", "Year 3 Official Transcript", False),
            (students["STU-0006"], "iep_document", "IEP Plan 2022-2026", True),
            (students["STU-0006"], "medical", "Medical Assessment Report (Confidential)", True),
        ]:
            _, created = StudentDocument.objects.get_or_create(
                student=student, title=title, company_id=COMPANY_ID,
                defaults={
                    "document_type": doc_type,
                    "is_confidential": confidential,
                    "uploaded_at": datetime.datetime(
                        2025, 9, 10, 10, 0, tzinfo=datetime.timezone.utc
                    ),
                    "company_id": COMPANY_ID,
                }
            )
            if created:
                doc_count += 1
        self.stdout.write("  {} Student Documents".format(doc_count))

        # ── Fee Invoices ──────────────────────────────────────────────────────
        fee_inv_data = [
            (students["STU-0001"], fee_cs, ay_2526,
             datetime.date(2025, 10, 1), 4850, 4850, 0, "paid"),
            (students["STU-0002"], fee_cs, ay_2526,
             datetime.date(2025, 10, 1), 4850, 2500, 0, "partially_paid"),
            (students["STU-0003"], fee_ba, ay_2526,
             datetime.date(2025, 10, 1), 4500, 4500, 0, "paid"),
            (students["STU-0004"], fee_acc, ay_2526,
             datetime.date(2025, 10, 15), 1950, 0, 0, "issued"),
            (students["STU-0006"], fee_cs, ay_2526,
             datetime.date(2025, 10, 1), 4850, 0, 0, "overdue"),
        ]
        fee_count = 0
        invoices = {}
        for i, (stu, sched, ay, due, amount, paid, discount, status) in enumerate(
            fee_inv_data, 1
        ):
            inv_num = "SINV-{:04d}".format(i)
            inv, created = StudentFeeInvoice.objects.get_or_create(
                invoice_number=inv_num, company_id=COMPANY_ID,
                defaults={
                    "student": stu,
                    "fee_schedule": sched,
                    "academic_year": ay,
                    "due_date": due,
                    "amount": amount,
                    "paid_amount": paid,
                    "discount_amount": discount,
                    "status": status,
                    "issue_date": datetime.date(2025, 9, 15),
                    "company_id": COMPANY_ID,
                }
            )
            if created:
                fee_count += 1
            invoices[inv_num] = inv
        self.stdout.write("  {} Student Fee Invoices".format(fee_count))

        # ── Scholarship Awards ────────────────────────────────────────────────
        # Merit award for Abena
        _, created = ScholarshipAward.objects.get_or_create(
            student=students["STU-0001"],
            scholarship=scholarships["VCA-MERIT"],
            academic_year=ay_2526,
            company_id=COMPANY_ID,
            defaults={
                "awarded_amount": 1000,
                "currency": "USD",
                "status": "active",
                "award_date": datetime.date(2025, 8, 1),
                "notes": "Awarded for maintaining GPA above 3.8 in 2024-2025",
                "company_id": COMPANY_ID,
            }
        )
        # Government bursary for James (financial need)
        _, created2 = ScholarshipAward.objects.get_or_create(
            student=students["STU-0006"],
            scholarship=scholarships["GOV-BURSARY"],
            academic_year=ay_2526,
            company_id=COMPANY_ID,
            defaults={
                "awarded_amount": 500,
                "currency": "USD",
                "status": "active",
                "award_date": datetime.date(2025, 9, 1),
                "notes": "Approved under national student bursary scheme",
                "company_id": COMPANY_ID,
            }
        )
        self.stdout.write("  2 Scholarship Awards")

        # ── Payment Plan for Kwabena (SINV-0002 partially paid) ──────────────
        kwabena_inv = invoices.get("SINV-0002")
        if kwabena_inv and not kwabena_inv.payment_plans.exists():
            plan = FeePaymentPlan.objects.create(
                invoice=kwabena_inv,
                plan_name="Kwabena 2-instalment plan",
                number_of_instalments=2,
                status="active",
                company_id=COMPANY_ID,
            )
            FeePaymentPlanInstalment.objects.create(
                payment_plan=plan, instalment_number=1,
                due_date=datetime.date(2025, 10, 1),
                amount=2500, paid_amount=2500, status="paid",
                paid_date=datetime.date(2025, 9, 28),
                payment_reference="MPESA-KO-001",
                company_id=COMPANY_ID,
            )
            FeePaymentPlanInstalment.objects.create(
                payment_plan=plan, instalment_number=2,
                due_date=datetime.date(2025, 12, 1),
                amount=2350, paid_amount=0, status="pending",
                company_id=COMPANY_ID,
            )
            self.stdout.write("  Payment Plan for Kwabena (2 instalments)")

        # ── Compliance Report ─────────────────────────────────────────────────
        ComplianceReport.objects.get_or_create(
            report_number="CR-0001", company_id=COMPANY_ID,
            defaults={
                "report_type": "enrollment_count",
                "academic_year": ay_2526,
                "status": "submitted",
                "jurisdiction": "National Accreditation Board (Ghana)",
                "due_date": datetime.date(2025, 11, 30),
                "submitted_date": datetime.date(2025, 11, 15),
                "report_data": {
                    "total_enrolled": 7,
                    "by_program": {
                        "BSC-CS": 4, "BSC-BA": 2, "CERT-ACC": 1,
                    },
                    "by_gender": {"male": 3, "female": 4},
                    "international_students": 0,
                },
                "notes": "Annual enrollment return submitted ahead of deadline.",
                "company_id": COMPANY_ID,
            }
        )
        self.stdout.write("  Compliance Report CR-0001")

        # ── Academic Transcript for graduated student Akosua ──────────────────
        akosua = students["STU-0005"]
        _, created = AcademicTranscript.objects.get_or_create(
            student=akosua, academic_year=ay_2425, company_id=COMPANY_ID,
            defaults={
                "transcript_number": "TRN-0001",
                "status": "official",
                "cumulative_gpa": "3.72",
                "total_credit_hours": 120,
                "generated_at": datetime.datetime(
                    2024, 6, 10, 9, 0, tzinfo=datetime.timezone.utc
                ),
                "transcript_data": {
                    "2020-2021": {
                        "Fall 2020": [
                            {"course_code": "BA101", "course_name": "Principles of Management",
                             "credit_hours": 3, "section_code": "A",
                             "final_grade": "A-", "grade_points": 3.7},
                        ],
                        "Spring 2021": [
                            {"course_code": "BA201", "course_name": "Financial Accounting",
                             "credit_hours": 3, "section_code": "A",
                             "final_grade": "A", "grade_points": 4.0},
                        ],
                    },
                    "2023-2024": {
                        "Full Year": [
                            {"course_code": "BA301", "course_name": "Marketing Management",
                             "credit_hours": 3, "section_code": "A",
                             "final_grade": "A", "grade_points": 4.0},
                        ],
                    },
                },
                "issued_to": "National Accreditation Board",
                "issued_date": datetime.date(2024, 7, 1),
                "company_id": COMPANY_ID,
            }
        )
        if created:
            self.stdout.write("  Academic Transcript TRN-0001 for Akosua Mensah")

        self.stdout.write(self.style.SUCCESS(
            "\nEducation SIS seed complete: {} programs, {} courses, {} students, "
            "{} applications, {} enrollments, {} scholarship awards, {} fee invoices".format(
                len(programs), len(courses), len(students),
                app_count, enroll_count, 2, fee_count,
            )
        ))
