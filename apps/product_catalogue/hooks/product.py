"""
Product Catalogue business-logic hooks.

  inherit_category_defaults  — fill in GL/tax/valuation from category tree
  generate_variants          — create variant Products from a template + attribute matrix
  expand_bundle              — return component list for a bundle/kit
  lookup_by_barcode          — find a Product by any registered barcode
  get_effective_price        — resolve the best ProductPrice row from a PriceList
"""
from __future__ import annotations

import itertools
import logging
from decimal import Decimal
from typing import Dict, List, Optional
import uuid

logger = logging.getLogger(__name__)


def inherit_category_defaults(product) -> None:
    """
    Fill in product-level GL/tax/valuation defaults from the category tree.
    Only sets fields that are currently null — never overwrites an explicit value.
    Intended to run before_save when category changes.
    """
    if not product.category_id:
        return

    try:
        category = product.category
    except Exception:
        return

    if not product.income_account_id:
        product.income_account_id = category.effective_income_account_id()

    if not product.expense_account_id:
        node = category
        while node is not None:
            if node.default_expense_account_id:
                product.expense_account_id = node.default_expense_account_id
                break
            node = node.parent

    if not product.stock_account_id:
        node = category
        while node is not None:
            if node.default_stock_account_id:
                product.stock_account_id = node.default_stock_account_id
                break
            node = node.parent

    if not product.tax_template_id:
        node = category
        while node is not None:
            if node.default_tax_template_id:
                product.tax_template_id = node.default_tax_template_id
                break
            node = node.parent


def generate_variants(template_id: str, attribute_value_map: Dict[str, List[str]]) -> List:
    """
    Generate variant Product records from a template product and an attribute matrix.

    attribute_value_map: {attribute_id: [attribute_value_id, ...], ...}

    Returns a list of newly created Product records (variants).
    Each variant inherits all fields from the template and gets a generated SKU:
      <template_sku>-<attr_abbr_1>-<attr_abbr_2>-...

    Existing variants with a matching attribute combination are skipped (idempotent).
    """
    from apps.product_catalogue.models import (
        Product, ProductAttribute, ProductAttributeValue, ProductVariantAttribute
    )

    try:
        template = Product.objects.get(id=template_id, is_template=True)
    except Product.DoesNotExist:
        raise ValueError("Product {0} not found or is not a template.".format(template_id))

    # Build the cartesian product of all attribute values
    attr_ids = list(attribute_value_map.keys())
    value_id_lists = [attribute_value_map[a] for a in attr_ids]
    combinations = list(itertools.product(*value_id_lists))

    created = []
    for combo in combinations:
        # combo is a tuple of attribute_value_ids, one per attribute
        attr_values = []
        for attr_id, val_id in zip(attr_ids, combo):
            try:
                av = ProductAttributeValue.objects.get(id=val_id, attribute_id=attr_id)
                attr_values.append(av)
            except ProductAttributeValue.DoesNotExist:
                logger.warning("ProductAttributeValue %s not found, skipping.", val_id)
                break
        else:
            # All attribute values resolved — build variant SKU
            abbrevs = [av.abbreviation or av.value[:3].upper() for av in attr_values]
            variant_sku = "{0}-{1}".format(template.sku, "-".join(abbrevs))

            variant, is_new = Product.objects.get_or_create(
                sku=variant_sku,
                defaults=dict(
                    name="{0} ({1})".format(template.name, ", ".join(av.value for av in attr_values)),
                    description=template.description,
                    category=template.category,
                    product_type=template.product_type,
                    lifecycle_status=template.lifecycle_status,
                    base_uom_id=template.base_uom_id,
                    base_uom_name=template.base_uom_name,
                    is_template=False,
                    template=template,
                    base_price=template.base_price,
                    standard_cost=template.standard_cost,
                    currency=template.currency,
                    income_account_id=template.income_account_id,
                    expense_account_id=template.expense_account_id,
                    stock_account_id=template.stock_account_id,
                    tax_template_id=template.tax_template_id,
                    is_sellable=template.is_sellable,
                    is_purchasable=template.is_purchasable,
                    show_on_website=template.show_on_website,
                    show_on_pos=template.show_on_pos,
                    show_on_mobile_app=template.show_on_mobile_app,
                    is_active=template.is_active,
                    company_id=template.company_id,
                ),
            )

            if is_new:
                for attr_val in attr_values:
                    ProductVariantAttribute.objects.get_or_create(
                        product=variant,
                        attribute=attr_val.attribute,
                        defaults={"value": attr_val, "company_id": template.company_id},
                    )
                created.append(variant)
                logger.info("Generated variant %s from template %s.", variant_sku, template.sku)

    return created


def expand_bundle(product_id: str, qty: Decimal = Decimal("1")) -> List[Dict]:
    """
    Return the full component list for a bundle/kit product, scaled by qty.

    Returns a list of dicts:
      [{product_id, sku, name, component_qty, uom_id, uom_name, is_optional}, ...]

    Raises ValueError if product_id is not a BUNDLE type.
    """
    from apps.product_catalogue.models import Product, ProductBundleComponent

    try:
        bundle = Product.objects.get(id=product_id)
    except Product.DoesNotExist:
        raise ValueError("Product {0} not found.".format(product_id))

    if bundle.product_type != Product.ProductType.BUNDLE:
        raise ValueError(
            "Product {0} is type '{1}', not 'bundle'.".format(bundle.sku, bundle.product_type)
        )

    components = ProductBundleComponent.objects.select_related("component").filter(
        bundle=bundle, is_deleted=False
    )

    return [
        {
            "product_id": str(c.component_id),
            "sku": c.component.sku,
            "name": c.component.name,
            "component_qty": c.qty * qty,
            "uom_id": str(c.uom_id) if c.uom_id else None,
            "uom_name": c.uom_name,
            "is_optional": c.is_optional,
        }
        for c in components
    ]


def lookup_by_barcode(barcode: str) -> Optional[object]:
    """Return the Product matching any registered barcode, or None."""
    from apps.product_catalogue.models import Product, ProductBarcode

    try:
        pb = ProductBarcode.objects.select_related("product").get(
            barcode=barcode, is_deleted=False
        )
        return pb.product
    except ProductBarcode.DoesNotExist:
        # Fall back: check warehouse.Item.barcode for backward compatibility
        try:
            from apps.warehouse.models import Item
            item = Item.objects.get(barcode=barcode, is_deleted=False)
            if item.product_id:
                return Product.objects.get(id=item.product_id)
        except Exception:
            pass
    return None


def get_effective_price(product_id: str, price_list_id: str, qty: Decimal = Decimal("1"),
                        customer_id: Optional[str] = None) -> Optional[Decimal]:
    """
    Resolve the best ProductPrice for a product in a given price list.

    Applies tiered pricing: finds the row with the highest min_qty <= qty.
    Customer-specific rows take precedence over general rows when present.
    Returns None if no price row exists.
    """
    from apps.product_catalogue.models import ProductPrice

    qs = ProductPrice.objects.filter(
        price_list_id=price_list_id,
        product_id=product_id,
        min_qty__lte=qty,
        is_deleted=False,
    ).order_by("-min_qty")

    # Customer-specific row wins if present
    if customer_id:
        customer_row = qs.filter(customer_id=customer_id).first()
        if customer_row:
            return customer_row.rate

    # General row
    general_row = qs.filter(customer_id__isnull=True).first()
    if general_row:
        return general_row.rate

    return None
