"""Django integration for dpmcore (Mode 3).

Add ``"dpmcore.django"`` to ``INSTALLED_APPS`` to expose
read-only Django ORM models backed by the DPM database.

Requires Django 5.2+.
"""

try:
    import django  # noqa: F401
except ImportError as exc:
    raise ImportError(
        "Django is required for dpmcore.django. "
        "Install it with: pip install dpmcore[django]"
    ) from exc
