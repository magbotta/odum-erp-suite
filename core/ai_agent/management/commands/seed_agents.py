"""Seed the example AI agents."""
from django.core.management.base import BaseCommand

COMPANY_ID = "00000000-0000-0000-0000-000000000001"
ADMIN_EMAIL = "admin@odum-erp.io"


class Command(BaseCommand):
    help = "Seed example AI Agent definitions: Collections Dunning + Lead Qualification + Expense Policy Review"

    def handle(self, *args, **options):
        from django.contrib.auth import get_user_model
        from core.ai_agent.models import AgentDefinition
        from core.ai_agent.agents.collections import get_seed_data as collections_data
        from core.ai_agent.agents.lead_qualification import get_seed_data as lead_data
        from core.ai_agent.agents.expense_policy_review import get_seed_data as expense_data

        import uuid
        company_id = uuid.UUID(COMPANY_ID)

        User = get_user_model()
        try:
            admin = User.objects.get(email=ADMIN_EMAIL)
        except User.DoesNotExist:
            admin = User.objects.filter(is_superuser=True).first()
            if not admin:
                self.stdout.write(self.style.WARNING("No admin user found; skipping agent seed"))
                return

        configured_by_id = admin.id

        for get_data in [collections_data, lead_data, expense_data]:
            data = get_data(configured_by_id=configured_by_id, company_id=company_id)
            slug = data.pop("slug")
            agent, created = AgentDefinition.objects.get_or_create(
                slug=slug,
                defaults=data,
            )
            if created:
                self.stdout.write("  Created agent: {0}".format(agent.name))
            else:
                self.stdout.write("  Already exists: {0}".format(agent.name))

        self.stdout.write(self.style.SUCCESS("Agent seed complete."))
