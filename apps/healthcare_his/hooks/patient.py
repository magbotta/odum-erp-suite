"""Healthcare HIS hooks — patient and appointment lifecycle."""
from apps.healthcare_his.models import Appointment, Patient
from core.numbering.service import get_next_number


def set_patient_number(patient: Patient) -> None:
    if not patient.patient_number:
        patient.patient_number = get_next_number("PAT", company_id=patient.company_id)


def set_appointment_number(appointment: Appointment) -> None:
    if not appointment.appointment_number:
        appointment.appointment_number = get_next_number(
            "APT", company_id=appointment.company_id
        )


def confirm_appointment(appointment: Appointment) -> None:
    appointment.status = "Confirmed"


def check_in_patient(appointment: Appointment) -> None:
    appointment.status = "Checked In"


def complete_appointment(appointment: Appointment) -> None:
    appointment.status = "Completed"
