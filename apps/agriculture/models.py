"""
Agriculture Management models (§7).
Farm/Plot registry with geofence boundaries, crop cycles, inputs, yield, livestock.
Depends on: Warehouse (input/output stock), Purchasing (input procurement), Accounting.
"""
from __future__ import annotations

from django.db import models

from core.metadata_engine.base_entity import BaseEntity


class Farm(BaseEntity):
    """A farm or agricultural holding with optional geospatial boundary (§5)."""

    name = models.CharField(max_length=255)
    farm_code = models.CharField(max_length=50, blank=True, db_index=True)
    owner_name = models.CharField(max_length=255, blank=True)
    address = models.TextField(blank=True)
    total_area_ha = models.DecimalField(max_digits=10, decimal_places=4, default=0,
                                        help_text="Total area in hectares")
    # Geofence stored as GeoJSON (§5 — PostGIS geofence field)
    boundary_geojson = models.JSONField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    # Cross-app: CRM Account representing this farm
    crm_account_id = models.UUIDField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "agri_farms"

    def __str__(self) -> str:
        return self.name


class Plot(BaseEntity):
    """A named parcel / block within a Farm with its own boundary (§5)."""

    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name="plots")
    name = models.CharField(max_length=150)
    area_ha = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    soil_type = models.CharField(max_length=100, blank=True)
    irrigation_type = models.CharField(max_length=100, blank=True)
    boundary_geojson = models.JSONField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "agri_plots"

    def __str__(self) -> str:
        return f"{self.farm} / {self.name}"


class Crop(BaseEntity):
    """A crop species / variety catalogue entry."""

    name = models.CharField(max_length=150)
    variety = models.CharField(max_length=150, blank=True)
    typical_cycle_days = models.PositiveSmallIntegerField(default=90)
    description = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "agri_crops"

    def __str__(self) -> str:
        return f"{self.name} ({self.variety})" if self.variety else self.name


class CropCycle(BaseEntity):
    """
    A single growing season for a Crop on a Plot.
    Tracks planting → growth → harvest lifecycle.
    """

    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        PLANTED = "planted", "Planted"
        GROWING = "growing", "Growing"
        HARVESTED = "harvested", "Harvested"
        FAILED = "failed", "Failed"

    plot = models.ForeignKey(Plot, on_delete=models.PROTECT, related_name="crop_cycles")
    crop = models.ForeignKey(Crop, on_delete=models.PROTECT, related_name="crop_cycles")
    season_name = models.CharField(max_length=100, blank=True)
    planting_date = models.DateField(null=True, blank=True)
    expected_harvest_date = models.DateField(null=True, blank=True)
    actual_harvest_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLANNED)
    expected_yield_kg = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    actual_yield_kg = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "agri_crop_cycles"

    def __str__(self) -> str:
        return f"{self.plot} — {self.crop} [{self.season_name or self.planting_date}]"


class InputApplication(BaseEntity):
    """
    A record of an agrochemical or seed application to a Plot/CropCycle.
    Cross-app: Warehouse Item = the input (fertilizer, pesticide, seed).
    """

    class InputType(models.TextChoices):
        SEED = "seed", "Seed"
        FERTILIZER = "fertilizer", "Fertilizer"
        PESTICIDE = "pesticide", "Pesticide"
        HERBICIDE = "herbicide", "Herbicide"
        IRRIGATION = "irrigation", "Irrigation"
        OTHER = "other", "Other"

    crop_cycle = models.ForeignKey(
        CropCycle, on_delete=models.CASCADE, related_name="input_applications"
    )
    input_type = models.CharField(max_length=20, choices=InputType.choices)
    input_item_id = models.UUIDField(help_text="Warehouse Item UUID for this input")
    input_name = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=12, decimal_places=4)
    uom = models.CharField(max_length=30, default="kg")
    application_date = models.DateField()
    applied_by_employee_id = models.UUIDField(null=True, blank=True)
    cost_per_unit = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    total_cost = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    notes = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "agri_input_applications"

    def __str__(self) -> str:
        return f"{self.crop_cycle} — {self.input_type}: {self.input_name}"


class HarvestRecord(BaseEntity):
    """Records the yield from a CropCycle — feeds into Warehouse stock (§7)."""

    crop_cycle = models.ForeignKey(
        CropCycle, on_delete=models.PROTECT, related_name="harvest_records"
    )
    harvest_date = models.DateField()
    quantity_kg = models.DecimalField(max_digits=12, decimal_places=2)
    quality_grade = models.CharField(max_length=50, blank=True)
    storage_warehouse_id = models.UUIDField(null=True, blank=True)
    unit_price = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    total_value = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    # Cross-app: StockEntry created when harvest is receipted into Warehouse
    stock_entry_id = models.UUIDField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "agri_harvest_records"

    def __str__(self) -> str:
        return f"{self.crop_cycle} — {self.harvest_date}: {self.quantity_kg} kg"


class LivestockRecord(BaseEntity):
    """A herd or individual animal registry entry (§7)."""

    class AnimalType(models.TextChoices):
        CATTLE = "cattle", "Cattle"
        POULTRY = "poultry", "Poultry"
        SWINE = "swine", "Swine"
        SHEEP = "sheep", "Sheep / Goats"
        FISH = "fish", "Aquaculture"
        OTHER = "other", "Other"

    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name="livestock")
    animal_type = models.CharField(max_length=20, choices=AnimalType.choices)
    breed = models.CharField(max_length=100, blank=True)
    tag_number = models.CharField(max_length=50, blank=True, db_index=True)
    quantity = models.PositiveIntegerField(default=1,
                                           help_text="For poultry/fish: flock/batch count")
    date_acquired = models.DateField(null=True, blank=True)
    acquisition_cost = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    current_weight_kg = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "agri_livestock_records"

    def __str__(self) -> str:
        return f"{self.farm} — {self.animal_type} ({self.tag_number or 'batch'})"
