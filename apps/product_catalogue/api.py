"""
Product Catalogue action endpoints — §6.12.

NOTE: do NOT add `from __future__ import annotations` — Pydantic v2 compat requires
      runtime annotation evaluation.
"""
import uuid
from decimal import Decimal
from typing import List, Optional

from django.shortcuts import get_object_or_404
from ninja import Router, Schema

router = Router(tags=["Product Catalogue"])


# ---------------------------------------------------------------------------
# Shared schemas
# ---------------------------------------------------------------------------

class ActionResponse(Schema):
    ok: bool
    message: str


class VariantAttributeValueIn(Schema):
    attribute_id: str
    value_ids: List[str]


class GenerateVariantsIn(Schema):
    attributes: List[VariantAttributeValueIn]


class GenerateVariantsOut(Schema):
    created_count: int
    skus: List[str]


class BarcodeOut(Schema):
    product_id: str
    sku: str
    name: str
    barcode_type: str


class EffectivePriceIn(Schema):
    price_list_id: str
    qty: Optional[Decimal] = Decimal("1")
    customer_id: Optional[str] = None


class EffectivePriceOut(Schema):
    product_id: str
    price_list_id: str
    qty: Decimal
    rate: Optional[Decimal]
    found: bool


class BundleComponentOut(Schema):
    product_id: str
    sku: str
    name: str
    component_qty: Decimal
    uom_id: Optional[str]
    uom_name: str
    is_optional: bool


# ---------------------------------------------------------------------------
# Generate variants from template
# ---------------------------------------------------------------------------

@router.post(
    "/products/{product_id}/generate-variants",
    response=GenerateVariantsOut,
    summary="Generate variant products from a template",
)
def generate_variants(request, product_id: str, payload: GenerateVariantsIn):
    from apps.product_catalogue.hooks.product import generate_variants as _generate

    attr_map = {item.attribute_id: item.value_ids for item in payload.attributes}
    created = _generate(product_id, attr_map)
    return GenerateVariantsOut(
        created_count=len(created),
        skus=[p.sku for p in created],
    )


# ---------------------------------------------------------------------------
# Barcode lookup
# ---------------------------------------------------------------------------

@router.get(
    "/barcodes/{barcode}",
    response=BarcodeOut,
    summary="Look up a product by barcode",
)
def barcode_lookup(request, barcode: str):
    from apps.product_catalogue.hooks.product import lookup_by_barcode
    from apps.product_catalogue.models import ProductBarcode
    from ninja.errors import HttpError

    product = lookup_by_barcode(barcode)
    if product is None:
        raise HttpError(404, "No product found for barcode '{0}'.".format(barcode))

    # Get barcode_type from the primary record if present
    pb = ProductBarcode.objects.filter(product=product, barcode=barcode).first()
    barcode_type = pb.barcode_type if pb else "internal"

    return BarcodeOut(
        product_id=str(product.id),
        sku=product.sku,
        name=product.name,
        barcode_type=barcode_type,
    )


# ---------------------------------------------------------------------------
# Effective price resolution
# ---------------------------------------------------------------------------

@router.post(
    "/products/{product_id}/effective-price",
    response=EffectivePriceOut,
    summary="Resolve the effective price for a product from a price list",
)
def effective_price(request, product_id: str, payload: EffectivePriceIn):
    from apps.product_catalogue.hooks.product import get_effective_price

    qty = payload.qty or Decimal("1")
    rate = get_effective_price(
        product_id=product_id,
        price_list_id=payload.price_list_id,
        qty=qty,
        customer_id=payload.customer_id,
    )
    return EffectivePriceOut(
        product_id=product_id,
        price_list_id=payload.price_list_id,
        qty=qty,
        rate=rate,
        found=rate is not None,
    )


# ---------------------------------------------------------------------------
# Bundle expansion
# ---------------------------------------------------------------------------

@router.get(
    "/products/{product_id}/expand-bundle",
    response=List[BundleComponentOut],
    summary="Expand a bundle product into its component list",
)
def expand_bundle(request, product_id: str, qty: Optional[Decimal] = None):
    from apps.product_catalogue.hooks.product import expand_bundle as _expand
    from ninja.errors import HttpError

    qty = qty or Decimal("1")
    try:
        components = _expand(product_id, qty=qty)
    except ValueError as exc:
        raise HttpError(400, str(exc))

    return [
        BundleComponentOut(
            product_id=c["product_id"],
            sku=c["sku"],
            name=c["name"],
            component_qty=c["component_qty"],
            uom_id=c["uom_id"],
            uom_name=c["uom_name"],
            is_optional=c["is_optional"],
        )
        for c in components
    ]


# ---------------------------------------------------------------------------
# Category defaults inheritance (on-demand for a product)
# ---------------------------------------------------------------------------

@router.post(
    "/products/{product_id}/inherit-category-defaults",
    response=ActionResponse,
    summary="Fill in GL/tax/valuation defaults from the product category tree",
)
def inherit_category_defaults(request, product_id: str):
    from apps.product_catalogue.hooks.product import inherit_category_defaults as _inherit
    from apps.product_catalogue.models import Product
    from ninja.errors import HttpError

    product = get_object_or_404(Product, id=product_id)
    _inherit(product)
    product.save()
    return ActionResponse(ok=True, message="Category defaults applied to product {0}.".format(product.sku))
