"""Healthcare HIS action endpoints."""
from uuid import UUID

from django.shortcuts import get_object_or_404
from ninja import Router

from apps.healthcare_his.models import Appointment, Encounter, InsuranceClaim
from core.platform_api.security import AuthBearer

router = Router(tags=["Healthcare HIS Actions"], auth=AuthBearer())


@router.post("/appointments/{appointment_id}/confirm")
def confirm_appointment(request, appointment_id: UUID):
    appointment = get_object_or_404(Appointment, pk=appointment_id)
    if appointment.status != "Scheduled":
        return {"error": "Only Scheduled appointments can be confirmed."}
    from apps.healthcare_his.hooks.patient import confirm_appointment as do_confirm
    do_confirm(appointment)
    appointment.save()
    return {"status": appointment.status}


@router.post("/appointments/{appointment_id}/check-in")
def check_in_patient(request, appointment_id: UUID):
    appointment = get_object_or_404(Appointment, pk=appointment_id)
    if appointment.status != "Confirmed":
        return {"error": "Only Confirmed appointments can check in."}
    from apps.healthcare_his.hooks.patient import check_in_patient as do_check_in
    do_check_in(appointment)
    appointment.save()
    return {"status": appointment.status}


@router.post("/appointments/{appointment_id}/complete")
def complete_appointment(request, appointment_id: UUID):
    appointment = get_object_or_404(Appointment, pk=appointment_id)
    if appointment.status not in ("Checked In", "In Progress"):
        return {"error": "Appointment must be Checked In or In Progress to complete."}
    from apps.healthcare_his.hooks.patient import complete_appointment as do_complete
    do_complete(appointment)
    appointment.save()
    return {"status": appointment.status}


@router.post("/appointments/{appointment_id}/cancel")
def cancel_appointment(request, appointment_id: UUID):
    appointment = get_object_or_404(Appointment, pk=appointment_id)
    if appointment.status in ("Completed", "Cancelled"):
        return {"error": f"Cannot cancel a {appointment.status} appointment."}
    appointment.status = "Cancelled"
    appointment.save()
    return {"status": appointment.status}
