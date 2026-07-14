"""
PermissionGuard — validates every agent action before execution.

Three layers of enforcement:
  1. Allow-list check: entity+action must appear in AgentDefinition.allowed_actions
  2. RBAC check: the agent's service_account must have the permission on the entity
  3. High-risk floor: certain actions cannot be below AUTO_WITH_REVIEW
     unless explicitly elevated in autonomy_config

See ADR-0001 §Autonomy Tier Defaults.
"""
from __future__ import annotations

import logging
from typing import Optional

from .models import AgentDefinition, AutonomyTier

logger = logging.getLogger(__name__)

# Actions in this set must be at least auto_execute_with_review.
# They can be elevated to suggest_only but NEVER to fully_autonomous
# without explicit operator configuration.
HIGH_RISK_ACTIONS = frozenset({
    # Financial postings
    "post_to_gl", "write_off", "journal_entry", "post_payment", "reverse_entry",
    # External communications
    "send_email", "send_sms", "send_webhook", "send_notification",
    # Workflow state changes on financial docs
    "submit", "cancel", "approve", "reject",
    # Regulated / compliance
    "aml_flag", "sar_file", "kyc_reject", "freeze_account",
})

# The minimum tier we allow for high-risk actions (can be configured higher).
HIGH_RISK_MIN_TIER = AutonomyTier.AUTO_WITH_REVIEW

# Tier ordering (lower index = more human oversight)
_TIER_ORDER = [
    AutonomyTier.SUGGEST_ONLY,
    AutonomyTier.AUTO_WITH_REVIEW,
    AutonomyTier.AUTO_REVERSIBLE,
    AutonomyTier.FULLY_AUTONOMOUS,
]


def _tier_index(tier: str) -> int:
    try:
        return _TIER_ORDER.index(tier)
    except ValueError:
        return 0  # default to most restrictive


class PolicyViolation(Exception):
    """Raised when an agent attempts an action that violates policy."""


class PermissionGuard:
    """Stateless validator. Instantiate once per executor run."""

    def __init__(self, agent: AgentDefinition):
        self.agent = agent
        self._service_user = None

    def _get_service_user(self):
        if self._service_user is None and self.agent.service_account_id:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            try:
                self._service_user = User.objects.get(id=self.agent.service_account_id)
            except User.DoesNotExist:
                pass
        return self._service_user

    def validate_action(
        self,
        entity: str,
        action: str,
        company_id=None,
    ) -> str:
        """
        Validate entity+action against all three layers.
        Returns the resolved AutonomyTier string.
        Raises PolicyViolation on any failure.
        """
        # Layer 1: allow-list
        if not self.agent.is_action_allowed(entity, action):
            raise PolicyViolation(
                "Agent '{0}' is not allowed to perform '{1}' on '{2}'".format(
                    self.agent.slug, action, entity
                )
            )

        # Layer 2: service account RBAC
        service_user = self._get_service_user()
        if service_user is not None:
            from core.auth.rbac import has_entity_permission
            rbac_action = self._map_to_rbac_action(action)
            if not has_entity_permission(service_user, entity, rbac_action, company_id):
                raise PolicyViolation(
                    "Agent service account lacks RBAC permission '{0}' on '{1}'".format(
                        rbac_action, entity
                    )
                )

        # Layer 3: resolve autonomy tier and enforce high-risk floor
        tier = self.agent.get_autonomy_tier(entity, action)
        tier = self._apply_high_risk_floor(action, tier)

        return tier

    def validate_mcp_tool(self, server_url: str, tool_name: str) -> None:
        """Raises PolicyViolation if the MCP tool is not in the agent's allow-list."""
        allowed = {
            (t["server_url"].rstrip("/"), t["tool_name"])
            for t in (self.agent.allowed_mcp_tools or [])
        }
        if (server_url.rstrip("/"), tool_name) not in allowed:
            raise PolicyViolation(
                "Agent '{0}' is not allowed to call MCP tool '{1}::{2}'".format(
                    self.agent.slug, server_url, tool_name
                )
            )

    @staticmethod
    def _map_to_rbac_action(action: str) -> str:
        """Map agent action names to EntityPermission RBAC actions."""
        if action == "read":
            return "read"
        if action in ("submit", "approve"):
            return "submit"
        if action in ("cancel", "reject", "write_off"):
            return "cancel"
        if action == "delete":
            return "delete"
        return "write"

    @staticmethod
    def _apply_high_risk_floor(action: str, tier: str) -> str:
        """
        High-risk actions cannot be lower than HIGH_RISK_MIN_TIER.
        (suggest_only is always acceptable — it's MORE restrictive; only
        auto_execute_reversible and fully_autonomous are forbidden for these actions.)
        """
        if action not in HIGH_RISK_ACTIONS:
            return tier

        forbidden = {AutonomyTier.AUTO_REVERSIBLE, AutonomyTier.FULLY_AUTONOMOUS}
        if tier in forbidden:
            logger.warning(
                "PermissionGuard: high-risk action '%s' configured with tier '%s'; "
                "upgrading to suggest_only",
                action, tier,
            )
            return AutonomyTier.SUGGEST_ONLY

        return tier
