"""BOM hooks: numbering, cost roll-up, and activation (§7)."""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.manufacturing.models import BillOfMaterials


def set_bom_number(bom: "BillOfMaterials") -> None:
    if not bom.bom_number:
        from core.numbering.service import get_next_number
        bom.bom_number = get_next_number("BOM", company_id=bom.company_id)


def compute_bom_cost(bom: "BillOfMaterials") -> None:
    """Roll up raw material + operation costs onto the BOM header."""
    raw_cost = Decimal("0")
    for bom_item in bom.bom_items.filter(is_deleted=False):
        raw_cost += bom_item.rate * bom_item.quantity * (
            1 + bom_item.scrap_pct / 100
        )

    op_cost = Decimal("0")
    for operation in bom.operations.filter(is_deleted=False):
        op_cost += operation.operating_cost

    bom.raw_material_cost = raw_cost
    bom.operating_cost = op_cost
    bom.total_cost = raw_cost + op_cost
    bom.save(update_fields=["raw_material_cost", "operating_cost", "total_cost"])


def activate_bom(bom: "BillOfMaterials") -> None:
    """
    When activating a BOM, deactivate all other active BOMs for the same item
    if is_default is True, so there is at most one default BOM per item.
    """
    from apps.manufacturing.models import BillOfMaterials as BOM
    if bom.is_default:
        BOM.objects.filter(
            item=bom.item, is_default=True, is_deleted=False
        ).exclude(pk=bom.pk).update(is_default=False)
