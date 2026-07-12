"""
Management command: generate Django model source code from entity definitions.

Usage:
    python manage.py generate_entity_models [--app crm] [--dry-run]

Writes apps/{app}/models/generated.py for each app that has registered entity
definitions. After running, create migrations normally with makemigrations.
"""
from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand

from core.metadata_engine.model_factory import generate_app_models_file
from core.metadata_engine.registry import registry


class Command(BaseCommand):
    help = "Generate Django model source code from registered entity definitions."

    def add_arguments(self, parser):
        parser.add_argument("--app", type=str, default=None, help="Limit to a single app")
        parser.add_argument("--dry-run", action="store_true", help="Print output without writing")

    def handle(self, *args, **options):
        filter_app = options.get("app")
        dry_run = options.get("dry_run")

        apps: dict[str, list] = {}
        for defn in registry.all():
            if filter_app and defn.app != filter_app:
                continue
            apps.setdefault(defn.app, []).append(defn)

        if not apps:
            self.stdout.write(self.style.WARNING("No entity definitions found."))
            return

        for app_name, definitions in sorted(apps.items()):
            source = generate_app_models_file(app_name, definitions)
            if dry_run:
                self.stdout.write(self.style.HTTP_INFO(f"\n# === {app_name}/models/generated.py ===\n"))
                self.stdout.write(source)
            else:
                out_dir = Path("apps") / app_name / "models"
                out_dir.mkdir(parents=True, exist_ok=True)
                init = out_dir / "__init__.py"
                if not init.exists():
                    init.write_text(
                        "from .generated import *  # noqa: F401, F403\n"
                    )
                out_file = out_dir / "generated.py"
                out_file.write_text(source, encoding="utf-8")
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Wrote {len(definitions)} model(s) to {out_file}"
                    )
                )
