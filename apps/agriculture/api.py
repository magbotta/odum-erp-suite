"""Agriculture action endpoints."""
from uuid import UUID

from django.shortcuts import get_object_or_404
from ninja import Router

from apps.agriculture.models import CropCycle, HarvestRecord
from core.platform_api.security import AuthBearer

router = Router(tags=["Agriculture Actions"], auth=AuthBearer())


@router.post("/crop-cycles/{cycle_id}/plant")
def record_planting(request, cycle_id: UUID):
    cycle = get_object_or_404(CropCycle, pk=cycle_id)
    if cycle.status != "planned":
        return {"error": "Only Planned crop cycles can be moved to Planted."}
    from apps.agriculture.hooks.crop_cycle import record_planting as do_plant
    do_plant(cycle)
    cycle.save()
    return {"status": cycle.status}


@router.post("/crop-cycles/{cycle_id}/harvest")
def record_harvest(request, cycle_id: UUID):
    cycle = get_object_or_404(CropCycle, pk=cycle_id)
    if cycle.status not in ("planted", "growing"):
        return {"error": "Crop cycle must be Planted or Growing to harvest."}
    from apps.agriculture.hooks.crop_cycle import record_harvest as do_harvest
    do_harvest(cycle)
    cycle.save()
    from apps.agriculture.hooks.crop_cycle import post_harvest_to_warehouse
    post_harvest_to_warehouse(cycle)
    return {"status": cycle.status}


@router.post("/crop-cycles/{cycle_id}/fail")
def mark_failed(request, cycle_id: UUID):
    cycle = get_object_or_404(CropCycle, pk=cycle_id)
    if cycle.status in ("harvested", "failed"):
        return {"error": f"Cannot mark a {cycle.status} cycle as failed."}
    cycle.status = "failed"
    cycle.save()
    return {"status": cycle.status}
