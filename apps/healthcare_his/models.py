"""
Healthcare / Hospital Information System models (§7).
HIPAA/GDPR-aligned: PHI fields are flagged for field-level encryption (§13).
Depends on: Warehouse (pharmacy/supplies), Accounting (billing), HRM (clinical staff).
"""
from __future__ import annotations

from django.db import models

from core.metadata_engine.base_entity import BaseEntity


class Ward(BaseEntity):
    """A hospital ward / unit (e.g. ICU, Maternity, General Medical)."""

    name = models.CharField(max_length=150)
    ward_type = models.CharField(max_length=50, blank=True)
    total_beds = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta(BaseEntity.Meta):
        db_table = "his_wards"

    def __str__(self) -> str:
        return self.name


class Bed(BaseEntity):
    """A bed within a Ward — tracked for ADT (Admit/Discharge/Transfer)."""

    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        OCCUPIED = "occupied", "Occupied"
        HOUSEKEEPING = "housekeeping", "Housekeeping"
        MAINTENANCE = "maintenance", "Maintenance"

    ward = models.ForeignKey(Ward, on_delete=models.CASCADE, related_name="beds")
    bed_number = models.CharField(max_length=20)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.AVAILABLE)

    class Meta(BaseEntity.Meta):
        db_table = "his_beds"
        unique_together = [("ward", "bed_number")]

    def __str__(self) -> str:
        return f"{self.ward} / {self.bed_number}"


class Patient(BaseEntity):
    """
    A patient's demographic and identity record (§7).
    PHI fields: date_of_birth, blood_type, allergies — flagged for encryption (§13).
    """

    class Gender(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"
        OTHER = "other", "Other"
        UNKNOWN = "unknown", "Unknown"

    patient_number = models.CharField(max_length=50, unique=True, db_index=True)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    date_of_birth = models.DateField(null=True, blank=True)  # PHI — encrypt
    gender = models.CharField(max_length=10, choices=Gender.choices, default=Gender.UNKNOWN)
    blood_type = models.CharField(max_length=5, blank=True)  # PHI
    phone = models.CharField(max_length=32, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)  # PHI
    emergency_contact_name = models.CharField(max_length=255, blank=True)
    emergency_contact_phone = models.CharField(max_length=32, blank=True)
    allergies = models.TextField(blank=True)  # PHI
    # Insurance
    insurance_provider = models.CharField(max_length=255, blank=True)
    insurance_policy_number = models.CharField(max_length=100, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "his_patients"

    def __str__(self) -> str:
        return f"{self.patient_number} — {self.first_name} {self.last_name}"


class Appointment(BaseEntity):
    """An outpatient appointment or scheduled procedure (§7)."""

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        CONFIRMED = "confirmed", "Confirmed"
        CHECKED_IN = "checked_in", "Checked In"
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        NO_SHOW = "no_show", "No Show"

    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name="appointments")
    appointment_number = models.CharField(max_length=50, blank=True, db_index=True)
    scheduled_at = models.DateTimeField()
    duration_minutes = models.PositiveSmallIntegerField(default=30)
    department = models.CharField(max_length=150, blank=True)
    physician_employee_id = models.UUIDField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.SCHEDULED
    )
    reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "his_appointments"

    def __str__(self) -> str:
        return f"{self.appointment_number} — {self.patient}"


class Encounter(BaseEntity):
    """
    A clinical encounter / visit (inpatient admission or outpatient visit).
    The core record that links to clinical orders, nursing notes, and billing.
    """

    class EncounterType(models.TextChoices):
        OUTPATIENT = "outpatient", "Outpatient"
        INPATIENT = "inpatient", "Inpatient"
        EMERGENCY = "emergency", "Emergency"
        DAY_SURGERY = "day_surgery", "Day Surgery"

    class Status(models.TextChoices):
        ADMITTED = "admitted", "Admitted"
        IN_PROGRESS = "in_progress", "In Progress"
        DISCHARGED = "discharged", "Discharged"
        TRANSFERRED = "transferred", "Transferred"

    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name="encounters")
    encounter_number = models.CharField(max_length=50, blank=True, db_index=True)
    encounter_type = models.CharField(
        max_length=20, choices=EncounterType.choices, default=EncounterType.OUTPATIENT
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ADMITTED
    )
    admitted_at = models.DateTimeField()
    discharged_at = models.DateTimeField(null=True, blank=True)
    bed = models.ForeignKey(
        Bed, null=True, blank=True, on_delete=models.SET_NULL, related_name="encounters"
    )
    attending_physician_id = models.UUIDField(null=True, blank=True)
    admitting_diagnosis = models.TextField(blank=True)  # PHI
    discharge_diagnosis = models.TextField(blank=True)  # PHI
    discharge_notes = models.TextField(blank=True)
    # Appointment that led to this encounter
    appointment = models.ForeignKey(
        Appointment, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="encounters",
    )

    class Meta(BaseEntity.Meta):
        db_table = "his_encounters"

    def __str__(self) -> str:
        return f"{self.encounter_number} — {self.patient}"


