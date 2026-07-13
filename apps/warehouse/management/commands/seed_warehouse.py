"""
Management command: seed realistic Warehouse dummy data.
Usage: python manage.py seed_warehouse [--clear]

Covers: UOMs, Item Categories, Items (30+), Warehouses, Bins, Batches,
Serial Numbers, Reorder Rules, Stock Entries (receipts + issues + transfers),
Stock Ledger (auto-posted), Cycle Count Sheet.
"""
import random
from datetime import date, time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

TODAY = date.today()


UOMS = [
    ("Each",        "EA"),
    ("Kilogram",    "KG"),
    ("Gram",        "G"),
    ("Litre",       "L"),
    ("Millilitre",  "ML"),
    ("Box",         "BOX"),
    ("Carton",      "CTN"),
    ("Metre",       "M"),
    ("Piece",       "PCS"),
    ("Set",         "SET"),
    ("Pair",        "PR"),
    ("Hour",        "HR"),
    ("Month",       "MO"),
]

ITEM_CATEGORIES = [
    ("Software Licenses",   None),
    ("Hardware",            None),
    ("Office Supplies",     None),
    ("Networking",          "Hardware"),
    ("Compute",             "Hardware"),
    ("Storage",             "Hardware"),
    ("Peripherals",         "Hardware"),
    ("Consumables",         "Office Supplies"),
    ("Furniture",           "Office Supplies"),
    ("Cleaning Supplies",   None),
    ("Safety & PPE",        None),
    ("Electronics",         None),
]

