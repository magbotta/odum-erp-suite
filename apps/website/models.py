"""Website / CMS models (§6.10): pages, blog, web forms, e-commerce hooks."""
from __future__ import annotations

from django.conf import settings
from django.db import models

from core.metadata_engine.base_entity import BaseEntity


class WebPage(BaseEntity):
    """A CMS page with a URL slug, rich content, and SEO metadata (§6.10)."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, db_index=True)
    content = models.JSONField(
        default=dict,
        help_text="Block-based content (compatible with a page-builder renderer)",
    )
    meta_title = models.CharField(max_length=255, blank=True)
    meta_description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    published_at = models.DateTimeField(null=True, blank=True)
    template = models.CharField(max_length=100, blank=True, default="default")
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children"
    )

    class Meta(BaseEntity.Meta):
        db_table = "website_pages"

    def __str__(self) -> str:
        return f"{self.title} (/{self.slug})"


class BlogCategory(BaseEntity):
    """Hierarchical blog / news category (§6.10)."""

    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children"
    )

    class Meta(BaseEntity.Meta):
        db_table = "website_blog_categories"
        verbose_name = "Blog Category"
        verbose_name_plural = "Blog Categories"

    def __str__(self) -> str:
        return self.name


class BlogPost(BaseEntity):
    """A blog / news article (§6.10)."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, db_index=True)
    content = models.TextField()
    excerpt = models.TextField(blank=True)
    category = models.ForeignKey(
        BlogCategory, null=True, blank=True, on_delete=models.SET_NULL, related_name="posts"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="blog_posts",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    featured_image = models.CharField(max_length=500, blank=True)
    meta_title = models.CharField(max_length=255, blank=True)
    meta_description = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "website_blog_posts"
        ordering = ["-published_at"]

    def __str__(self) -> str:
        return self.title


class WebForm(BaseEntity):
    """
    A configurable web form whose submissions are converted to a target entity
    (typically a CRM Lead) via the metadata engine (§6.10, §9.3).
    """

    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    target_entity = models.CharField(
        max_length=100, blank=True, help_text="e.g. crm.Lead — entity to create on submit",
    )
    success_message = models.TextField(blank=True, default="Thank you for your submission.")
    redirect_url = models.CharField(max_length=500, blank=True)
    is_active = models.BooleanField(default=True)
    send_confirmation_email = models.BooleanField(default=False)
    email_field = models.CharField(
        max_length=50, blank=True, help_text="Field name whose value is the submitter's email",
    )

    class Meta(BaseEntity.Meta):
        db_table = "website_web_forms"

    def __str__(self) -> str:
        return self.title


class WebFormField(BaseEntity):
    """One field within a WebForm (§6.10)."""

    class FieldType(models.TextChoices):
        TEXT = "text", "Text"
        EMAIL = "email", "Email"
        PHONE = "phone", "Phone"
        TEXTAREA = "textarea", "Text Area"
        SELECT = "select", "Select"
        CHECKBOX = "checkbox", "Checkbox"
        NUMBER = "number", "Number"
        DATE = "date", "Date"

    form = models.ForeignKey(WebForm, on_delete=models.CASCADE, related_name="fields")
    field_name = models.CharField(max_length=50, help_text="Maps to entity field name")
    label = models.CharField(max_length=100)
    field_type = models.CharField(max_length=20, choices=FieldType.choices, default=FieldType.TEXT)
    is_required = models.BooleanField(default=False)
    options = models.JSONField(null=True, blank=True, help_text="For select fields: list of options")
    placeholder = models.CharField(max_length=255, blank=True)
    sequence = models.PositiveSmallIntegerField(default=0)

    class Meta(BaseEntity.Meta):
        db_table = "website_web_form_fields"
        ordering = ["form", "sequence"]

    def __str__(self) -> str:
        return f"{self.form.title} / {self.label}"


class WebFormSubmission(BaseEntity):
    """A recorded form submission; also triggers entity creation via the metadata engine."""

    form = models.ForeignKey(WebForm, on_delete=models.PROTECT, related_name="submissions")
    data = models.JSONField(help_text="Submitted field values as {field_name: value}")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_entity_id = models.UUIDField(
        null=True, blank=True, help_text="ID of the entity created from this submission",
    )

    class Meta(BaseEntity.Meta):
        db_table = "website_form_submissions"

    def __str__(self) -> str:
        return f"{self.form} submission [{self.created_at}]"