class ClinicalOrder(BaseEntity):
    """
    A physician order (medication, lab, imaging, procedure) within an Encounter.
    CPOE with decision-support hooks.
    """

    class OrderType(models.TextChoices):
        MEDICATION = "medication", "Medication"
        LAB = "lab", "Laboratory"
        IMAGING = "imaging", "Imaging / Radiology"
        PROCEDURE = "procedure", "Procedure"
        DIET = "diet", "Diet / Nutrition"
        NURSING = "nursing", "Nursing"

    class Status(models.TextChoices):
        ORDERED = "ordered", "Ordered"
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    encounter = models.ForeignKey(Encounter, on_delete=models.CASCADE, related_name="orders")
    order_type = models.CharField(max_length=20, choices=OrderType.choices)
    description = models.CharField(max_length=500)
    ordered_by_employee_id = models.UUIDField(null=True, blank=True)
    ordered_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ORDERED)
    instructions = models.TextField(blank=True)
    priority = models.CharField(
        max_length=20,
        choices=[("routine", "Routine"), ("urgent", "Urgent"), ("stat", "STAT")],
        default="routine",
    )

    class Meta(BaseEntity.Meta):
        db_table = "his_clinical_orders"

    def __str__(self) -> str:
        return f"{self.encounter} — {self.order_type}: {self.description}"


class Prescription(BaseEntity):
    """A medication order / eMAR entry — cross-app Warehouse item (drug) (§7)."""

    class Status(models.TextChoices):
        ORDERED = "ordered", "Ordered"
        DISPENSED = "dispensed", "Dispensed"
        ADMINISTERED = "administered", "Administered"
        CANCELLED = "cancelled", "Cancelled"

    encounter = models.ForeignKey(Encounter, on_delete=models.CASCADE, related_name="prescriptions")
    clinical_order = models.ForeignKey(
        ClinicalOrder, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="prescriptions",
    )
    drug_item_id = models.UUIDField(help_text="Warehouse Item (drug) UUID")
    drug_name = models.CharField(max_length=255)
    dose = models.CharField(max_length=100)
    route = models.CharField(max_length=50, blank=True)
    frequency = models.CharField(max_length=100, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ORDERED)
    prescribed_by_employee_id = models.UUIDField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "his_prescriptions"

    def __str__(self) -> str:
        return f"{self.encounter} — {self.drug_name} {self.dose}"


class InsuranceClaim(BaseEntity):
    """
    A claim submitted to an insurer for services in an Encounter (§7).
    The Insurance App (§7.6) represents the payer side of this boundary.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        PENDING = "pending", "Pending Review"
        APPROVED = "approved", "Approved"
        DENIED = "denied", "Denied"
        PARTIALLY_PAID = "partially_paid", "Partially Paid"
        PAID = "paid", "Paid"

    encounter = models.ForeignKey(Encounter, on_delete=models.PROTECT, related_name="insurance_claims")
    claim_number = models.CharField(max_length=50, blank=True, db_index=True)
    insurer_name = models.CharField(max_length=255)
    policy_number = models.CharField(max_length=100)
    billed_amount = models.DecimalField(max_digits=19, decimal_places=4)
    approved_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    paid_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    patient_responsibility = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    submitted_at = models.DateTimeField(null=True, blank=True)
    denial_reason = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "his_insurance_claims"

    def __str__(self) -> str:
        return f"{self.claim_number} — {self.encounter}"
