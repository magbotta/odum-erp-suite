"""Agriculture hooks — crop cycle and harvest posting."""
import uuid
from decimal import Decimal

from django.utils import timezone

from apps.agriculture.models import CropCycle, HarvestRecord


def record_planting(cycle: CropCycle) -> None:
    cycle.status = "planted"


def update_growth(cycle: CropCycle) -> None:
    cycle.status = "growing"


def record_harvest(cycle: CropCycle) -> None:
    cycle.status = "harvested"
    if not cycle.actual_harvest_date:
        cycle.actual_harvest_date = timezone.now().date()


def post_harvest_to_warehouse(cycle: CropCycle) -> None:
    """
    On harvest completion, create a StockEntry for the harvested yield.
    Delegates to Warehouse via cross-app service call.
    In production: call warehouse.service.receive_stock(item_id, qty, warehouse_id).
    """
    # Only post if we have a harvest record with an actual yield
    harvest = HarvestRecord.objects.filter(crop_cycle=cycle).first()
    if harvest and harvest.storage_warehouse_id and not harvest.stock_entry_id:
        harvest.stock_entry_id = uuid.uuid4()  # placeholder — real call goes to Warehouse
        harvest.save(update_fields=["stock_entry_id"])
