"""
Management command: seed_product_catalogue

Seeds a representative product catalogue:
  - 3 product categories (with GL defaults)
  - 2 product attributes (Color, Size) with values
  - 10 standalone products (5 stockable, 2 service, 2 digital, 1 bundle)
  - 1 template product with 4 generated variants
  - Barcodes and UOM conversions for stockable products
  - 3 price lists (Retail, Wholesale, VIP) linked from seed_sales if present
  - ProductPrice rows for all products in all 3 price lists

Run after seed_sales so that price lists already exist.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand

import uuid


def _get_or_create_company_id():
    try:
        from core.auth.models import Company
        c = Company.objects.first()
        return c.id if c else uuid.uuid4()
    except Exception:
        return uuid.uuid4()


class Command(BaseCommand):
    help = "Seed product catalogue with demo products, categories, attributes, and pricing."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=str, default=None)

    def handle(self, *args, **options):
        cid = options.get("company_id")
        if cid:
            company_id = uuid.UUID(cid)
        else:
            company_id = _get_or_create_company_id()

        self.stdout.write("Seeding product catalogue for company {}...".format(company_id))

        categories = self._seed_categories(company_id)
        attributes = self._seed_attributes(company_id)
        products = self._seed_products(categories, company_id)
        self._seed_template_and_variants(categories, attributes, company_id)
        self._seed_barcodes(products, company_id)
        self._seed_uom_conversions(products, company_id)
        price_lists = self._get_or_create_price_lists(company_id)
        self._seed_product_prices(products, price_lists, company_id)

        self.stdout.write(self.style.SUCCESS("Product catalogue seed complete."))

    # ── Categories ────────────────────────────────────────────────────────────

    def _seed_categories(self, company_id):
        from apps.product_catalogue.models import ProductCategory

        root_specs = [
            {
                "name": "Electronics",
                "code": "ELEC",
                "default_valuation_method": "fifo",
            },
            {
                "name": "Services",
                "code": "SVC",
                "default_valuation_method": "",
            },
            {
                "name": "Consumables",
                "code": "CONS",
                "default_valuation_method": "moving_avg",
            },
        ]
        result = []
        for spec in root_specs:
            cat, created = ProductCategory.objects.get_or_create(
                name=spec["name"],
                company_id=company_id,
                defaults={
                    "code": spec["code"],
                    "default_valuation_method": spec["default_valuation_method"],
                },
            )
            if created:
                self.stdout.write("  Created category: {}".format(cat.name))
            result.append(cat)
        return result

    # ── Attributes ────────────────────────────────────────────────────────────

    def _seed_attributes(self, company_id):
        from apps.product_catalogue.models import ProductAttribute, ProductAttributeValue

        attr_specs = [
            {
                "name": "Color",
                "attribute_type": "select",
                "values": [
                    ("Black", "BLK"),
                    ("White", "WHT"),
                    ("Blue", "BLU"),
                    ("Red", "RED"),
                ],
            },
            {
                "name": "Size",
                "attribute_type": "select",
                "values": [
                    ("Small", "S"),
                    ("Medium", "M"),
                    ("Large", "L"),
                    ("XL", "XL"),
                ],
            },
        ]
        result = []
        for spec in attr_specs:
            attr, _ = ProductAttribute.objects.get_or_create(
                name=spec["name"],
                company_id=company_id,
                defaults={"attribute_type": spec["attribute_type"]},
            )
            for value, abbr in spec["values"]:
                ProductAttributeValue.objects.get_or_create(
                    attribute=attr,
                    value=value,
                    defaults={"abbreviation": abbr, "company_id": company_id},
                )
            result.append(attr)
        return result

    # ── Standalone Products ───────────────────────────────────────────────────

    def _seed_products(self, categories, company_id):
        from apps.product_catalogue.models import Product

        elec_cat, svc_cat, cons_cat = categories[0], categories[1], categories[2]

        product_specs = [
            # Stockable — Electronics
            {"sku": "LAPTOP-PRO-15", "name": "Laptop Pro 15\"", "category": elec_cat,
             "product_type": "stockable", "base_price": Decimal("1299.00"), "standard_cost": Decimal("950.00"),
             "is_sellable": True, "is_purchasable": True, "show_on_website": True, "show_on_pos": True},
            {"sku": "WIRELESS-MOUSE", "name": "Wireless Mouse", "category": elec_cat,
             "product_type": "stockable", "base_price": Decimal("45.00"), "standard_cost": Decimal("18.00"),
             "is_sellable": True, "is_purchasable": True, "show_on_website": True, "show_on_pos": True},
            {"sku": "USB-HUB-7P", "name": "7-Port USB Hub", "category": elec_cat,
             "product_type": "stockable", "base_price": Decimal("39.00"), "standard_cost": Decimal("15.00"),
             "is_sellable": True, "is_purchasable": True, "show_on_website": True, "show_on_pos": True},
            {"sku": "HDMI-CABLE-2M", "name": "HDMI Cable 2m", "category": elec_cat,
             "product_type": "stockable", "base_price": Decimal("12.00"), "standard_cost": Decimal("3.50"),
             "is_sellable": True, "is_purchasable": True, "show_on_website": True, "show_on_pos": True},
            {"sku": "WEBCAM-HD-1080", "name": "HD Webcam 1080p", "category": elec_cat,
             "product_type": "stockable", "base_price": Decimal("89.00"), "standard_cost": Decimal("42.00"),
             "is_sellable": True, "is_purchasable": True, "show_on_website": True, "show_on_pos": True},
            # Consumables
            {"sku": "PAPER-A4-500", "name": "A4 Paper (500 sheets)", "category": cons_cat,
             "product_type": "stockable", "base_price": Decimal("8.50"), "standard_cost": Decimal("4.00"),
             "is_sellable": True, "is_purchasable": True, "show_on_pos": True},
            {"sku": "INK-CARTRIDGE-BK", "name": "Ink Cartridge Black", "category": cons_cat,
             "product_type": "stockable", "base_price": Decimal("22.00"), "standard_cost": Decimal("9.00"),
             "is_sellable": True, "is_purchasable": True, "show_on_pos": True},
            # Services
            {"sku": "SUPPORT-ANNUAL", "name": "Annual Support Contract", "category": svc_cat,
             "product_type": "service", "base_price": Decimal("599.00"), "standard_cost": Decimal("200.00"),
             "is_sellable": True, "is_purchasable": False, "show_on_website": True},
            {"sku": "INSTALL-SVC", "name": "Installation Service (1 day)", "category": svc_cat,
             "product_type": "service", "base_price": Decimal("350.00"), "standard_cost": Decimal("120.00"),
             "is_sellable": True, "is_purchasable": False, "show_on_website": True},
            # Digital
            {"sku": "EBOOK-GUIDE", "name": "User Guide (eBook)", "category": svc_cat,
             "product_type": "digital", "base_price": Decimal("9.99"), "standard_cost": Decimal("0"),
             "is_sellable": True, "is_purchasable": False, "show_on_website": True, "show_on_mobile_app": True},
        ]

        result = []
        for spec in product_specs:
            cat = spec.pop("category")
            sku = spec.pop("sku")
            prod, created = Product.objects.get_or_create(
                sku=sku,
                defaults={
                    "category": cat,
                    "lifecycle_status": "active",
                    "currency": "USD",
                    "is_active": True,
                    "company_id": company_id,
                    **spec,
                },
            )
            if created:
                self.stdout.write("  Created product: {} — {}".format(prod.sku, prod.name))
            result.append(prod)

        # Bundle: Workstation Kit
        kit_components = result[:3]  # Laptop + Mouse + USB Hub
        kit, kit_created = Product.objects.get_or_create(
            sku="KIT-WORKSTATION",
            defaults={
                "name": "Workstation Starter Kit",
                "category": categories[0],
                "product_type": "bundle",
                "lifecycle_status": "active",
                "base_price": Decimal("1299.00"),
                "standard_cost": Decimal("983.00"),
                "currency": "USD",
                "is_sellable": True,
                "is_purchasable": False,
                "show_on_website": True,
                "show_on_pos": True,
                "is_active": True,
                "company_id": company_id,
            },
        )
        if kit_created:
            from apps.product_catalogue.models import ProductBundleComponent
            for comp in kit_components:
                ProductBundleComponent.objects.get_or_create(
                    bundle=kit, component=comp,
                    defaults={"qty": Decimal("1"), "is_optional": False, "company_id": company_id},
                )
            self.stdout.write("  Created bundle: {} with {} components".format(kit.sku, len(kit_components)))
        result.append(kit)

        return result

    # ── Template + Variants ───────────────────────────────────────────────────

    def _seed_template_and_variants(self, categories, attributes, company_id):
        from apps.product_catalogue.hooks.product import generate_variants
        from apps.product_catalogue.models import Product, ProductAttributeValue

        template, created = Product.objects.get_or_create(
            sku="TSHIRT-TEMPLATE",
            defaults={
                "name": "Classic T-Shirt",
                "category": categories[2],
                "product_type": "stockable",
                "lifecycle_status": "active",
                "base_price": Decimal("24.99"),
                "standard_cost": Decimal("8.00"),
                "currency": "USD",
                "is_template": True,
                "is_sellable": True,
                "is_purchasable": True,
                "show_on_website": True,
                "show_on_pos": True,
                "is_active": True,
                "company_id": company_id,
            },
        )
        if created:
            self.stdout.write("  Created template: {}".format(template.sku))

        # Generate 2 colors x 2 sizes = 4 variants
        color_attr, size_attr = attributes[0], attributes[1]
        color_values = list(
            ProductAttributeValue.objects.filter(
                attribute=color_attr, value__in=["Black", "White"]
            ).values_list("id", flat=True)
        )
        size_values = list(
            ProductAttributeValue.objects.filter(
                attribute=size_attr, value__in=["Small", "Large"]
            ).values_list("id", flat=True)
        )

        if color_values and size_values:
            variants = generate_variants(
                str(template.id),
                {
                    str(color_attr.id): [str(v) for v in color_values],
                    str(size_attr.id): [str(v) for v in size_values],
                },
            )
            if variants:
                self.stdout.write("  Generated {} variants from {}".format(len(variants), template.sku))

    # ── Barcodes ──────────────────────────────────────────────────────────────

    def _seed_barcodes(self, products, company_id):
        from apps.product_catalogue.models import ProductBarcode

        for i, product in enumerate(products[:7]):  # stockable products only
            ean = "5901234{0:06d}".format(i + 1)
            ProductBarcode.objects.get_or_create(
                product=product,
                barcode=ean,
                defaults={
                    "barcode_type": "ean13",
                    "is_primary": True,
                    "company_id": company_id,
                },
            )

    # ── UOM Conversions ───────────────────────────────────────────────────────

    def _seed_uom_conversions(self, products, company_id):
        from apps.product_catalogue.models import ProductUOMConversion
        from apps.warehouse.models import UOM

        try:
            each = UOM.objects.filter(abbreviation__in=["EA", "Pcs", "Each"]).first()
            box = UOM.objects.filter(abbreviation__in=["Box", "BOX"]).first()
            if not each or not box:
                return
        except Exception:
            return

        for product in products[:5]:
            ProductUOMConversion.objects.get_or_create(
                product=product,
                from_uom_id=box.id,
                to_uom_id=each.id,
                defaults={
                    "from_uom_name": str(box),
                    "to_uom_name": str(each),
                    "conversion_factor": Decimal("12"),
                    "company_id": company_id,
                },
            )

    # ── Price Lists + ProductPrice ────────────────────────────────────────────

    def _get_or_create_price_lists(self, company_id):
        from apps.product_catalogue.models import PriceList

        specs = [
            {"name": "Standard Retail", "is_selling": True},
            {"name": "Wholesale / Volume", "is_selling": True},
            {"name": "VIP Customer", "is_selling": True},
        ]
        result = []
        for spec in specs:
            pl, _ = PriceList.objects.get_or_create(
                name=spec["name"],
                company_id=company_id,
                defaults={"currency": "USD", "is_selling": True, "is_active": True},
            )
            result.append(pl)
        return result

    def _seed_product_prices(self, products, price_lists, company_id):
        from apps.product_catalogue.models import ProductPrice

        retail_pl, wholesale_pl, vip_pl = price_lists[0], price_lists[1], price_lists[2]

        for product in products:
            base = product.base_price or Decimal("50.00")

            # Retail: base price
            ProductPrice.objects.get_or_create(
                price_list=retail_pl, product=product, min_qty=Decimal("0"),
                defaults={"rate": base, "company_id": company_id},
            )
            # Wholesale: base
            ProductPrice.objects.get_or_create(
                price_list=wholesale_pl, product=product, min_qty=Decimal("0"),
                defaults={
                    "rate": (base * Decimal("0.90")).quantize(Decimal("0.01")),
                    "company_id": company_id,
                },
            )
            # Wholesale: volume (qty >= 10)
            ProductPrice.objects.get_or_create(
                price_list=wholesale_pl, product=product, min_qty=Decimal("10"),
                defaults={
                    "rate": (base * Decimal("0.85")).quantize(Decimal("0.01")),
                    "company_id": company_id,
                },
            )
            # VIP: 20% off
            ProductPrice.objects.get_or_create(
                price_list=vip_pl, product=product, min_qty=Decimal("0"),
                defaults={
                    "rate": (base * Decimal("0.80")).quantize(Decimal("0.01")),
                    "company_id": company_id,
                },
            )
        self.stdout.write("  Seeded ProductPrice rows for {} products x 3 price lists.".format(len(products)))
