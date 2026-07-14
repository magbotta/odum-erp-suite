"""
Integration tests: Product <-> warehouse.Item <-> purchasing/sales line items.

Verifies that the product_id UUID soft-link connects a product_catalogue.Product
to a warehouse.Item, and that purchasing and sales line items carry the same
product_id through the full order flow.
"""
import uuid
from decimal import Decimal

from django.test import TestCase

from apps.product_catalogue.models import Product, PriceList, ProductPrice
from apps.product_catalogue.hooks.product import get_effective_price

COMPANY_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class ProductWarehouseItemLinkTest(TestCase):

    def test_warehouse_item_can_soft_link_to_product(self):
        from apps.warehouse.models import Item

        product = Product.objects.create(
            sku="INT-PROD-001",
            name="Integration Product",
            product_type="stockable",
            lifecycle_status="active",
            company_id=COMPANY_ID,
        )

        item = Item.objects.create(
            item_code="INT-ITEM-001",
            item_name="Integration Item",
            is_stock_item=True,
            product_id=product.id,
            company_id=COMPANY_ID,
        )

        reloaded = Item.objects.get(pk=item.pk)
        self.assertEqual(reloaded.product_id, product.id)

    def test_purchasing_line_item_carries_product_id(self):
        from apps.purchasing.models import PurchaseRequisition, PurchaseRequisitionItem
        import datetime

        product = Product.objects.create(
            sku="INT-PROD-002",
            name="Purchase Product",
            product_type="stockable",
            company_id=COMPANY_ID,
        )

        pr = PurchaseRequisition.objects.create(
            requisition_number="PR-INT-001",
            posting_date=datetime.date.today(),
            status="draft",
            company_id=COMPANY_ID,
        )

        item_uuid = uuid.uuid4()
        pri = PurchaseRequisitionItem.objects.create(
            requisition=pr,
            item_id=item_uuid,
            item_code="INT-ITEM-002",
            item_name="Purchase Product",
            qty=Decimal("10"),
            product_id=product.id,
            company_id=COMPANY_ID,
        )

        reloaded = PurchaseRequisitionItem.objects.get(pk=pri.pk)
        self.assertEqual(reloaded.product_id, product.id)
        self.assertEqual(reloaded.item_id, item_uuid)


class PriceResolutionTest(TestCase):

    def _make_product(self, sku):
        return Product.objects.create(
            sku=sku, name=sku, product_type="stockable",
            base_price=Decimal("100.00"), company_id=COMPANY_ID
        )

    def _make_price_list(self, name):
        return PriceList.objects.create(
            name=name, currency="USD", is_selling=True, company_id=COMPANY_ID
        )

    def test_get_effective_price_returns_correct_tier(self):
        product = self._make_product("PRICE-TEST-001")
        pl = self._make_price_list("Test PL")

        ProductPrice.objects.create(
            price_list=pl, product=product,
            min_qty=Decimal("0"), rate=Decimal("100.00"), company_id=COMPANY_ID
        )
        ProductPrice.objects.create(
            price_list=pl, product=product,
            min_qty=Decimal("10"), rate=Decimal("90.00"), company_id=COMPANY_ID
        )
        ProductPrice.objects.create(
            price_list=pl, product=product,
            min_qty=Decimal("50"), rate=Decimal("80.00"), company_id=COMPANY_ID
        )

        self.assertEqual(
            get_effective_price(str(product.id), str(pl.id), qty=Decimal("5")),
            Decimal("100.00"),
        )
        self.assertEqual(
            get_effective_price(str(product.id), str(pl.id), qty=Decimal("10")),
            Decimal("90.00"),
        )
        self.assertEqual(
            get_effective_price(str(product.id), str(pl.id), qty=Decimal("100")),
            Decimal("80.00"),
        )

    def test_get_effective_price_returns_none_if_no_price(self):
        product = self._make_product("PRICE-TEST-002")
        pl = self._make_price_list("Empty PL")

        result = get_effective_price(str(product.id), str(pl.id), qty=Decimal("1"))
        self.assertIsNone(result)

    def test_customer_specific_price_wins(self):
        product = self._make_product("PRICE-TEST-003")
        pl = self._make_price_list("Customer PL")
        customer_id = uuid.uuid4()

        ProductPrice.objects.create(
            price_list=pl, product=product,
            min_qty=Decimal("0"), rate=Decimal("100.00"), company_id=COMPANY_ID
        )
        ProductPrice.objects.create(
            price_list=pl, product=product,
            min_qty=Decimal("0"), rate=Decimal("75.00"),
            customer_id=customer_id, company_id=COMPANY_ID
        )

        price = get_effective_price(
            str(product.id), str(pl.id),
            qty=Decimal("1"), customer_id=str(customer_id)
        )
        self.assertEqual(price, Decimal("75.00"))

    def test_general_price_used_when_no_customer_match(self):
        product = self._make_product("PRICE-TEST-004")
        pl = self._make_price_list("Mixed PL")
        other_customer = uuid.uuid4()

        ProductPrice.objects.create(
            price_list=pl, product=product,
            min_qty=Decimal("0"), rate=Decimal("100.00"), company_id=COMPANY_ID
        )
        ProductPrice.objects.create(
            price_list=pl, product=product,
            min_qty=Decimal("0"), rate=Decimal("75.00"),
            customer_id=other_customer, company_id=COMPANY_ID
        )

        another_customer = uuid.uuid4()
        price = get_effective_price(
            str(product.id), str(pl.id),
            qty=Decimal("1"), customer_id=str(another_customer)
        )
        self.assertEqual(price, Decimal("100.00"))
