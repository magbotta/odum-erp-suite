"""Asset Management models (§6.2): lifecycle, depreciation, maintenance, movement, audit, lease."""
from __future__ import annotations

from django.conf import settings
from django.db import models

from core.metadata_engine.base_entity import BaseEntity


class AssetCategory(BaseEntity):
    """Groups assets with shared depreciation rules (§6.2)."""

    class DepreciationMethod(models.TextChoices):
        STRAIGHT_LINE = "straight_line", "Straight Line"
        DECLINING_BALANCE = "declining_balance", "Declining Balance"
        UNITS_OF_PRODUCTION = "units_of_production", "Units of Production"

    name = models.CharField(max_length=150, unique=True)
    depreciation_method = models.CharField(
        max_length=30, choices=DepreciationMethod.choices, default=DepreciationMethod.STRAIGHT_LINE
    )
    useful_life_years = models.PositiveSmallIntegerField(default=5)
    salvage_value_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text="Residual value as % of purchase price",
    )
    # Cross-app GL account UUIDs (soft refs to accounting.ChartOfAccount)
    asset_account_id = models.UUIDField(null=True, blank=True)
    depreciation_expense_account_id = models.UUIDField(null=True, blank=True)
    accumulated_depreciation_account_id = models.UUIDField(null=True, blank=True)
    disposal_gain_account_id = models.UUIDField(null=True, blank=True)
    disposal_loss_account_id = models.UUIDField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "asset_categories"
        verbose_name = "Asset Category"
        verbose_name_plural = "Asset Categories"

    def __str__(self) -> str:
        return self.name


