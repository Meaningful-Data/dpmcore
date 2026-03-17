"""Bridge between Django settings and dpmcore services.

Provides a convenience helper that builds a
:class:`~dpmcore.connection._ServiceAccessor` from Django's
``DATABASES`` configuration so Django views can call dpmcore
services without manual engine setup.

Usage::

    from dpmcore.django.bridge import get_dpm_services

    services = get_dpm_services()
    result = services.syntax.validate("v1 = v2")
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from dpmcore.connection import _ServiceAccessor


def _build_url_from_django(alias: str = "dpm") -> str:
    """Derive a SQLAlchemy URL from Django DATABASES config."""
    from django.conf import settings

    db_conf = settings.DATABASES[alias]
    engine = db_conf["ENGINE"]
    name = db_conf.get("NAME", "")

    if "sqlite" in engine:
        return f"sqlite:///{name}"

    user = db_conf.get("USER", "")
    password = db_conf.get("PASSWORD", "")
    host = db_conf.get("HOST", "localhost")
    port = db_conf.get("PORT", "")

    if "postgresql" in engine:
        scheme = "postgresql"
    elif "mssql" in engine or "sql_server" in engine:
        scheme = "mssql+pyodbc"
    else:
        scheme = "sqlite"

    authority = f"{user}:{password}@{host}"
    if port:
        authority += f":{port}"

    return f"{scheme}://{authority}/{name}"


def get_dpm_services(
    database_url: Optional[str] = None,
    alias: str = "dpm",
) -> "_ServiceAccessor":
    """Return a :class:`~dpmcore.connection._ServiceAccessor`.

    Args:
        database_url: Explicit SQLAlchemy URL. When ``None``,
            the URL is derived from Django's ``DATABASES``
            setting using *alias*.
        alias: Django database alias (default ``"dpm"``).

    Returns:
        A service accessor with lazy-loaded dpmcore services.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from dpmcore.connection import _ServiceAccessor

    url = database_url or _build_url_from_django(alias)
    engine = create_engine(url, pool_pre_ping=True)
    session = Session(bind=engine)
    return _ServiceAccessor(session, engine)
