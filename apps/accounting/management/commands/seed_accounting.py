"""
Management command: seed realistic Accounting dummy data.
Usage: python manage.py seed_accounting [--clear]

Covers: ChartOfAccounts, CostCenters, FiscalYear, AccountingPeriods,
TaxRules, Customers, Vendors, JournalEntries, SalesInvoices,
PurchaseBills, Payments, BankAccounts, BankTransactions, Budgets.
"""
import random
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

User = get_user_model()

TODAY = date.today()
YEAR = TODAY.year


# ── Chart of Accounts ─────────────────────────────────────────────────────────

COA = [
    # (number, name, type, is_group, parent_number)
    # Assets
    ("1000", "Assets",                       "asset",     True,  None),
    ("1100", "Current Assets",               "asset",     True,  "1000"),
    ("1110", "Cash and Cash Equivalents",    "asset",     False, "1100"),
    ("1120", "Accounts Receivable",          "asset",     False, "1100"),
    ("1130", "Inventory",                    "asset",     False, "1100"),
    ("1140", "Prepaid Expenses",             "asset",     False, "1100"),
    ("1200", "Non-Current Assets",           "asset",     True,  "1000"),
    ("1210", "Property Plant & Equipment",   "asset",     False, "1200"),
    ("1220", "Accumulated Depreciation",     "asset",     False, "1200"),
    ("1230", "Intangible Assets",            "asset",     False, "1200"),
    # Liabilities
    ("2000", "Liabilities",                  "liability", True,  None),
    ("2100", "Current Liabilities",          "liability", True,  "2000"),
    ("2110", "Accounts Payable",             "liability", False, "2100"),
    ("2120", "Accrued Liabilities",          "liability", False, "2100"),
    ("2130", "Tax Payable",                  "liability", False, "2100"),
    ("2140", "Deferred Revenue",             "liability", False, "2100"),
    ("2200", "Non-Current Liabilities",      "liability", True,  "2000"),
    ("2210", "Long-term Debt",               "liability", False, "2200"),
    # Equity
    ("3000", "Equity",                       "equity",    True,  None),
    ("3100", "Share Capital",                "equity",    False, "3000"),
    ("3200", "Retained Earnings",            "equity",    False, "3000"),
    ("3300", "Current Year Earnings",        "equity",    False, "3000"),
    # Income
    ("4000", "Revenue",                      "income",    True,  None),
    ("4100", "Software License Revenue",     "income",    False, "4000"),
    ("4200", "Professional Services Revenue","income",    False, "4000"),
    ("4300", "Support & Maintenance Revenue","income",    False, "4000"),
    ("4400", "Other Income",                 "income",    False, "4000"),
    # Expenses
    ("5000", "Operating Expenses",           "expense",   True,  None),
    ("5100", "Cost of Revenue",              "expense",   False, "5000"),
    ("5200", "Salaries & Wages",             "expense",   False, "5000"),
    ("5300", "Rent & Facilities",            "expense",   False, "5000"),
    ("5400", "Software & Subscriptions",     "expense",   False, "5000"),
    ("5500", "Marketing & Advertising",      "expense",   False, "5000"),
    ("5600", "Travel & Entertainment",       "expense",   False, "5000"),
    ("5700", "Depreciation Expense",         "expense",   False, "5000"),
    ("5800", "Professional Fees",            "expense",   False, "5000"),
    ("5900", "Other Operating Expenses",     "expense",   False, "5000"),
]

COST_CENTERS = [
    ("Engineering",   "CC-ENG",  False),
    ("Sales",         "CC-SAL",  False),
    ("Marketing",     "CC-MKT",  False),
    ("Finance",       "CC-FIN",  False),
    ("Operations",    "CC-OPS",  False),
    ("G&A",           "CC-GNA",  False),
]

