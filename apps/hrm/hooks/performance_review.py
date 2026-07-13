"""Hook: stamp timestamps on performance review status transitions (§6.4)."""
from django.utils import timezone


def on_submit(review) -> None:
    if not review.submitted_at:
        review.submitted_at = timezone.now()


def on_acknowledge(review) -> None:
    if not review.acknowledged_at:
        review.acknowledged_at = timezone.now()
