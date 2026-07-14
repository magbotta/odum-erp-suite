"""Product Catalogue models — §6.12 shared Product/Item Master.

The canonical product record every other module builds on:
  - ProductCategory: self-referencing hierarchy with GL/tax/valuation defaults
  - Product: SKU, variants, bundles, pricing, visibility, media
  - PriceList / ProductPrice: moved from apps.sales; Sales soft-links by UUID
  - Supporting: ProductAttribute, ProductVariant, ProductBarcode, ProductMedia,
    ProductBundleComponent, ProductUOMConversion

Cross-app note: warehouse.Item is the stock-extension of Product.  It carries
a product_id UUID soft-link back here.  Sales, POS, and Manufacturing continue
to FK to warehouse.Item for fulfilment operations; product identity and pricing
live here.
"""
from __future__ import annotations

from django.db import models

from core.metadata_engine.base_entity import BaseEntity


# ── Category hierarchy ────────────────────────────────────────────────────────

class ProductCategory(BaseEntity):
    """
    Hierarchical product category.  Category-level defaults for GL accounts,
    tax treatment, and valuation method are inherited by every Product in the
    category unless explicitly overridden on the Product itself.
    """

    name = models.CharField(max_length=150)
    parent = models.ForeignKey(
        "self", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="children",
    )
    code = models.CharField(max_length=20, blank=True, db_index=True)
    description = models.TextField(blank=True)

    # Category-level GL defaults (soft links to accounting app)
    default_income_account_id = models.UUIDField(null=True, blank=True)
    default_expense_account_id = models.UUIDField(null=True, blank=True)
    default_stock_account_id = models.UUIDField(null=True, blank=True)
    default_tax_template_id = models.UUIDField(null=True, blank=True)
    default_valuation_method = models.CharField(
        max_length=20, blank=True,
        choices=[
            ("fifo", "FIFO"),
            ("moving_avg", "Moving Average"),
            ("standard", "Standard Cost"),
        ],
    )

    class Meta(BaseEntity.Meta):
        db_table = "catalogue_product_categories"
        verbose_name = "Product Category"
        verbose_name_plural = "Product Categories"

    def __str__(self) -> str:
        return self.name

    def effective_income_account_id(self):
        """Walk up the tree returning the first non-null income_account_id."""
        node = self
        while node is not None:
            if node.default_income_account_id:
                return node.default_income_account_id
            node = node.parent
        return None

    def effective_valuation_method(self) -> str:
        node = self
        while node is not None:
            if node.default_valuation_method:
                return node.default_valuation_method
            node = node.parent
        return "fifo"


# ── Attribute definitions ─────────────────────────────────────────────────────

class ProductAttribute(BaseEntity):
    """A variant dimension: Color, Size, Storage Capacity, Configuration…"""

    class AttributeType(models.TextChoices):
        TEXT = "text", "Free Text"
        NUMBER = "number", "Number"
        SELECT = "select", "Select (from list)"

    name = models.CharField(max_length=100)
    attribute_type = models.CharField(
        max_length=10, choices=AttributeType.choices, default=AttributeType.SELECT
    )

    class Meta(BaseEntity.Meta):
        db_table = "catalogue_product_attributes"

    def __str__(self) -> str:
        return self.name


