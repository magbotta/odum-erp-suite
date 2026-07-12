"""Asset Management models (§6.2): lifecycle, depreciation, maintenance, movement."""
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
    # Cross-app GL accounts
    asset_account_id = models.UUIDField(null=True, blank=True)
    depreciation_expense_account_id = models.UUIDField(null=True, blank=True)
    accumulated_depreciation_account_id = models.UUIDField(null=True, blank=True)

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
    category = models.ForeignKey(
        AssetCategory, on_delete=models.PROTECT, related_name="assets"
    )
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
    purchase_order_id = models.UUIDField(null=True, blank=True)
    # Disposal fields
    disposal_date = models.DateField(null=True, blank=True)
    disposal_amount = models.DecimalField(max_digits=19, decimal_places=4, null=True, blank=True)
    disposal_reason = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "assets"

    def __str__(self) -> str:
        return f"{self.asset_code} — {self.asset_name}"


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
        return f"{self.asset} — {self.schedule_date} — {self.depreciation_amount}"


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
        return f"{self.asset} — {self.maintenance_type} [{self.scheduled_date}]"


class AssetMovement(BaseEntity):
    """Records a transfer of an asset between locations or custodians (§6.2)."""

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="movements")
    movement_date = models.DateField()
    from_location = models.CharField(max_length=255)
    to_location = models.CharField(max_length=255)
    from_custodian_id = models.UUIDField(null=True, blank=True)
    to_custodian_id = models.UUIDField(null=True, blank=True)
    purpose = models.CharField(max_length=255, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="asset_movements_approved",
    )

    class Meta(BaseEntity.Meta):
        db_table = "asset_movements"

    def __str__(self) -> str:
        return f"{self.asset} → {self.to_location} [{self.movement_date}]"
