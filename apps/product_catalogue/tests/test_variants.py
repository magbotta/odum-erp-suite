"""Tests for variant generation from a product template."""
import uuid
from decimal import Decimal

from django.test import TestCase

from apps.product_catalogue.models import (
    Product, ProductAttribute, ProductAttributeValue, ProductVariantAttribute,
)
from apps.product_catalogue.hooks.product import generate_variants

COMPANY_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _make_template(sku="TSHIRT-TPL"):
    return Product.objects.create(
        sku=sku,
        name="Classic T-Shirt",
        product_type="stockable",
        lifecycle_status="active",
        is_template=True,
        base_price=Decimal("24.99"),
        currency="USD",
        company_id=COMPANY_ID,
    )


def _make_attr(name, values):
    attr = ProductAttribute.objects.create(
        name=name, attribute_type="select", company_id=COMPANY_ID
    )
    vals = []
    for v, abbr in values:
        av = ProductAttributeValue.objects.create(
            attribute=attr, value=v, abbreviation=abbr, company_id=COMPANY_ID
        )
        vals.append(av)
    return attr, vals


class GenerateVariantsTest(TestCase):

    def test_generates_cartesian_product_of_attributes(self):
        template = _make_template()
        color_attr, colors = _make_attr("Color", [("Black", "BLK"), ("White", "WHT")])
        size_attr, sizes = _make_attr("Size", [("Small", "S"), ("Large", "L")])

        created = generate_variants(
            str(template.id),
            {
                str(color_attr.id): [str(v.id) for v in colors],
                str(size_attr.id): [str(v.id) for v in sizes],
            },
        )

        self.assertEqual(len(created), 4)
        skus = {p.sku for p in created}
        self.assertIn("TSHIRT-TPL-BLK-S", skus)
        self.assertIn("TSHIRT-TPL-BLK-L", skus)
        self.assertIn("TSHIRT-TPL-WHT-S", skus)
        self.assertIn("TSHIRT-TPL-WHT-L", skus)

    def test_variants_inherit_template_fields(self):
        template = _make_template()
        color_attr, colors = _make_attr("Color", [("Blue", "BLU")])

        created = generate_variants(
            str(template.id),
            {str(color_attr.id): [str(colors[0].id)]},
        )

        variant = created[0]
        self.assertFalse(variant.is_template)
        self.assertEqual(variant.template_id, template.id)
        self.assertEqual(variant.base_price, template.base_price)
        self.assertEqual(variant.currency, template.currency)
        self.assertEqual(variant.company_id, COMPANY_ID)

    def test_idempotent_does_not_duplicate(self):
        template = _make_template()
        color_attr, colors = _make_attr("Color", [("Red", "RED")])

        attr_map = {str(color_attr.id): [str(colors[0].id)]}
        first = generate_variants(str(template.id), attr_map)
        second = generate_variants(str(template.id), attr_map)

        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 0)  # already exists
        self.assertEqual(Product.objects.filter(template=template).count(), 1)

    def test_variant_attributes_are_assigned(self):
        template = _make_template()
        size_attr, sizes = _make_attr("Size", [("Medium", "M")])

        created = generate_variants(
            str(template.id),
            {str(size_attr.id): [str(sizes[0].id)]},
        )

        variant = created[0]
        va = ProductVariantAttribute.objects.filter(product=variant).first()
        self.assertIsNotNone(va)
        self.assertEqual(va.attribute, size_attr)
        self.assertEqual(va.value, sizes[0])

    def test_raises_if_not_template(self):
        product = Product.objects.create(
            sku="STANDALONE", name="Standalone", product_type="stockable",
            is_template=False, company_id=COMPANY_ID
        )
        with self.assertRaises(ValueError):
            generate_variants(str(product.id), {})