TAX_RULES = [
    ("US Sales Tax",       "sales_tax",  Decimal("0.0875"), "US"),
    ("UK VAT Standard",    "vat",        Decimal("0.2000"), "GB"),
    ("EU VAT Standard",    "vat",        Decimal("0.2000"), "EU"),
    ("Ghana VAT",          "vat",        Decimal("0.1500"), "GH"),
    ("US Federal WHT",     "withholding",Decimal("0.2100"), "US"),
]

CUSTOMERS = [
    ("Acme Corporation",       "company",    "US-EIN-12-3456789", "Net 30", "USD", 250_000),
    ("Blue Ocean Logistics",   "company",    "US-EIN-98-7654321", "Net 45", "USD", 150_000),
    ("Cascade Health Systems", "company",    "US-EIN-55-1234567", "Net 30", "USD", 500_000),
    ("Delta Financial Group",  "company",    "GB-VAT-123456789",  "Net 60", "GBP", 300_000),
    ("Evergreen Tech Solutions","company",   "US-EIN-22-9876543", "Net 30", "USD", 100_000),
    ("Frontier Education Trust","company",   "US-EIN-33-1122334", "Net 45", "USD", 75_000),
    ("Granite Manufacturing",  "company",    "US-EIN-44-5566778", "Net 30", "USD", 200_000),
    ("Harbor Retail Group",    "company",    "US-EIN-55-8899001", "Net 30", "USD", 400_000),
]

VENDORS = [
    ("AWS (Amazon Web Services)", "Technology",  "US-EIN-91-1144442", "Net 30", "USD"),
    ("Stripe Inc.",               "Financial",   "US-EIN-45-3291785", "Net 30", "USD"),
    ("Google LLC",                "Technology",  "US-EIN-77-0493581", "Net 30", "USD"),
    ("WeWork",                    "Real Estate", "US-EIN-83-1183661", "Net 30", "USD"),
    ("Salesforce Inc.",           "Technology",  "US-EIN-94-3320396", "Net 30", "USD"),
    ("Deloitte LLP",              "Professional","US-EIN-13-5563760", "Net 45", "USD"),
    ("Office Depot",              "Supplies",    "US-EIN-59-2663954", "Net 15", "USD"),
    ("Delta Air Lines",           "Travel",      "US-EIN-58-0218548", "Net 30", "USD"),
]

INVOICE_SCENARIOS = [
    # (customer_idx, description, net_total, tax_pct, days_ago, status)
    (0, "Odum ERP Annual License — Acme Corp",        120_000, Decimal("0.0875"), 75, "paid"),
    (1, "WMS Module Implementation — Blue Ocean",      68_500, Decimal("0.0875"), 60, "paid"),
    (2, "HIS Phase 1 License — Cascade Health",       185_000, Decimal("0.0875"), 45, "submitted"),
    (3, "CRM & Reporting Suite — Delta Financial",     72_000, Decimal("0.2000"), 40, "submitted"),
    (4, "Developer Platform License — Evergreen",      48_000, Decimal("0.0875"), 30, "submitted"),
    (5, "SIS Implementation — Frontier Education",     61_000, Decimal("0.0875"), 20, "draft"),
    (6, "MRP Upgrade — Granite Manufacturing",        105_000, Decimal("0.0875"), 15, "draft"),
    (7, "POS Rollout 40 Stores — Harbor Retail",      175_000, Decimal("0.0875"), 10, "draft"),
    (0, "Professional Services Q3 — Acme",             35_000, Decimal("0.0875"), 90, "paid"),
    (1, "Support & Maintenance Y1 — Blue Ocean",       12_000, Decimal("0.0875"), 80, "paid"),
    (2, "Support & Maintenance Y1 — Cascade",          22_000, Decimal("0.0875"), 50, "submitted"),
]

