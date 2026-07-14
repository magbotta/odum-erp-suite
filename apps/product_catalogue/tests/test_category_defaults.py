"""Tests for category GL/valuation default inheritance."""
import uuid

from django.test import TestCase

from apps.product_catalogue.models import Product, ProductCategory
from apps.product_catalogue.hooks.product import inherit_category_defaults

COMPANY_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
INCOME_ACCOUNT = uuid.uuid4()
EXPENSE_ACCOUNT = uuid.uuid4()
STOCK_ACCOUNT = uuid.uuid4()
TAX_TEMPLATE = uuid.uuid4()


class CategoryDefaultsTest(TestCase):

    def _make_category(self, name, parent=None, income_id=None, valuation="fifo"):
        return ProductCategory.objects.create(
            name=name,
            parent=parent,
            default_income_account_id=income_id,
            default_valuation_method=valuation,
            company_id=COMPANY_ID,
        )

    def _make_product(self, category):
        return Product.objects.create(
            sku="PROD-{}".format(uuid.uuid4().hex[:6]),
            name="Test Product",
            product_type="stockable",
            category=category,
            company_id=COMPANY_ID,
        )

    def test_product_inherits_income_account_from_category(self):
        cat = self._make_category("Electronics", income_id=INCOME_ACCOUNT)
        product = self._make_product(cat)

        self.assertIsNone(product.income_account_id)
        inherit_category_defaults(product)
        self.assertEqual(product.income_account_id, INCOME_ACCOUNT)

    def test_inherit_walks_up_tree(self):
        root = self._make_category("Root", income_id=INCOME_ACCOUNT)
        child = self._make_category("Child", parent=root, income_id=None)
        product = self._make_product(child)

        inherit_category_defaults(product)
        self.assertEqual(product.income_account_id, INCOME_ACCOUNT)

    def test_existing_product_field_not_overwritten(self):
        cat = self._make_category("Cat", income_id=INCOME_ACCOUNT)
        existing_id = uuid.uuid4()
        product = Product.objects.create(
            sku="PROD-OVERRIDE",
            name="Already Set",
            product_type="stockable",
            category=cat,
            income_account_id=existing_id,
            company_id=COMPANY_ID,
        )

        inherit_category_defaults(product)
        self.assertEqual(product.income_account_id, existing_id)

    def test_effective_valuation_method_returns_fifo_default(self):
        cat = self._make_category("NoValuation")
        self.assertEqual(cat.effective_valuation_method(), "fifo")

    def test_effective_valuation_method_walks_up_tree(self):
        root = self._make_category("Root", valuation="moving_avg")
        child = ProductCategory.objects.create(
            name="Child", parent=root, default_valuation_method="", company_id=COMPANY_ID
        )
        self.assertEqual(child.effective_valuation_method(), "moving_avg")

    def test_no_category_does_nothing(self):
        product = Product.objects.create(
            sku="PROD-NOCAT",
            name="No Category",
            product_type="stockable",
            company_id=COMPANY_ID,
        )
        inherit_category_defaults(product)
        self.assertIsNone(product.income_account_id)
