"""CRM lead scoring hook (§6.3)."""
from __future__ import annotations


def score_lead(lead) -> None:
    """
    Simple rule-based lead scoring.
    Each condition adds to the score; the model field is then updated.
    """
    score = 0

    if lead.email:
        score += 10
    if lead.phone:
        score += 5
    if lead.company:
        score += 10
    if lead.lead_source == "referral":
        score += 20
    elif lead.lead_source == "website":
        score += 10

    lead.score = score