class Asset(BaseEntity):
    """
    A fixed or intangible asset tracked through its full lifecycle (§6.2):
    acquisition → active → maintenance/revaluation → disposal/write-off.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        UNDER_MAINTENANCE = "under_maintenance", "Under Maintenance"
        SCRAPPED = "scrapped", "Scrapped"
        SOLD = "sold", "Sold"

    asset_name = models.CharField(max_length=255)
    asset_code = models.CharField(max_length=50, unique=True, db_index=True)
    category = models.ForeignKey(AssetCategory, on_delete=models.PROTECT, related_name="assets")
    status = models.CharField(max_length=25, choices=Status.choices, default=Status.DRAFT)
    purchase_date = models.DateField()
    purchase_price = models.DecimalField(max_digits=19, decimal_places=4)
    current_value = models.DecimalField(max_digits=19, decimal_places=4)
    salvage_value = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    useful_life_years = models.PositiveSmallIntegerField()
    depreciation_method = models.CharField(max_length=30, blank=True)
    depreciation_start_date = models.DateField(null=True, blank=True)
    fully_depreciated = models.BooleanField(default=False)
    location = models.CharField(max_length=255, blank=True)
    barcode = models.CharField(max_length=100, blank=True, db_index=True)
    serial_no = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    # Cross-app soft links
    custodian_employee_id = models.UUIDField(null=True, blank=True)
    custodian_name = models.CharField(max_length=255, blank=True)
    purchase_order_id = models.UUIDField(null=True, blank=True)
    # Disposal fields
    disposal_date = models.DateField(null=True, blank=True)
    disposal_amount = models.DecimalField(max_digits=19, decimal_places=4, null=True, blank=True)
    disposal_reason = models.TextField(blank=True)
    # Accumulated depreciation tracked here for quick reporting
    accumulated_depreciation = models.DecimalField(max_digits=19, decimal_places=4, default=0)

    class Meta(BaseEntity.Meta):
        db_table = "assets"

    def __str__(self) -> str:
        return "{} — {}".format(self.asset_code, self.asset_name)


class AssetDepreciationSchedule(BaseEntity):
    """
    One row of the auto-generated depreciation schedule for an asset (§6.2).
    Posted = a JournalEntry has been created for this row.
    """

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="depreciation_schedule")
    schedule_date = models.DateField()
    depreciation_amount = models.DecimalField(max_digits=19, decimal_places=4)
    accumulated_depreciation = models.DecimalField(max_digits=19, decimal_places=4)
    book_value_after = models.DecimalField(max_digits=19, decimal_places=4)
    is_posted = models.BooleanField(default=False)
    journal_entry_id = models.UUIDField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "asset_depreciation_schedule"
        ordering = ["asset", "schedule_date"]

    def __str__(self) -> str:
        return "{} — {} — {}".format(self.asset, self.schedule_date, self.depreciation_amount)


class AssetRevaluation(BaseEntity):
    """
    Records a revaluation or impairment event for an asset (§6.2).
    Updates current_value and posts a GL entry for the difference.
    """

    class RevaluationType(models.TextChoices):
        REVALUATION = "revaluation", "Upward Revaluation"
        IMPAIRMENT = "impairment", "Impairment / Write-down"

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="revaluations")
    revaluation_date = models.DateField()
    revaluation_type = models.CharField(
        max_length=20, choices=RevaluationType.choices, default=RevaluationType.IMPAIRMENT
    )
    previous_value = models.DecimalField(max_digits=19, decimal_places=4)
    new_value = models.DecimalField(max_digits=19, decimal_places=4)
    adjustment_amount = models.DecimalField(max_digits=19, decimal_places=4)
    reason = models.TextField(blank=True)
    journal_entry_id = models.UUIDField(null=True, blank=True)
    is_posted = models.BooleanField(default=False)

    class Meta(BaseEntity.Meta):
        db_table = "asset_revaluations"
        ordering = ["asset", "revaluation_date"]

    def __str__(self) -> str:
        return "{} — {} [{}]".format(
            self.asset, self.get_revaluation_type_display(), self.revaluation_date
        )


class AssetMaintenance(BaseEntity):
    """A maintenance record (preventive or corrective) for an asset (§6.2)."""

    class MaintenanceType(models.TextChoices):
        PREVENTIVE = "preventive", "Preventive"
        CORRECTIVE = "corrective", "Corrective"
        INSPECTION = "inspection", "Inspection"

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="maintenance_records")
    maintenance_type = models.CharField(
        max_length=20, choices=MaintenanceType.choices, default=MaintenanceType.PREVENTIVE
    )
    scheduled_date = models.DateField()
    completion_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SCHEDULED)
    cost = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    description = models.TextField(blank=True)
    performed_by = models.CharField(max_length=255, blank=True)
    next_maintenance_date = models.DateField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "asset_maintenance"

    def __str__(self) -> str:
        return "{} — {} [{}]".format(self.asset, self.maintenance_type, self.scheduled_date)


class AssetMovement(BaseEntity):
    """Records a transfer of an asset between locations or custodians (§6.2)."""

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="movements")
    movement_date = models.DateField()
    from_location = models.CharField(max_length=255)
    to_location = models.CharField(max_length=255)
    from_custodian_id = models.UUIDField(null=True, blank=True)
    to_custodian_id = models.UUIDField(null=True, blank=True)
    from_custodian_name = models.CharField(max_length=255, blank=True)
    to_custodian_name = models.CharField(max_length=255, blank=True)
    purpose = models.CharField(max_length=255, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="asset_movements_approved",
    )

    class Meta(BaseEntity.Meta):
        db_table = "asset_movements"

    def __str__(self) -> str:
        return "{} -> {} [{}]".format(self.asset, self.to_location, self.movement_date)


class AssetAudit(BaseEntity):
    """
    A physical asset audit / cycle count session (§6.2).
    Scans barcodes/RFID to verify location and condition of each asset.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    audit_number = models.CharField(max_length=50, blank=True, db_index=True)
    audit_date = models.DateField()
    location_filter = models.CharField(max_length=255, blank=True, help_text="Restrict to assets at this location")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    conducted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="asset_audits",
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    total_assets_expected = models.PositiveIntegerField(default=0)
    total_assets_found = models.PositiveIntegerField(default=0)
    total_assets_missing = models.PositiveIntegerField(default=0)

    class Meta(BaseEntity.Meta):
        db_table = "asset_audits"

    def __str__(self) -> str:
        return "Audit {} [{}]".format(self.audit_number or str(self.pk)[:8], self.audit_date)


