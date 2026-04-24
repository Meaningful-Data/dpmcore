"""ORM layer for dpmcore — models, engine, and session management."""

import dpmcore.orm.auxiliary  # noqa: F401
import dpmcore.orm.glossary  # noqa: F401

# Import all model modules so cross-module relationships resolve
# correctly before any query is executed.
import dpmcore.orm.infrastructure  # noqa: F401
import dpmcore.orm.operations  # noqa: F401
import dpmcore.orm.packaging  # noqa: F401
import dpmcore.orm.rendering  # noqa: F401
import dpmcore.orm.variables  # noqa: F401
from dpmcore.orm.base import (
    Base,
    SessionFactory,
    create_engine,
    create_session,
)

__all__ = [
    "Base",
    "SessionFactory",
    "create_engine",
    "create_session",
]