BILL_SCENARIOS = [
    # (vendor_idx, description, amount, days_ago, status)
    (0, "AWS EC2 & RDS — June 2026",          8_420, 35, "paid"),
    (0, "AWS EC2 & RDS — May 2026",           7_890, 65, "paid"),
    (1, "Stripe Payment Processing Fees Q2",   3_150, 40, "paid"),
    (2, "Google Workspace — Annual",           4_800, 50, "paid"),
    (3, "WeWork HQ Office — July 2026",       18_000, 15, "submitted"),
    (3, "WeWork HQ Office — June 2026",       18_000, 45, "paid"),
    (4, "Salesforce CRM License (Migration)", 12_400, 60, "paid"),
    (5, "Deloitte Audit Services Q2",         45_000, 55, "submitted"),
    (6, "Office Supplies — Q2 2026",           1_280, 40, "paid"),
    (7, "Team Travel — Sales Conference",      6_750, 25, "submitted"),
]

JOURNAL_ENTRIES = [
    # (date_offset_days, narration, lines: [(account_num, debit, credit)])
    (-180, "Opening Balance Entry", [
        ("1110", 500_000, 0),
        ("1210", 120_000, 0),
        ("2210",       0, 80_000),
        ("3100",       0, 540_000),
    ]),
    (-90, "Payroll — April 2026", [
        ("5200", 95_000, 0),
        ("1110",      0, 95_000),
    ]),
    (-60, "Payroll — May 2026", [
        ("5200", 97_500, 0),
        ("1110",      0, 97_500),
    ]),
    (-30, "Payroll — June 2026", [
        ("5200", 99_200, 0),
        ("1110",      0, 99_200),
    ]),
    (-90, "Monthly Depreciation — Q2", [
        ("5700", 3_500, 0),
        ("1220",     0, 3_500),
    ]),
    (-60, "Prepaid Insurance Amortization", [
        ("5900", 1_200, 0),
        ("1140",     0, 1_200),
    ]),
    (-45, "Inter-company Recharge — Engineering to Sales", [
        ("5100", 12_000, 0),
        ("4400",      0, 12_000),
    ]),
]

BANK_ACCOUNTS = [
    ("Primary Operating Account",  "Chase Bank",      "****4821", "USD", "current"),
    ("Payroll Account",            "Chase Bank",      "****9034", "USD", "current"),
    ("GBP Collections Account",    "Barclays Bank",   "****2277", "GBP", "current"),
    ("Reserve / Savings",          "Chase Bank",      "****7755", "USD", "savings"),
]