# (code, name, category, uom, selling, buying, valuation, has_serial, has_batch, barcode)
ITEMS = [
    # Software (non-stock, service)
    ("SW-ERP-LIC",   "Ochre ERP Annual License (1 user)",   "Software Licenses", "MO",    199.00,  0.00,  "standard", False, False, ""),
    ("SW-SUPP-LIC",  "Support & Maintenance License",        "Software Licenses", "MO",     49.00,  0.00,  "standard", False, False, ""),
    ("SW-STOR-1TB",  "Cloud Storage Add-on (1 TB/yr)",       "Software Licenses", "MO",     20.00,  0.00,  "standard", False, False, ""),
    # Hardware — serialised
    ("HW-LAPTOP-PRO","Laptop Pro 14\" (M4)",                 "Compute",           "EA",  2499.00,1899.00, "fifo",     True,  False, "7891234560001"),
    ("HW-LAPTOP-STD","Laptop Standard 15\" (i7)",            "Compute",           "EA",  1299.00, 949.00, "fifo",     True,  False, "7891234560002"),
    ("HW-SRVR-2U",   "2U Rack Server (32-core)",             "Compute",           "EA",  6499.00,4999.00, "fifo",     True,  False, "7891234560003"),
    ("HW-DSKTP-I5",  "Desktop Workstation i5",               "Compute",           "EA",   899.00, 649.00, "fifo",     True,  False, "7891234560004"),
    # Networking
    ("NET-SW-24P",   "24-Port Managed Switch",               "Networking",        "EA",   799.00, 599.00, "fifo",     True,  False, "7891234560010"),
    ("NET-RTR-ENT",  "Enterprise Router",                    "Networking",        "EA",  1499.00,1099.00, "fifo",     True,  False, "7891234560011"),
    ("NET-CAB-CAT6", "CAT6 Ethernet Cable 5m",               "Networking",        "EA",     8.99,   4.50, "moving_avg",False,False, "7891234560012"),
    ("NET-WAP-AX",   "Wi-Fi 7 Access Point",                 "Networking",        "EA",   349.00, 249.00, "fifo",     True,  False, "7891234560013"),
    # Storage
    ("STG-SSD-1TB",  "SSD 1TB NVMe",                         "Storage",           "EA",   119.00,  79.00, "fifo",     False, False, "7891234560020"),
    ("STG-HDD-4TB",  "HDD 4TB Enterprise",                   "Storage",           "EA",   149.00,  99.00, "fifo",     False, False, "7891234560021"),
    ("STG-NAS-8TB",  "NAS Appliance 8TB",                    "Storage",           "EA",   699.00, 499.00, "fifo",     True,  False, "7891234560022"),
    # Peripherals
    ("PRF-MON-27",   "27\" 4K IPS Monitor",                  "Peripherals",       "EA",   549.00, 399.00, "fifo",     True,  False, "7891234560030"),
    ("PRF-KB-MECH",  "Mechanical Keyboard (TKL)",            "Peripherals",       "EA",    89.00,  55.00, "moving_avg",False,False, "7891234560031"),
    ("PRF-MOUSE-ERG","Ergonomic Wireless Mouse",             "Peripherals",       "EA",    59.00,  35.00, "moving_avg",False,False, "7891234560032"),
    ("PRF-HEADSET",  "USB Headset w/ Noise Cancellation",    "Peripherals",       "EA",    79.00,  50.00, "moving_avg",False,False, "7891234560033"),
    ("PRF-DOCK-USB", "USB-C Docking Station",                "Peripherals",       "EA",   149.00,  99.00, "moving_avg",False,False, "7891234560034"),
    ("PRF-WEBCAM-4K","4K Webcam",                            "Peripherals",       "EA",    99.00,  65.00, "moving_avg",False,False, "7891234560035"),
    # Office Supplies — batch-tracked (consumables)
    ("OFF-PAPER-A4", "A4 Copy Paper (500 sheets)",           "Consumables",       "BOX",    7.99,   4.50, "moving_avg",False,True,  "7891234560040"),
    ("OFF-PEN-BLK",  "Ballpoint Pens Black (12-pack)",       "Consumables",       "BOX",    4.99,   2.50, "moving_avg",False,True,  "7891234560041"),
    ("OFF-TONER-BK", "Laser Toner Cartridge (Black)",        "Consumables",       "EA",    79.00,  50.00, "moving_avg",False,True,  "7891234560042"),
    ("OFF-NOTEPAD",  "A5 Spiral Notepad (pack of 5)",        "Consumables",       "PCS",    9.99,   5.50, "moving_avg",False,False, "7891234560043"),
    # Furniture
    ("FRN-DESK-STND","Height-Adjustable Standing Desk",      "Furniture",         "EA",   599.00, 399.00, "fifo",     False, False, "7891234560050"),
    ("FRN-CHAIR-ERG","Ergonomic Office Chair",               "Furniture",         "EA",   449.00, 299.00, "fifo",     False, False, "7891234560051"),
    # Cleaning & PPE
    ("CLN-SANITIZER","Hand Sanitizer 500ml",                 "Cleaning Supplies", "EA",     3.99,   1.80, "moving_avg",False,True,  "7891234560060"),
    ("CLN-WIPES",    "Surface Disinfectant Wipes (80ct)",    "Cleaning Supplies", "BOX",    6.99,   3.50, "moving_avg",False,True,  "7891234560061"),
    ("PPE-MASK-N95", "N95 Respirator Mask (10-pack)",        "Safety & PPE",      "BOX",   14.99,   8.00, "moving_avg",False,True,  "7891234560062"),
    # Electronics
    ("ELC-TABLET-10","10\" Android Tablet",                  "Electronics",       "EA",   299.00, 199.00, "fifo",     True,  False, "7891234560070"),
    ("ELC-CHARGER",  "65W GaN USB-C Charger",                "Electronics",       "EA",    39.99,  22.00, "moving_avg",False,False, "7891234560071"),
    ("ELC-EXTBAT",   "30000mAh Power Bank",                  "Electronics",       "EA",    49.99,  28.00, "moving_avg",False,False, "7891234560072"),
]

