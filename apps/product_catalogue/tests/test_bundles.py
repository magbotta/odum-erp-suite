"""Tests for bundle expansion."""
import uuid
from decimal import Decimal

from django.test import TestCase

from apps.product_catalogue.models import Product, ProductBundleComponent
from apps.product_catalogue.hooks.product import expand_bundle

COMPANY_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _product(sku, ptype="stockable"):
    return Product.objects.create(
        sku=sku, name=sku, product_type=ptype, company_id=COMPANY_ID
    )


class ExpandBundleTest(TestCase):

    def test_expand_returns_all_components(self):
        bundle = _product("KIT-001", "bundle")
        c1 = _product("COMP-A")
        c2 = _product("COMP-B")
        ProductBundleComponent.objects.create(
            bundle=bundle, component=c1, qty=Decimal("2"), company_id=COMPANY_ID
        )
        ProductBundleComponent.objects.create(
            bundle=bundle, component=c2, qty=Decimal("1"), company_id=COMPANY_ID
        )

        result = expand_bundle(str(bundle.id))

        self.assertEqual(len(result), 2)
        skus = {r["sku"] for r in result}
        self.assertIn("COMP-A", skus)
        self.assertIn("COMP-B", skus)

    def test_qty_is_scaled(self):
        bundle = _product("KIT-002", "bundle")
        comp = _product("COMP-C")
        ProductBundleComponent.objects.create(
            bundle=bundle, component=comp, qty=Decimal("3"), company_id=COMPANY_ID
        )

        result = expand_bundle(str(bundle.id), qty=Decimal("2"))

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["component_qty"], Decimal("6"))

    def test_optional_flag_preserved(self):
        bundle = _product("KIT-003", "bundle")
        comp = _product("COMP-D")
        ProductBundleComponent.objects.create(
            bundle=bundle, component=comp, qty=Decimal("1"),
            is_optional=True, company_id=COMPANY_ID
        )

        result = expand_bundle(str(bundle.id))
        self.assertTrue(result[0]["is_optional"])

    def test_raises_if_not_bundle(self):
        product = _product("NOT-BUNDLE", "stockable")
        with self.assertRaises(ValueError):
            expand_bundle(str(product.id))

    def test_raises_if_not_found(self):
        with self.assertRaises(ValueError):
            expand_bundle(str(uuid.uuid4()))
