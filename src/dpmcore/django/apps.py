"""Django app configuration for dpmcore."""

from django.apps import AppConfig


class DpmcoreConfig(AppConfig):
    """Configuration for the dpmcore Django app."""

    name = "dpmcore.django"
    label = "dpmcore_django"
    default_auto_field = "django.db.models.AutoField"
    verbose_name = "DPM Core"
