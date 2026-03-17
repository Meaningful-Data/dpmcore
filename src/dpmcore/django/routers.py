"""Database router for dpmcore Django models.

Routes all ``dpmcore_django`` models to the ``"dpm"`` database
alias. Schema is managed by SQLAlchemy, so migrations are
always blocked.

Usage in ``settings.py``::

    DATABASE_ROUTERS = ["dpmcore.django.routers.DpmRouter"]
"""

from typing import Any, Optional, Type

from django.db import models


class DpmRouter:
    """Route dpmcore models to the ``dpm`` database alias."""

    app_label = "dpmcore_django"
    db_alias = "dpm"

    def db_for_read(
        self,
        model: Type[models.Model],
        **hints: Any,
    ) -> Optional[str]:
        """Direct reads to the DPM database."""
        if model._meta.app_label == self.app_label:
            return self.db_alias
        return None

    def db_for_write(
        self,
        model: Type[models.Model],
        **hints: Any,
    ) -> Optional[str]:
        """Direct writes to the DPM database."""
        if model._meta.app_label == self.app_label:
            return self.db_alias
        return None

    def allow_relation(
        self,
        obj1: models.Model,
        obj2: models.Model,
        **hints: Any,
    ) -> Optional[bool]:
        """Allow relations between dpmcore models."""
        labels = {
            obj1._meta.app_label,
            obj2._meta.app_label,
        }
        if self.app_label in labels:
            return labels == {self.app_label}
        return None

    def allow_migrate(
        self,
        db: str,
        app_label: str,
        model_name: Optional[str] = None,
        **hints: Any,
    ) -> Optional[bool]:
        """Never migrate dpmcore models (managed=False)."""
        if app_label == self.app_label:
            return False
        return None