class AssetAuditLine(BaseEntity):
    """One scanned asset within a physical audit (§6.2)."""

    class Condition(models.TextChoices):
        GOOD = "good", "Good"
        FAIR = "fair", "Fair"
        POOR = "poor", "Poor"
        DAMAGED = "damaged", "Damaged"

    class FindingStatus(models.TextChoices):
        FOUND = "found", "Found"
        MISSING = "missing", "Missing"
        EXCESS = "excess", "Excess / Unregistered"

    audit = models.ForeignKey(AssetAudit, on_delete=models.CASCADE, related_name="lines")
    asset = models.ForeignKey(Asset, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_lines")
    scanned_barcode = models.CharField(max_length=100, blank=True)
    expected_location = models.CharField(max_length=255, blank=True)
    found_location = models.CharField(max_length=255, blank=True)
    finding_status = models.CharField(max_length=10, choices=FindingStatus.choices, default=FindingStatus.FOUND)
    condition = models.CharField(max_length=10, choices=Condition.choices, blank=True)
    notes = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "asset_audit_lines"

    def __str__(self) -> str:
        return "{} / {} — {}".format(self.audit, self.asset, self.finding_status)


class AssetInsurance(BaseEntity):
    """Insurance policy covering an asset with expiry tracking (§6.2)."""

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="insurance_policies")
    policy_number = models.CharField(max_length=100)
    insurer_name = models.CharField(max_length=255)
    insured_value = models.DecimalField(max_digits=19, decimal_places=2)
    annual_premium = models.DecimalField(max_digits=19, decimal_places=2, default=0)
    policy_start = models.DateField()
    policy_end = models.DateField()
    coverage_description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta(BaseEntity.Meta):
        db_table = "asset_insurance"
        verbose_name = "Asset Insurance"
        verbose_name_plural = "Asset Insurance Policies"

    def __str__(self) -> str:
        return "{} — {} ({}–{})".format(
            self.asset, self.insurer_name, self.policy_start, self.policy_end
        )


class AssetWarranty(BaseEntity):
    """Warranty record for an asset with expiry alert support (§6.2)."""

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="warranties")
    warranty_number = models.CharField(max_length=100, blank=True)
    vendor_name = models.CharField(max_length=255)
    warranty_start = models.DateField()
    warranty_end = models.DateField()
    coverage_description = models.TextField(blank=True)
    is_extended = models.BooleanField(default=False, help_text="True if this is an extended/purchased warranty")
    is_active = models.BooleanField(default=True)

    class Meta(BaseEntity.Meta):
        db_table = "asset_warranties"
        verbose_name = "Asset Warranty"
        verbose_name_plural = "Asset Warranties"

    def __str__(self) -> str:
        return "{} — {} warranty (expires {})".format(self.asset, self.vendor_name, self.warranty_end)


class LeaseAgreement(BaseEntity):
    """
    A lease agreement creating a right-of-use (ROU) asset and lease liability
    per ASC 842 / IFRS 16 (§6.2).
    """

    class LeaseType(models.TextChoices):
        FINANCE = "finance", "Finance Lease"
        OPERATING = "operating", "Operating Lease"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        TERMINATED = "terminated", "Terminated"
        EXPIRED = "expired", "Expired"

    lease_number = models.CharField(max_length=50, blank=True, db_index=True)
    # The underlying asset (the ROU asset)
    asset = models.ForeignKey(Asset, null=True, blank=True, on_delete=models.SET_NULL, related_name="leases")
    description = models.CharField(max_length=255)
    lessor_name = models.CharField(max_length=255)
    lease_type = models.CharField(max_length=10, choices=LeaseType.choices, default=LeaseType.OPERATING)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.DRAFT)
    commencement_date = models.DateField()
    end_date = models.DateField()
    lease_term_months = models.PositiveIntegerField(default=0)
    monthly_payment = models.DecimalField(max_digits=19, decimal_places=2)
    discount_rate = models.DecimalField(max_digits=5, decimal_places=4, default=0,
                                        help_text="Incremental borrowing rate (e.g. 0.0500 = 5%)")
    right_of_use_asset_value = models.DecimalField(max_digits=19, decimal_places=2, default=0)
    lease_liability = models.DecimalField(max_digits=19, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="USD")
    renewal_option = models.BooleanField(default=False)
    purchase_option = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "asset_leases"

    def __str__(self) -> str:
        return "{} — {} ({})".format(
            self.lease_number or str(self.pk)[:8], self.description, self.lease_type
        )
