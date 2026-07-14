"""Tests for ProductUOMConversion math."""
import uuid
from decimal import Decimal

from django.test import TestCase

from apps.product_catalogue.models import Product, ProductUOMConversion

COMPANY_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
UOM_EACH = uuid.uuid4()
UOM_BOX = uuid.uuid4()


def _make_product(sku="ITEM-001"):
    return Product.objects.create(
        sku=sku, name="Test Item", product_type="stockable",
        company_id=COMPANY_ID
    )


class ProductUOMConversionTest(TestCase):

    def _make_conversion(self, product, factor="12"):
        return ProductUOMConversion.objects.create(
            product=product,
            from_uom_id=UOM_BOX,
            from_uom_name="Box",
            to_uom_id=UOM_EACH,
            to_uom_name="Each",
            conversion_factor=Decimal(factor),
            company_id=COMPANY_ID,
        )

    def test_convert_box_to_each(self):
        product = _make_product()
        conv = self._make_conversion(product, "12")
        result = conv.convert(Decimal("3"))
        self.assertEqual(result, Decimal("36"))

    def test_convert_fractional(self):
        product = _make_product("ITEM-002")
        conv = self._make_conversion(product, "2.5")
        result = conv.convert(Decimal("4"))
        self.assertEqual(result, Decimal("10.0"))

    def test_convert_one_unit(self):
        product = _make_product("ITEM-003")
        conv = self._make_conversion(product, "6")
        result = conv.convert(Decimal("1"))
        self.assertEqual(result, Decimal("6"))

    def test_unique_together_enforced(self):
        from django.db import IntegrityError
        product = _make_product("ITEM-004")
        self._make_conversion(product)
        with self.assertRaises(IntegrityError):
            ProductUOMConversion.objects.create(
                product=product,
                from_uom_id=UOM_BOX,
                from_uom_name="Box",
                to_uom_id=UOM_EACH,
                to_uom_name="Each",
                conversion_factor=Decimal("24"),
                company_id=COMPANY_ID,
            )