WAREHOUSES = [
    # (code, name, type, is_group, parent_code, city, country)
    ("ALL",     "All Warehouses",      "stores",        True,  None,    "",            "US"),
    ("HQ",      "HQ Main Store",       "stores",        False, "ALL",   "San Francisco","US"),
    ("HQ-FG",   "HQ Finished Goods",  "finished_goods", False,"ALL",   "San Francisco","US"),
    ("NY",      "New York Regional",   "stores",        False, "ALL",   "New York",    "US"),
    ("UK",      "London Office Store", "stores",        False, "ALL",   "London",      "UK"),
    ("TRANSIT", "In-Transit",          "transit",       False, "ALL",   "",            "US"),
    ("VIRTUAL", "Virtual (Services)",  "virtual",       False, "ALL",   "",            "US"),
]

BINS = [
    # (warehouse_code, bin_code, aisle, rack, level)
    ("HQ",    "A-01-01", "A", "01", "01"),
    ("HQ",    "A-01-02", "A", "01", "02"),
    ("HQ",    "A-02-01", "A", "02", "01"),
    ("HQ",    "B-01-01", "B", "01", "01"),
    ("HQ",    "B-01-02", "B", "01", "02"),
    ("HQ",    "B-02-01", "B", "02", "01"),
    ("HQ-FG", "FG-01",   "FG","01", "01"),
    ("HQ-FG", "FG-02",   "FG","02", "01"),
    ("NY",    "NY-A-01", "A", "01", "01"),
    ("NY",    "NY-B-01", "B", "01", "01"),
    ("UK",    "UK-A-01", "A", "01", "01"),
]

REORDER_RULES = [
    # (item_code, warehouse_code, reorder_level, reorder_qty, safety_stock)
    ("HW-LAPTOP-PRO",  "HQ",   3,  10,  2),
    ("HW-LAPTOP-STD",  "HQ",   5,  15,  3),
    ("PRF-MON-27",     "HQ",   4,  10,  2),
    ("NET-CAB-CAT6",   "HQ",  20,  50, 10),
    ("OFF-PAPER-A4",   "HQ",  10,  50,  5),
    ("OFF-TONER-BK",   "HQ",   2,   6,  1),
    ("CLN-SANITIZER",  "HQ",  10,  30,  5),
    ("HW-LAPTOP-STD",  "NY",   2,   5,  1),
    ("HW-LAPTOP-PRO",  "NY",   1,   3,  1),
]


def _days_ago(n):
    return TODAY - timedelta(days=n)