class ProductAttributeValue(BaseEntity):
    """One option in a SELECT attribute: Red, Large, 500 GB…"""

    attribute = models.ForeignKey(
        ProductAttribute, on_delete=models.CASCADE, related_name="values"
    )
    value = models.CharField(max_length=100)
    abbreviation = models.CharField(max_length=10, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "catalogue_product_attribute_values"
        unique_together = [("attribute", "value")]

    def __str__(self) -> str:
        return "{0}: {1}".format(self.attribute.name, self.value)


# ── Core Product entity ───────────────────────────────────────────────────────

class Product(BaseEntity):
    """
    The canonical product record.  Every other module references this; only
    warehouse.Item extends it for stock-specific behaviour.
    """

    class ProductType(models.TextChoices):
        STOCKABLE = "stockable", "Stockable Product"
        SERVICE = "service", "Service"
        BUNDLE = "bundle", "Bundle / Kit"
        DIGITAL = "digital", "Digital / Download"

    class LifecycleStatus(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        DISCONTINUED = "discontinued", "Discontinued"

    # Identity
    sku = models.CharField(max_length=100, unique=True, db_index=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    category = models.ForeignKey(
        ProductCategory, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="products",
    )
    product_type = models.CharField(
        max_length=20, choices=ProductType.choices, default=ProductType.STOCKABLE
    )
    lifecycle_status = models.CharField(
        max_length=20, choices=LifecycleStatus.choices, default=LifecycleStatus.DRAFT
    )

    # UOM — soft link to warehouse.UOM (UUID + denormalized abbreviation)
    base_uom_id = models.UUIDField(null=True, blank=True, db_index=True)
    base_uom_name = models.CharField(max_length=10, blank=True)

    # Variant / template relationship
    is_template = models.BooleanField(
        default=False,
        help_text="True when this product defines the attribute set for its variants.",
    )
    template = models.ForeignKey(
        "self", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="variants",
        help_text="Parent template product; null for standalone or template products.",
    )

    # Pricing defaults (PriceList rows override these)
    base_price = models.DecimalField(max_digits=19, decimal_places=4, null=True, blank=True)
    standard_cost = models.DecimalField(max_digits=19, decimal_places=4, null=True, blank=True)
    currency = models.CharField(max_length=3, default="USD")

    # GL defaults — override category-level defaults when set
    income_account_id = models.UUIDField(null=True, blank=True)
    expense_account_id = models.UUIDField(null=True, blank=True)
    stock_account_id = models.UUIDField(null=True, blank=True)
    tax_template_id = models.UUIDField(null=True, blank=True)

    # Catalog visibility per channel
    is_sellable = models.BooleanField(default=True)
    is_purchasable = models.BooleanField(default=True)
    show_on_website = models.BooleanField(default=False)
    show_on_pos = models.BooleanField(default=True)
    show_on_mobile_app = models.BooleanField(default=False)

    # Physical attributes
    weight = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    weight_uom_name = models.CharField(max_length=10, blank=True)

    is_active = models.BooleanField(default=True)

    class Meta(BaseEntity.Meta):
        db_table = "catalogue_products"

    def __str__(self) -> str:
        return "{0} — {1}".format(self.sku, self.name)

    # ── Helpers used by hooks ──────────────────────────────────────────────

    def effective_income_account_id(self):
        if self.income_account_id:
            return self.income_account_id
        if self.category_id:
            return self.category.effective_income_account_id()
        return None

    def effective_valuation_method(self) -> str:
        if self.category_id:
            return self.category.effective_valuation_method()
        return "fifo"


# ── Variant attribute assignment ───────────────────────────────────────────────

class ProductVariantAttribute(BaseEntity):
    """Maps a variant Product to the ProductAttributeValues that define it."""

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="variant_attributes"
    )
    attribute = models.ForeignKey(
        ProductAttribute, on_delete=models.CASCADE, related_name="variant_usages"
    )
    value = models.ForeignKey(
        ProductAttributeValue, on_delete=models.CASCADE, related_name="variant_usages"
    )

    class Meta(BaseEntity.Meta):
        db_table = "catalogue_product_variant_attributes"
        unique_together = [("product", "attribute")]

    def __str__(self) -> str:
        return "{0} / {1}={2}".format(self.product.sku, self.attribute.name, self.value.value)


# ── Multi-UOM conversion ───────────────────────────────────────────────────────

class ProductUOMConversion(BaseEntity):
    """
    Product-specific UOM conversion factor.
    e.g. 1 Carton = 12 Pcs for this SKU.
    from_uom_id / to_uom_id are UUID soft-links to warehouse.UOM.
    """

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="uom_conversions"
    )
    from_uom_id = models.UUIDField(db_index=True)
    from_uom_name = models.CharField(max_length=10, blank=True)
    to_uom_id = models.UUIDField(db_index=True)
    to_uom_name = models.CharField(max_length=10, blank=True)
    conversion_factor = models.DecimalField(max_digits=19, decimal_places=6)

    class Meta(BaseEntity.Meta):
        db_table = "catalogue_product_uom_conversions"
        unique_together = [("product", "from_uom_id", "to_uom_id")]

    def __str__(self) -> str:
        return "1 {0} = {1} {2} ({3})".format(
            self.from_uom_name, self.conversion_factor, self.to_uom_name, self.product.sku
        )

    def convert(self, qty):
        """Return qty expressed in to_uom."""
        from decimal import Decimal
        return Decimal(str(qty)) * self.conversion_factor


# ── Barcodes ───────────────────────────────────────────────────────────────────

class ProductBarcode(BaseEntity):
    """One or more barcodes per product / UOM combination."""

    class BarcodeType(models.TextChoices):
        EAN13 = "ean13", "EAN-13"
        UPC = "upc", "UPC-A"
        CODE128 = "code128", "Code 128"
        QR = "qr", "QR Code"
        INTERNAL = "internal", "Internal"

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="barcodes"
    )
    # Optional: which UOM does this barcode represent (case vs each)
    uom_id = models.UUIDField(null=True, blank=True, db_index=True)
    uom_name = models.CharField(max_length=10, blank=True)
    barcode = models.CharField(max_length=200, db_index=True)
    barcode_type = models.CharField(
        max_length=10, choices=BarcodeType.choices, default=BarcodeType.INTERNAL
    )
    is_primary = models.BooleanField(default=False)

    class Meta(BaseEntity.Meta):
        db_table = "catalogue_product_barcodes"
        indexes = [
            models.Index(fields=["barcode"], name="catalogue_barcode_lookup_idx"),
        ]

    def __str__(self) -> str:
        return "{0} ({1}) — {2}".format(self.barcode, self.barcode_type, self.product.sku)