class Command(BaseCommand):
    help = "Seed realistic Accounting dummy data across all 14 entities."

    def add_arguments(self, parser):
        parser.add_argument("--clear", action="store_true", help="Delete existing accounting data before seeding")

    def handle(self, *args, **options):
        from apps.accounting.models import (
            AccountingPeriod, BankAccount, BankTransaction, Budget, BudgetEntry,
            ChartOfAccount, CostCenter, Customer, FiscalYear, JournalEntry,
            JournalEntryLine, Payment, PaymentAllocation, PurchaseBill,
            PurchaseBillItem, SalesInvoice, SalesInvoiceItem, TaxRule, Vendor,
        )

        if options["clear"]:
            self.stdout.write("  Clearing existing accounting data…")
            for Model in [
                PaymentAllocation, BankTransaction, BudgetEntry, Budget,
                SalesInvoiceItem, SalesInvoice, PurchaseBillItem, PurchaseBill,
                Payment, JournalEntryLine, JournalEntry, BankAccount,
                AccountingPeriod, FiscalYear, TaxRule, Customer, Vendor,
                CostCenter, ChartOfAccount,
            ]:
                Model.objects.all().delete()
            self.stdout.write(self.style.WARNING("  Cleared."))

        admin = User.objects.filter(is_superuser=True).first()

        # ── 1. Chart of Accounts ──────────────────────────────────────────────
        self.stdout.write("  Seeding chart of accounts…")
        coa_map = {}  # number → obj
        for number, name, acct_type, is_group, parent_num in COA:
            parent = coa_map.get(parent_num) if parent_num else None
            obj, _ = ChartOfAccount.objects.get_or_create(
                account_number=number,
                defaults={
                    "account_name": name,
                    "account_type": acct_type,
                    "is_group": is_group,
                    "parent": parent,
                    "is_active": True,
                },
            )
            coa_map[number] = obj

        # Helper: look up a leaf account by number
        def acct(num):
            return coa_map[num]

        # ── 2. Cost Centers ───────────────────────────────────────────────────
        self.stdout.write("  Seeding cost centers…")
        cc_objs = []
        for name, number, is_group in COST_CENTERS:
            obj, _ = CostCenter.objects.get_or_create(
                cost_center_number=number, defaults={"name": name, "is_group": is_group, "is_active": True}
            )
            cc_objs.append(obj)

        # ── 3. Fiscal Year + Periods ──────────────────────────────────────────
        self.stdout.write("  Seeding fiscal year and periods…")
        fy, _ = FiscalYear.objects.get_or_create(
            year_name=f"FY {YEAR}",
            defaults={
                "start_date": date(YEAR, 1, 1),
                "end_date": date(YEAR, 12, 31),
                "is_active": True,
                "is_closed": False,
            },
        )
        period_defs = [
            (f"Jan {YEAR}", date(YEAR,1,1),  date(YEAR,1,31),  True),
            (f"Feb {YEAR}", date(YEAR,2,1),  date(YEAR,2,28),  True),
            (f"Mar {YEAR}", date(YEAR,3,1),  date(YEAR,3,31),  True),
            (f"Apr {YEAR}", date(YEAR,4,1),  date(YEAR,4,30),  True),
            (f"May {YEAR}", date(YEAR,5,1),  date(YEAR,5,31),  True),
            (f"Jun {YEAR}", date(YEAR,6,1),  date(YEAR,6,30),  True),
            (f"Jul {YEAR}", date(YEAR,7,1),  date(YEAR,7,31),  False),
            (f"Aug {YEAR}", date(YEAR,8,1),  date(YEAR,8,31),  False),
            (f"Sep {YEAR}", date(YEAR,9,1),  date(YEAR,9,30),  False),
            (f"Oct {YEAR}", date(YEAR,10,1), date(YEAR,10,31), False),
            (f"Nov {YEAR}", date(YEAR,11,1), date(YEAR,11,30), False),
            (f"Dec {YEAR}", date(YEAR,12,1), date(YEAR,12,31), False),
        ]
        period_objs = []
        for pname, pstart, pend, closed in period_defs:
            p, _ = AccountingPeriod.objects.get_or_create(
                fiscal_year=fy, period_name=pname,
                defaults={"start_date": pstart, "end_date": pend, "is_closed": closed},
            )
            period_objs.append(p)

        # ── 4. Tax Rules ──────────────────────────────────────────────────────
        self.stdout.write("  Seeding tax rules…")
        tax_objs = []
        for tname, ttype, rate, jurisdiction in TAX_RULES:
            t, _ = TaxRule.objects.get_or_create(
                tax_name=tname,
                defaults={
                    "tax_type": ttype,
                    "rate": rate,
                    "jurisdiction": jurisdiction,
                    "account": acct("2130"),
                    "is_active": True,
                },
            )
            tax_objs.append(t)

        # ── 5. Customers ──────────────────────────────────────────────────────
        self.stdout.write("  Seeding customers…")
        cust_objs = []
        for cname, ctype, tax_id, terms, currency, limit in CUSTOMERS:
            c, _ = Customer.objects.get_or_create(
                customer_name=cname,
                defaults={
                    "customer_type": ctype,
                    "tax_id": tax_id,
                    "payment_terms": terms,
                    "default_currency": currency,
                    "credit_limit": Decimal(str(limit)),
                    "is_active": True,
                },
            )
            cust_objs.append(c)

        # ── 6. Vendors ────────────────────────────────────────────────────────
        self.stdout.write("  Seeding vendors…")
        vendor_objs = []
        for vname, vtype, tax_id, terms, currency in VENDORS:
            v, _ = Vendor.objects.get_or_create(
                vendor_name=vname,
                defaults={
                    "vendor_type": vtype,
                    "tax_id": tax_id,
                    "payment_terms": terms,
                    "default_currency": currency,
                    "is_active": True,
                },
            )
            vendor_objs.append(v)

        # ── 7. Bank Accounts ──────────────────────────────────────────────────
        self.stdout.write("  Seeding bank accounts…")
        bank_objs = []
        for bname, bank, acct_num, currency, btype in BANK_ACCOUNTS:
            b, _ = BankAccount.objects.get_or_create(
                account_name=bname,
                defaults={
                    "bank_name": bank,
                    "account_number": acct_num,
                    "currency": currency,
                    "bank_account_type": btype,
                    "linked_gl_account": acct("1110"),
                    "is_active": True,
                },
            )
            bank_objs.append(b)

        # ── 8. Journal Entries ────────────────────────────────────────────────
        self.stdout.write("  Seeding journal entries…")
        je_objs = []
        for day_offset, narration, lines in JOURNAL_ENTRIES:
            post_date = TODAY + timedelta(days=day_offset)
            je, created = JournalEntry.objects.get_or_create(
                narration=narration,
                defaults={
                    "entry_type": "opening" if "Opening" in narration else "journal",
                    "posting_date": post_date,
                    "status": "submitted",
                    "submitted_at": timezone.now() + timedelta(days=day_offset),
                    "submitted_by": admin,
                },
            )
            if created:
                total_dr = Decimal("0")
                total_cr = Decimal("0")
                for acct_num, dr, cr in lines:
                    dr_d = Decimal(str(dr))
                    cr_d = Decimal(str(cr))
                    JournalEntryLine.objects.create(
                        entry=je,
                        account=acct(acct_num),
                        debit_amount=dr_d,
                        credit_amount=cr_d,
                        currency="USD",
                        cost_center=random.choice(cc_objs) if dr > 0 and acct_num.startswith("5") else None,
                    )
                    total_dr += dr_d
                    total_cr += cr_d
                je.total_debit = total_dr
                je.total_credit = total_cr
                je.save(update_fields=["total_debit", "total_credit"])
            je_objs.append(je)

        # ── 9. Sales Invoices ─────────────────────────────────────────────────
        self.stdout.write("  Seeding sales invoices…")
        inv_objs = []
        for i, (cust_idx, desc, net, tax_rate, days_ago, status) in enumerate(INVOICE_SCENARIOS):
            inv_num = f"INV-{YEAR}-{str(i+1).zfill(4)}"
            post_date = TODAY - timedelta(days=days_ago)
            due_date = post_date + timedelta(days=30)
            tax_amt = (Decimal(str(net)) * tax_rate).quantize(Decimal("0.0001"))
            grand = Decimal(str(net)) + tax_amt
            paid_amt = grand if status == "paid" else Decimal("0")
            outstanding = Decimal("0") if status == "paid" else grand

            inv, created = SalesInvoice.objects.get_or_create(
                invoice_number=inv_num,
                defaults={
                    "customer": cust_objs[cust_idx],
                    "posting_date": post_date,
                    "due_date": due_date,
                    "currency": "USD",
                    "net_total": Decimal(str(net)),
                    "tax_total": tax_amt,
                    "grand_total": grand,
                    "outstanding_amount": outstanding,
                    "paid_amount": paid_amt,
                    "status": status,
                    "notes": f"Auto-generated invoice for {desc}",
                },
            )
            if created:
                # Determine income account
                if "License" in desc:
                    income_acct = acct("4100")
                elif "Services" in desc or "Implementation" in desc:
                    income_acct = acct("4200")
                else:
                    income_acct = acct("4300")

                SalesInvoiceItem.objects.create(
                    invoice=inv,
                    item_description=desc,
                    qty=Decimal("1"),
                    rate=Decimal(str(net)),
                    amount=Decimal(str(net)),
                    income_account=income_acct,
                )

                # Post GL for submitted/paid invoices
                if status in ("submitted", "paid"):
                    je = JournalEntry.objects.create(
                        entry_type="journal",
                        posting_date=post_date,
                        narration=f"Sales Invoice {inv_num}",
                        voucher_type="SalesInvoice",
                        voucher_no=str(inv.pk),
                        status="submitted",
                        total_debit=grand,
                        total_credit=grand,
                        submitted_at=timezone.now() - timedelta(days=days_ago),
                    )
                    JournalEntryLine.objects.create(
                        entry=je, account=acct("1120"),
                        debit_amount=grand, credit_amount=Decimal("0"),
                        currency="USD", party_type="Customer", party_id=inv.customer_id,
                    )
                    JournalEntryLine.objects.create(
                        entry=je, account=income_acct,
                        debit_amount=Decimal("0"), credit_amount=Decimal(str(net)),
                        currency="USD",
                    )
                    JournalEntryLine.objects.create(
                        entry=je, account=acct("2130"),
                        debit_amount=Decimal("0"), credit_amount=tax_amt,
                        currency="USD",
                    )
                    inv.journal_entry = je
                    inv.save(update_fields=["journal_entry"])
            inv_objs.append(inv)

        # ── 10. Purchase Bills ────────────────────────────────────────────────
        self.stdout.write("  Seeding purchase bills…")
        bill_objs = []
        for i, (vend_idx, desc, amount, days_ago, status) in enumerate(BILL_SCENARIOS):
            bill_num = f"BILL-{YEAR}-{str(i+1).zfill(4)}"
            post_date = TODAY - timedelta(days=days_ago)
            due_date = post_date + timedelta(days=30)
            amt = Decimal(str(amount))

            bill, created = PurchaseBill.objects.get_or_create(
                bill_number=bill_num,
                defaults={
                    "vendor": vendor_objs[vend_idx],
                    "vendor_invoice_number": f"EXT-{random.randint(10000,99999)}",
                    "posting_date": post_date,
                    "due_date": due_date,
                    "currency": "USD",
                    "grand_total": amt,
                    "outstanding_amount": Decimal("0") if status == "paid" else amt,
                    "status": status,
                },
            )
            if created:
                # Determine expense account
                vname = vendor_objs[vend_idx].vendor_name.lower()
                if "aws" in vname or "google" in vname or "salesforce" in vname:
                    exp_acct = acct("5400")
                elif "wework" in vname:
                    exp_acct = acct("5300")
                elif "deloitte" in vname:
                    exp_acct = acct("5800")
                elif "delta" in vname:
                    exp_acct = acct("5600")
                elif "stripe" in vname:
                    exp_acct = acct("5100")
                else:
                    exp_acct = acct("5900")

                PurchaseBillItem.objects.create(
                    bill=bill,
                    description=desc,
                    qty=Decimal("1"),
                    rate=amt,
                    amount=amt,
                    expense_account=exp_acct,
                )

                if status in ("submitted", "paid"):
                    je = JournalEntry.objects.create(
                        entry_type="journal",
                        posting_date=post_date,
                        narration=f"Purchase Bill {bill_num}",
                        voucher_type="PurchaseBill",
                        voucher_no=str(bill.pk),
                        status="submitted",
                        total_debit=amt,
                        total_credit=amt,
                        submitted_at=timezone.now() - timedelta(days=days_ago),
                    )
                    JournalEntryLine.objects.create(
                        entry=je, account=exp_acct,
                        debit_amount=amt, credit_amount=Decimal("0"), currency="USD",
                    )
                    JournalEntryLine.objects.create(
                        entry=je, account=acct("2110"),
                        debit_amount=Decimal("0"), credit_amount=amt,
                        currency="USD", party_type="Vendor", party_id=bill.vendor_id,
                    )
                    bill.journal_entry = je
                    bill.save(update_fields=["journal_entry"])
            bill_objs.append(bill)

        # ── 11. Payments ──────────────────────────────────────────────────────
        self.stdout.write("  Seeding payments…")
        payment_objs = []
        # Customer receipts for paid invoices
        for inv in inv_objs:
            if inv.status == "paid" and inv.paid_amount > 0:
                pay, created = Payment.objects.get_or_create(
                    party_id=inv.customer_id,
                    amount=inv.paid_amount,
                    payment_date=inv.due_date or inv.posting_date + timedelta(days=28),
                    defaults={
                        "payment_type": "receive",
                        "party_type": "customer",
                        "currency": inv.currency,
                        "mode_of_payment": random.choice(["bank_transfer", "card"]),
                        "status": "processed",
                        "reference_number": f"TXN-{random.randint(100000,999999)}",
                    },
                )
                if created:
                    PaymentAllocation.objects.get_or_create(
                        payment=pay,
                        invoice_id=inv.pk,
                        defaults={
                            "invoice_type": "SalesInvoice",
                            "allocated_amount": inv.paid_amount,
                            "currency": inv.currency,
                            "allocation_date": pay.payment_date,
                        },
                    )
                payment_objs.append(pay)

        # Vendor payments for paid bills
        for bill in bill_objs:
            if bill.status == "paid":
                pay, created = Payment.objects.get_or_create(
                    party_id=bill.vendor_id,
                    amount=bill.grand_total,
                    payment_date=bill.due_date or bill.posting_date + timedelta(days=28),
                    defaults={
                        "payment_type": "pay",
                        "party_type": "vendor",
                        "currency": bill.currency,
                        "mode_of_payment": "bank_transfer",
                        "status": "processed",
                        "reference_number": f"PAY-{random.randint(100000,999999)}",
                    },
                )
                if created:
                    PaymentAllocation.objects.get_or_create(
                        payment=pay,
                        invoice_id=bill.pk,
                        defaults={
                            "invoice_type": "PurchaseBill",
                            "allocated_amount": bill.grand_total,
                            "currency": bill.currency,
                            "allocation_date": pay.payment_date,
                        },
                    )
                payment_objs.append(pay)

        # ── 12. Bank Transactions ─────────────────────────────────────────────
        self.stdout.write("  Seeding bank transactions…")
        primary_bank = bank_objs[0]
        running_balance = Decimal("500000")
        txn_count = 0

        # Credits: customer receipts
        for pay in payment_objs:
            if pay.payment_type == "receive" and pay.status == "processed":
                running_balance += pay.amount
                BankTransaction.objects.get_or_create(
                    bank_account=primary_bank,
                    reference=pay.reference_number,
                    defaults={
                        "transaction_date": pay.payment_date,
                        "description": f"Customer Receipt — {pay.reference_number}",
                        "debit_amount": Decimal("0"),
                        "credit_amount": pay.amount,
                        "running_balance": running_balance,
                        "transaction_type": "credit",
                        "is_reconciled": True,
                    },
                )
                txn_count += 1

        # Debits: vendor payments + payroll
        for pay in payment_objs:
            if pay.payment_type == "pay" and pay.status == "processed":
                running_balance -= pay.amount
                BankTransaction.objects.get_or_create(
                    bank_account=primary_bank,
                    reference=pay.reference_number,
                    defaults={
                        "transaction_date": pay.payment_date,
                        "description": f"Vendor Payment — {pay.reference_number}",
                        "debit_amount": pay.amount,
                        "credit_amount": Decimal("0"),
                        "running_balance": running_balance,
                        "transaction_type": "debit",
                        "is_reconciled": True,
                    },
                )
                txn_count += 1

        # A few unreconciled transactions
        for desc, dr, cr in [
            ("Stripe Payout — July W1", Decimal("0"), Decimal("42300")),
            ("AWS Auto-pay", Decimal("8420"), Decimal("0")),
            ("Unknown Credit", Decimal("0"), Decimal("5000")),
        ]:
            running_balance = running_balance - dr + cr
            BankTransaction.objects.get_or_create(
                description=desc,
                defaults={
                    "bank_account": primary_bank,
                    "transaction_date": TODAY - timedelta(days=random.randint(1, 7)),
                    "debit_amount": dr,
                    "credit_amount": cr,
                    "running_balance": running_balance,
                    "transaction_type": "credit" if cr > 0 else "debit",
                    "is_reconciled": False,
                    "reference": f"STMT-{random.randint(1000,9999)}",
                },
            )
            txn_count += 1

        # ── 13. Budgets ───────────────────────────────────────────────────────
        self.stdout.write("  Seeding budgets…")
        budget_lines = [
            # (account_num, q1, q2, q3, q4)
            ("4100", 300_000, 350_000, 380_000, 420_000),
            ("4200",  80_000,  90_000, 100_000, 110_000),
            ("4300",  40_000,  45_000,  50_000,  55_000),
            ("5200", 280_000, 290_000, 300_000, 310_000),
            ("5300",  54_000,  54_000,  54_000,  54_000),
            ("5400",  30_000,  32_000,  34_000,  36_000),
            ("5500",  25_000,  30_000,  35_000,  40_000),
            ("5600",  15_000,  18_000,  20_000,  22_000),
            ("5800",  45_000,  45_000,  45_000,  45_000),
        ]

        budget, _ = Budget.objects.get_or_create(
            budget_name=f"Annual Operating Budget {YEAR}",
            defaults={
                "fiscal_year": fy,
                "status": "Active",
                "total_budgeted": Decimal(str(sum(q1+q2+q3+q4 for _, q1, q2, q3, q4 in budget_lines))),
                "notes": f"Approved board budget for FY {YEAR}",
            },
        )
        for acct_num, q1, q2, q3, q4 in budget_lines:
            BudgetEntry.objects.get_or_create(
                budget=budget,
                account=acct(acct_num),
                defaults={
                    "q1_amount": Decimal(str(q1)),
                    "q2_amount": Decimal(str(q2)),
                    "q3_amount": Decimal(str(q3)),
                    "q4_amount": Decimal(str(q4)),
                },
            )

        # ── Summary ───────────────────────────────────────────────────────────
        from apps.accounting.models import (
            AccountingPeriod, BankAccount, BankTransaction, Budget, BudgetEntry,
            ChartOfAccount, CostCenter, Customer, FiscalYear, JournalEntry,
            JournalEntryLine, Payment, PaymentAllocation, PurchaseBill,
            PurchaseBillItem, SalesInvoice, SalesInvoiceItem, TaxRule, Vendor,
        )
        self.stdout.write(self.style.SUCCESS(
            f"\n  ✓ Accounting seed complete:\n"
            f"    {ChartOfAccount.objects.count()} GL accounts (chart of accounts)\n"
            f"    {CostCenter.objects.count()} cost centers\n"
            f"    {FiscalYear.objects.count()} fiscal year(s), {AccountingPeriod.objects.count()} periods "
            f"({AccountingPeriod.objects.filter(is_closed=True).count()} closed)\n"
            f"    {TaxRule.objects.count()} tax rules\n"
            f"    {Customer.objects.count()} customers\n"
            f"    {Vendor.objects.count()} vendors\n"
            f"    {BankAccount.objects.count()} bank accounts\n"
            f"    {JournalEntry.objects.count()} journal entries ({JournalEntryLine.objects.count()} lines)\n"
            f"    {SalesInvoice.objects.count()} sales invoices ({SalesInvoiceItem.objects.count()} line items)\n"
            f"    {PurchaseBill.objects.count()} purchase bills ({PurchaseBillItem.objects.count()} line items)\n"
            f"    {Payment.objects.count()} payments ({PaymentAllocation.objects.count()} allocations)\n"
            f"    {BankTransaction.objects.count()} bank transactions "
            f"({BankTransaction.objects.filter(is_reconciled=False).count()} unreconciled)\n"
            f"    {Budget.objects.count()} budget(s) ({BudgetEntry.objects.count()} budget entries)\n"
        ))
