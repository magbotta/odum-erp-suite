"""
Telecommunications models (§7).
Subscriber/service registry, usage-based rating, recurring/prepaid billing, CPQ for bundles.
Depends on: Sales (contracts/CPQ), Accounting (recurring revenue), CRM (subscriber cases).
"""
from __future__ import annotations

from django.db import models

from core.metadata_engine.base_entity import BaseEntity


class ServicePlan(BaseEntity):
    """A product / tariff plan that subscribers can subscribe to (§7)."""

    class BillingType(models.TextChoices):
        PREPAID = "prepaid", "Prepaid"
        POSTPAID = "postpaid", "Postpaid"
        HYBRID = "hybrid", "Hybrid"

    class ServiceType(models.TextChoices):
        VOICE = "voice", "Voice"
        DATA = "data", "Data"
        SMS = "sms", "SMS"
        BUNDLE = "bundle", "Bundle"
        IOT = "iot", "IoT"

    name = models.CharField(max_length=255)
    plan_code = models.CharField(max_length=50, blank=True, db_index=True)
    service_type = models.CharField(max_length=20, choices=ServiceType.choices, default=ServiceType.BUNDLE)
    billing_type = models.CharField(max_length=20, choices=BillingType.choices, default=BillingType.POSTPAID)
    monthly_fee = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    currency = models.CharField(max_length=3, default="USD")
    included_minutes = models.IntegerField(default=0)
    included_sms = models.IntegerField(default=0)
    included_data_mb = models.IntegerField(default=0)
    overage_rate_per_unit = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    contract_months = models.PositiveSmallIntegerField(default=0,
                                                       help_text="0 = month-to-month")
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "telecom_service_plans"

    def __str__(self) -> str:
        return self.name


class Subscriber(BaseEntity):
    """A telecom customer / subscriber account (§7)."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        TERMINATED = "terminated", "Terminated"

    subscriber_number = models.CharField(max_length=50, unique=True, db_index=True)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    business_name = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True, db_index=True)
    phone = models.CharField(max_length=32, blank=True)
    address = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    kyc_verified = models.BooleanField(default=False)
    # Cross-app: CRM Account/Contact
    crm_account_id = models.UUIDField(null=True, blank=True)
    registration_date = models.DateField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "telecom_subscribers"

    def __str__(self) -> str:
        return f"{self.subscriber_number} — {self.first_name} {self.last_name}"


class ServiceSubscription(BaseEntity):
    """
    A subscriber's active subscription to a ServicePlan — the "service line" (§7).
    One subscriber may have multiple subscriptions (e.g. voice + data + IoT SIM).
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending Activation"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        TERMINATED = "terminated", "Terminated"

    subscriber = models.ForeignKey(
        Subscriber, on_delete=models.CASCADE, related_name="subscriptions"
    )
    plan = models.ForeignKey(
        ServicePlan, on_delete=models.PROTECT, related_name="subscriptions"
    )
    msisdn = models.CharField(max_length=20, blank=True, db_index=True,
                              help_text="Mobile Subscriber Integrated Services Digital Network Number")
    iccid = models.CharField(max_length=22, blank=True, db_index=True,
                             help_text="SIM card ICCID")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    activation_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    prepaid_balance = models.DecimalField(max_digits=19, decimal_places=4, default=0,
                                          help_text="For prepaid: remaining balance")
    currency = models.CharField(max_length=3, default="USD")

    class Meta(BaseEntity.Meta):
        db_table = "telecom_subscriptions"

    def __str__(self) -> str:
        return f"{self.subscriber} / {self.plan} ({self.msisdn})"


class UsageRecord(BaseEntity):
    """
    A single CDR (Call/Data Record) for usage-based rating (§7).
    Rated records feed into invoice generation.
    """

    class UsageType(models.TextChoices):
        VOICE_CALL = "voice_call", "Voice Call"
        SMS = "sms", "SMS"
        DATA = "data", "Data Session"
        MMS = "mms", "MMS"

    subscription = models.ForeignKey(
        ServiceSubscription, on_delete=models.CASCADE, related_name="usage_records"
    )
    usage_type = models.CharField(max_length=20, choices=UsageType.choices)
    started_at = models.DateTimeField()
    duration_seconds = models.IntegerField(default=0)
    data_volume_mb = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    destination = models.CharField(max_length=50, blank=True,
                                   help_text="For voice/SMS: destination number")
    is_roaming = models.BooleanField(default=False)
    is_rated = models.BooleanField(default=False)
    rated_amount = models.DecimalField(max_digits=19, decimal_places=6, default=0)
    currency = models.CharField(max_length=3, default="USD")

    class Meta(BaseEntity.Meta):
        db_table = "telecom_usage_records"

    def __str__(self) -> str:
        return f"{self.subscription} — {self.usage_type} [{self.started_at}]"


class TelecomInvoice(BaseEntity):
    """
    A monthly (or ad-hoc) invoice for a subscriber covering recurring fees + overage (§7).
    Cross-app: creates an Accounting SalesInvoice.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ISSUED = "issued", "Issued"
        PAID = "paid", "Paid"
        OVERDUE = "overdue", "Overdue"
        CANCELLED = "cancelled", "Cancelled"

    subscriber = models.ForeignKey(
        Subscriber, on_delete=models.PROTECT, related_name="invoices"
    )
    invoice_number = models.CharField(max_length=50, blank=True, db_index=True)
    billing_period_start = models.DateField()
    billing_period_end = models.DateField()
    recurring_charges = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    usage_charges = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    taxes = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    grand_total = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    currency = models.CharField(max_length=3, default="USD")
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    accounting_invoice_id = models.UUIDField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "telecom_invoices"

    def __str__(self) -> str:
        return f"{self.invoice_number} — {self.subscriber}"