# ── Product media ──────────────────────────────────────────────────────────────

class ProductMedia(BaseEntity):
    """Images and documents attached to a product (CDN-friendly delivery)."""

    class MediaType(models.TextChoices):
        IMAGE = "image", "Image"
        DOCUMENT = "document", "Document"
        VIDEO = "video", "Video"

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="media_items"
    )
    media_type = models.CharField(
        max_length=10, choices=MediaType.choices, default=MediaType.IMAGE
    )
    url = models.CharField(max_length=500)
    alt_text = models.CharField(max_length=255, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta(BaseEntity.Meta):
        db_table = "catalogue_product_media"
        ordering = ["product", "sort_order"]

    def __str__(self) -> str:
        return "{0} [{1}]".format(self.product.sku, self.media_type)


# ── Bundle / Kit components ────────────────────────────────────────────────────

class ProductBundleComponent(BaseEntity):
    """
    One component within a Bundle or Kit product.
    Both bundle and component are Products (no cross-app boundary).
    """

    bundle = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="bundle_components"
    )
    component = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="used_in_bundles"
    )
    qty = models.DecimalField(max_digits=19, decimal_places=4, default=1)
    uom_id = models.UUIDField(null=True, blank=True)
    uom_name = models.CharField(max_length=10, blank=True)
    is_optional = models.BooleanField(default=False)

    class Meta(BaseEntity.Meta):
        db_table = "catalogue_bundle_components"
        unique_together = [("bundle", "component")]

    def __str__(self) -> str:
        return "{0} × {1} in {2}".format(self.qty, self.component.sku, self.bundle.sku)


# ── Price lists (moved from apps.sales) ───────────────────────────────────────

class PriceList(BaseEntity):
    """
    Named price list with optional currency scope and validity window.
    Previously in apps.sales — moved here so all product pricing lives in one app.
    Sales, Purchasing, and POS reference price lists via UUID soft-link.
    """

    name = models.CharField(max_length=100)
    currency = models.CharField(max_length=3, default="USD")
    is_buying = models.BooleanField(default=False)
    is_selling = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "catalogue_price_lists"

    def __str__(self) -> str:
        return self.name


class ProductPrice(BaseEntity):
    """
    Price of a Product within a PriceList.
    `min_qty` enables tiered/volume pricing: the row with the highest applicable
    min_qty wins.  `customer_id` enables customer-specific pricing.
    Previously called ItemPrice in apps.sales.
    """

    price_list = models.ForeignKey(
        PriceList, on_delete=models.CASCADE, related_name="product_prices"
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="price_list_entries"
    )
    uom_id = models.UUIDField(
        null=True, blank=True, help_text="Null = base UOM pricing; set for UOM-specific tiers."
    )
    min_qty = models.DecimalField(
        max_digits=19, decimal_places=4, default=0,
        help_text="Minimum qty for this tier to apply (0 = base price).",
    )
    rate = models.DecimalField(max_digits=19, decimal_places=4)
    # Customer-specific pricing (soft link to CRM/Accounting)
    customer_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta(BaseEntity.Meta):
        db_table = "catalogue_product_prices"
        indexes = [
            models.Index(
                fields=["price_list", "product", "min_qty"],
                name="catalogue_price_lookup_idx",
            ),
        ]

    def __str__(self) -> str:
        return "{0} / {1} @ min_qty {2} = {3}".format(
            self.price_list, self.product.sku, self.min_qty, self.rate
        )