class Command(BaseCommand):
    help = "Seed realistic Warehouse dummy data."

    def add_arguments(self, parser):
        parser.add_argument("--clear", action="store_true", help="Delete existing warehouse data first")

    def handle(self, *args, **options):
        from apps.warehouse.models import (
            Batch, Bin, CycleCountDetail, CycleCountSheet, Item,
            ItemCategory, ReorderRule, SerialNo, StockEntry, StockEntryDetail,
            StockLedger, UOM, UOMConversion, Warehouse,
        )
        from apps.warehouse.hooks.stock_entry import post_stock_ledger

        if options["clear"]:
            self.stdout.write("  Clearing warehouse data…")
            for M in [
                CycleCountDetail, CycleCountSheet, SerialNo, Batch,
                StockLedger, StockEntryDetail, StockEntry,
                ReorderRule, Bin, Warehouse, Item, ItemCategory,
                UOMConversion, UOM,
            ]:
                M.objects.all().delete()
            self.stdout.write(self.style.WARNING("  Cleared."))

        # ── 1. UOMs ───────────────────────────────────────────────────────────
        self.stdout.write("  Seeding UOMs…")
        uom_map = {}
        for name, abbr in UOMS:
            u, _ = UOM.objects.get_or_create(abbreviation=abbr, defaults={"name": name})
            uom_map[abbr] = u

        # UOM conversions
        UOMConversion.objects.get_or_create(
            from_uom=uom_map["BOX"], to_uom=uom_map["EA"],
            defaults={"conversion_factor": Decimal("12")}
        )
        UOMConversion.objects.get_or_create(
            from_uom=uom_map["CTN"], to_uom=uom_map["BOX"],
            defaults={"conversion_factor": Decimal("10")}
        )
        UOMConversion.objects.get_or_create(
            from_uom=uom_map["KG"], to_uom=uom_map["G"],
            defaults={"conversion_factor": Decimal("1000")}
        )

        # ── 2. Item Categories ────────────────────────────────────────────────
        self.stdout.write("  Seeding item categories…")
        cat_map = {}
        # First pass — root categories
        for name, parent_name in ITEM_CATEGORIES:
            if parent_name is None:
                c, _ = ItemCategory.objects.get_or_create(name=name, defaults={"parent": None})
                cat_map[name] = c
        # Second pass — children
        for name, parent_name in ITEM_CATEGORIES:
            if parent_name is not None:
                c, _ = ItemCategory.objects.get_or_create(
                    name=name, defaults={"parent": cat_map.get(parent_name)}
                )
                cat_map[name] = c

        # ── 3. Items ──────────────────────────────────────────────────────────
        self.stdout.write("  Seeding items…")
        item_map = {}
        for (code, name, cat_name, uom_abbr, sell, buy, val_method,
             has_sn, has_batch, barcode) in ITEMS:
            is_svc = cat_name == "Software Licenses"
            item, _ = Item.objects.get_or_create(
                item_code=code,
                defaults={
                    "item_name": name,
                    "category": cat_map.get(cat_name),
                    "uom": uom_map.get(uom_abbr),
                    "is_stock_item": not is_svc,
                    "is_service_item": is_svc,
                    "is_purchase_item": True,
                    "is_sales_item": True,
                    "has_serial_no": has_sn,
                    "has_batch": has_batch,
                    "has_expiry_date": has_batch and cat_name in ("Consumables","Cleaning Supplies","Safety & PPE"),
                    "shelf_life_days": 730 if has_batch else 0,
                    "standard_selling_price": Decimal(str(sell)) if sell else None,
                    "standard_buying_price": Decimal(str(buy)) if buy else None,
                    "valuation_method": val_method,
                    "barcode": barcode,
                    "is_active": True,
                },
            )
            item_map[code] = item

        # ── 4. Warehouses ─────────────────────────────────────────────────────
        self.stdout.write("  Seeding warehouses…")
        wh_map = {}
        for code, name, wh_type, is_group, parent_code, city, country in WAREHOUSES:
            wh, _ = Warehouse.objects.get_or_create(
                warehouse_code=code,
                defaults={
                    "warehouse_name": name,
                    "warehouse_type": wh_type,
                    "is_group": is_group,
                    "parent_warehouse": wh_map.get(parent_code) if parent_code else None,
                    "city": city,
                    "country": country,
                    "is_active": True,
                },
            )
            wh_map[code] = wh

        # ── 5. Bins ───────────────────────────────────────────────────────────
        self.stdout.write("  Seeding bins…")
        bin_map = {}
        for wh_code, bin_code, aisle, rack, level in BINS:
            b, _ = Bin.objects.get_or_create(
                warehouse=wh_map[wh_code],
                bin_code=bin_code,
                defaults={"aisle": aisle, "rack": rack, "level": level, "is_active": True},
            )
            bin_map[(wh_code, bin_code)] = b

        hq = wh_map["HQ"]
        hq_fg = wh_map["HQ-FG"]
        ny = wh_map["NY"]
        uk = wh_map["UK"]

        # ── 6. Batches (for batch-tracked items) ──────────────────────────────
        self.stdout.write("  Seeding batches…")
        batch_map = {}
        batch_items = [(c, item_map[c]) for (c, *_, hb, _) in ITEMS if hb]
        for item_code, item in batch_items:
            for batch_suffix, mfg_offset, exp_offset, qty in [
                ("A", -365, 365,  500),
                ("B", -180, 180,  300),
                ("C",  -30, 330,  200),
            ]:
                bid = f"{item_code}-{batch_suffix}"
                b, _ = Batch.objects.get_or_create(
                    batch_id=bid,
                    item=item,
                    defaults={
                        "manufacturing_date": _days_ago(-mfg_offset),
                        "expiry_date": _days_ago(-exp_offset) if item.has_expiry_date else None,
                        "batch_qty": Decimal(str(qty)),
                        "remaining_qty": Decimal(str(int(qty * 0.7))),
                        "status": "active",
                        "supplier_lot_no": f"SUP-{random.randint(10000,99999)}",
                    },
                )
                batch_map[(item_code, batch_suffix)] = b

        # ── 7. Stock Entries (Receipts) ───────────────────────────────────────
        self.stdout.write("  Seeding stock entries — initial receipts…")

        # Opening receipt — hardware into HQ
        hardware_receipt_lines = [
            ("HW-LAPTOP-PRO", 20, Decimal("1899.00")),
            ("HW-LAPTOP-STD", 30, Decimal("949.00")),
            ("HW-SRVR-2U",     5, Decimal("4999.00")),
            ("HW-DSKTP-I5",   10, Decimal("649.00")),
            ("NET-SW-24P",    10, Decimal("599.00")),
            ("NET-RTR-ENT",    5, Decimal("1099.00")),
            ("NET-WAP-AX",    15, Decimal("249.00")),
            ("NET-CAB-CAT6",  100, Decimal("4.50")),
            ("STG-SSD-1TB",   50, Decimal("79.00")),
            ("STG-HDD-4TB",   30, Decimal("99.00")),
            ("STG-NAS-8TB",    8, Decimal("499.00")),
            ("PRF-MON-27",    20, Decimal("399.00")),
            ("PRF-KB-MECH",   40, Decimal("55.00")),
            ("PRF-MOUSE-ERG", 40, Decimal("35.00")),
            ("PRF-HEADSET",   30, Decimal("50.00")),
            ("PRF-DOCK-USB",  25, Decimal("99.00")),
            ("PRF-WEBCAM-4K", 20, Decimal("65.00")),
            ("FRN-DESK-STND", 15, Decimal("399.00")),
            ("FRN-CHAIR-ERG", 15, Decimal("299.00")),
            ("ELC-TABLET-10", 12, Decimal("199.00")),
            ("ELC-CHARGER",   30, Decimal("22.00")),
            ("ELC-EXTBAT",    20, Decimal("28.00")),
        ]
        total_val = sum(qty * rate for _, qty, rate in hardware_receipt_lines)
        se1, created = StockEntry.objects.get_or_create(
            entry_type="receipt",
            posting_date=_days_ago(180),
            to_warehouse=hq,
            defaults={
                "status": "submitted",
                "remarks": "Opening hardware stock receipt — Q1 procurement",
                "total_value": total_val,
            },
        )
        if created:
            for item_code, qty, rate in hardware_receipt_lines:
                StockEntryDetail.objects.create(
                    stock_entry=se1,
                    item=item_map[item_code],
                    qty=Decimal(str(qty)),
                    basic_rate=rate,
                    amount=Decimal(str(qty)) * rate,
                    uom=item_map[item_code].uom,
                )
            post_stock_ledger(se1)

        # Batch-tracked consumables receipt into HQ
        consumable_lines = [
            ("OFF-PAPER-A4", 100, Decimal("4.50"),  ("OFF-PAPER-A4", "A")),
            ("OFF-PEN-BLK",   50, Decimal("2.50"),  ("OFF-PEN-BLK", "A")),
            ("OFF-TONER-BK",  20, Decimal("50.00"), ("OFF-TONER-BK", "A")),
            ("OFF-NOTEPAD",   80, Decimal("5.50"),  None),
            ("CLN-SANITIZER",100, Decimal("1.80"),  ("CLN-SANITIZER","A")),
            ("CLN-WIPES",     60, Decimal("3.50"),  ("CLN-WIPES","A")),
            ("PPE-MASK-N95",  50, Decimal("8.00"),  ("PPE-MASK-N95","A")),
        ]
        total_cons = sum(qty * rate for _, qty, rate, _ in consumable_lines)
        se2, created = StockEntry.objects.get_or_create(
            entry_type="receipt",
            posting_date=_days_ago(150),
            to_warehouse=hq,
            defaults={
                "status": "submitted",
                "remarks": "Office consumables — Q1 purchase",
                "total_value": total_cons,
            },
        )
        if created:
            for item_code, qty, rate, batch_key in consumable_lines:
                batch = batch_map.get(batch_key) if batch_key else None
                StockEntryDetail.objects.create(
                    stock_entry=se2,
                    item=item_map[item_code],
                    qty=Decimal(str(qty)),
                    basic_rate=rate,
                    amount=Decimal(str(qty)) * rate,
                    uom=item_map[item_code].uom,
                    batch=batch,
                )
            post_stock_ledger(se2)

        # Transfer: HQ → NY
        ny_transfer_lines = [
            ("HW-LAPTOP-PRO", 5, Decimal("1899.00")),
            ("HW-LAPTOP-STD", 8, Decimal("949.00")),
            ("PRF-MON-27",    5, Decimal("399.00")),
            ("PRF-KB-MECH",  10, Decimal("55.00")),
            ("PRF-MOUSE-ERG",10, Decimal("35.00")),
        ]
        total_ny = sum(qty * rate for _, qty, rate in ny_transfer_lines)
        se3, created = StockEntry.objects.get_or_create(
            entry_type="transfer",
            posting_date=_days_ago(120),
            from_warehouse=hq,
            to_warehouse=ny,
            defaults={
                "status": "submitted",
                "remarks": "Stock transfer to New York regional office",
                "total_value": total_ny,
            },
        )
        if created:
            for item_code, qty, rate in ny_transfer_lines:
                StockEntryDetail.objects.create(
                    stock_entry=se3,
                    item=item_map[item_code],
                    qty=Decimal(str(qty)),
                    basic_rate=rate,
                    amount=Decimal(str(qty)) * rate,
                    uom=item_map[item_code].uom,
                )
            post_stock_ledger(se3)

        # Transfer: HQ → UK
        uk_transfer_lines = [
            ("HW-LAPTOP-PRO", 3, Decimal("1899.00")),
            ("HW-LAPTOP-STD", 5, Decimal("949.00")),
            ("PRF-MON-27",    3, Decimal("399.00")),
            ("NET-WAP-AX",    3, Decimal("249.00")),
        ]
        total_uk = sum(qty * rate for _, qty, rate in uk_transfer_lines)
        se4, created = StockEntry.objects.get_or_create(
            entry_type="transfer",
            posting_date=_days_ago(90),
            from_warehouse=hq,
            to_warehouse=uk,
            defaults={
                "status": "submitted",
                "remarks": "Stock transfer to London office",
                "total_value": total_uk,
            },
        )
        if created:
            for item_code, qty, rate in uk_transfer_lines:
                StockEntryDetail.objects.create(
                    stock_entry=se4,
                    item=item_map[item_code],
                    qty=Decimal(str(qty)),
                    basic_rate=rate,
                    amount=Decimal(str(qty)) * rate,
                    uom=item_map[item_code].uom,
                )
            post_stock_ledger(se4)

        # Material Issues (issues to employees / projects)
        issue_lines = [
            ("HW-LAPTOP-PRO", 4, Decimal("1899.00")),
            ("HW-LAPTOP-STD", 6, Decimal("949.00")),
            ("PRF-MON-27",    4, Decimal("399.00")),
            ("PRF-KB-MECH",   8, Decimal("55.00")),
            ("PRF-MOUSE-ERG", 8, Decimal("35.00")),
            ("PRF-DOCK-USB",  5, Decimal("99.00")),
            ("OFF-PAPER-A4", 30, Decimal("4.50")),
            ("CLN-SANITIZER",20, Decimal("1.80")),
        ]
        total_iss = sum(qty * rate for _, qty, rate in issue_lines)
        se5, created = StockEntry.objects.get_or_create(
            entry_type="issue",
            posting_date=_days_ago(60),
            from_warehouse=hq,
            defaults={
                "status": "submitted",
                "remarks": "Employee equipment issue — Q2 new hires",
                "total_value": total_iss,
            },
        )
        if created:
            for item_code, qty, rate in issue_lines:
                StockEntryDetail.objects.create(
                    stock_entry=se5,
                    item=item_map[item_code],
                    qty=Decimal(str(qty)),
                    basic_rate=rate,
                    amount=Decimal(str(qty)) * rate,
                    uom=item_map[item_code].uom,
                )
            post_stock_ledger(se5)

        # Recent replenishment receipt
        replen_lines = [
            ("HW-LAPTOP-PRO",  8, Decimal("1899.00")),
            ("HW-LAPTOP-STD", 12, Decimal("949.00")),
            ("PRF-MON-27",     8, Decimal("399.00")),
            ("OFF-PAPER-A4",  50, Decimal("4.50")),
            ("OFF-TONER-BK",  10, Decimal("50.00")),
            ("CLN-WIPES",     40, Decimal("3.50")),
        ]
        total_rep = sum(qty * rate for _, qty, rate in replen_lines)
        se6, created = StockEntry.objects.get_or_create(
            entry_type="receipt",
            posting_date=_days_ago(30),
            to_warehouse=hq,
            defaults={
                "status": "submitted",
                "remarks": "Q2 replenishment order",
                "total_value": total_rep,
            },
        )
        if created:
            for item_code, qty, rate in replen_lines:
                StockEntryDetail.objects.create(
                    stock_entry=se6,
                    item=item_map[item_code],
                    qty=Decimal(str(qty)),
                    basic_rate=rate,
                    amount=Decimal(str(qty)) * rate,
                    uom=item_map[item_code].uom,
                )
            post_stock_ledger(se6)

        # Draft entry (not yet submitted)
        se7, _ = StockEntry.objects.get_or_create(
            entry_type="receipt",
            posting_date=TODAY,
            to_warehouse=hq,
            status="draft",
            defaults={
                "remarks": "Pending delivery — new laptop batch",
                "total_value": Decimal("0"),
            },
        )
        if se7.details.count() == 0:
            StockEntryDetail.objects.create(
                stock_entry=se7,
                item=item_map["HW-LAPTOP-PRO"],
                qty=Decimal("10"),
                basic_rate=Decimal("1899.00"),
                amount=Decimal("18990.00"),
                uom=item_map["HW-LAPTOP-PRO"].uom,
            )

        # ── 8. Serial Numbers ─────────────────────────────────────────────────
        self.stdout.write("  Seeding serial numbers…")
        serial_items = [
            ("HW-LAPTOP-PRO",  12, hq, "in_store"),
            ("HW-LAPTOP-STD",  18, hq, "in_store"),
            ("HW-LAPTOP-PRO",   4, ny, "in_store"),
            ("HW-LAPTOP-STD",   5, ny, "in_store"),
            ("HW-LAPTOP-PRO",   3, uk, "in_store"),
            ("HW-SRVR-2U",      5, hq, "in_store"),
            ("NET-SW-24P",      7, hq, "in_store"),
            ("PRF-MON-27",     12, hq, "in_store"),
            # Some delivered
            ("HW-LAPTOP-PRO",   4, None, "delivered"),
            ("HW-LAPTOP-STD",   6, None, "delivered"),
        ]
        sn_counter = 1
        for item_code, qty, warehouse, status in serial_items:
            item = item_map[item_code]
            for _ in range(qty):
                sn = f"SN-{item_code[-3:]}-{str(sn_counter).zfill(6)}"
                SerialNo.objects.get_or_create(
                    serial_no=sn,
                    item=item,
                    defaults={
                        "warehouse": warehouse,
                        "status": status,
                        "purchase_date": _days_ago(random.randint(30, 180)),
                        "warranty_expiry_date": _days_ago(random.randint(-730, -365)),
                    },
                )
                sn_counter += 1

        # ── 9. Reorder Rules ──────────────────────────────────────────────────
        self.stdout.write("  Seeding reorder rules…")
        for item_code, wh_code, reorder_lvl, reorder_qty, safety in REORDER_RULES:
            ReorderRule.objects.get_or_create(
                item=item_map[item_code],
                warehouse=wh_map[wh_code],
                defaults={
                    "re_order_level": Decimal(str(reorder_lvl)),
                    "re_order_qty": Decimal(str(reorder_qty)),
                    "safety_stock": Decimal(str(safety)),
                    "material_request_type": "purchase",
                },
            )

        # ── 10. Cycle Count Sheet ─────────────────────────────────────────────
        self.stdout.write("  Seeding cycle count sheet…")
        from apps.warehouse.models import CycleCountSheet, CycleCountDetail

        sheet, created = CycleCountSheet.objects.get_or_create(
            warehouse=hq,
            count_date=_days_ago(15),
            defaults={"status": "completed", "remarks": "Q2 partial cycle count — HQ Store"},
        )
        if created:
            # Add count lines for a few items with slight variance
            count_items = [
                ("HW-LAPTOP-PRO", Decimal("1899.00"),  12, 11),  # 1 missing
                ("HW-LAPTOP-STD", Decimal("949.00"),   18, 19),  # 1 found extra
                ("PRF-MON-27",    Decimal("399.00"),   12, 12),  # exact
                ("OFF-PAPER-A4",  Decimal("4.50"),     70, 65),  # 5 missing
                ("CLN-SANITIZER", Decimal("1.80"),     60, 60),  # exact
            ]
            for item_code, val_rate, sys_qty, counted in count_items:
                CycleCountDetail.objects.create(
                    sheet=sheet,
                    item=item_map[item_code],
                    system_qty=Decimal(str(sys_qty)),
                    counted_qty=Decimal(str(counted)),
                    variance_qty=Decimal(str(counted - sys_qty)),
                    valuation_rate=val_rate,
                    variance_value=Decimal(str(counted - sys_qty)) * val_rate,
                    is_counted=True,
                )

        # ── Summary ───────────────────────────────────────────────────────────
        self.stdout.write(self.style.SUCCESS(
            f"\n  ✓ Warehouse seed complete:\n"
            f"    {UOM.objects.count()} UOMs, {UOMConversion.objects.count()} conversions\n"
            f"    {ItemCategory.objects.count()} item categories\n"
            f"    {Item.objects.count()} items\n"
            f"    {Warehouse.objects.count()} warehouses, {Bin.objects.count()} bins\n"
            f"    {Batch.objects.count()} batches\n"
            f"    {SerialNo.objects.count()} serial numbers\n"
            f"    {ReorderRule.objects.count()} reorder rules\n"
            f"    {StockEntry.objects.count()} stock entries "
            f"({StockEntry.objects.filter(status='submitted').count()} submitted, "
            f"{StockEntry.objects.filter(status='draft').count()} draft)\n"
            f"    {StockEntryDetail.objects.count()} stock entry lines\n"
            f"    {StockLedger.objects.count()} stock ledger rows\n"
            f"    {CycleCountSheet.objects.count()} cycle count sheet(s), "
            f"{CycleCountDetail.objects.count()} count lines\n"
        ))
