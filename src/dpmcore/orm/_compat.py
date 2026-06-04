"""SQLAlchemy 1.4 / 2.0 compatibility shim.

dpmcore targets both SQLAlchemy 2.0.x (the canonical, typed-declarative
target) and the 1.4.50 package shipped by Ubuntu 24.04 (Noble) via apt.
The ORM source is written in 2.0 style; on 1.4 this module aliases the
2.0-only symbols so the same source runs unchanged:

- ``mapped_column`` -> classic ``Column``. dpmcore only uses the
  ``(name, Type, **kw)`` forms (no 2.0 dataclass kwargs such as
  ``init=``/``repr=``/``kw_only=``), so the signatures are compatible.
- ``Mapped`` is re-exported. It exists in 1.4 and is inert on classic
  columns (verified in issue #104, GATE 0), so the type annotations stay.

``base.py`` builds the declarative base per version. ``SA2`` is exported
for the rare spots that must branch (e.g. version-gated test skips).
"""

from typing import TYPE_CHECKING

from sqlalchemy import __version__ as _SA_VERSION

SA2 = _SA_VERSION.startswith("2.")

# TYPE_CHECKING is True under mypy, so the type checker always sees the
# real 2.0 ``Mapped``/``mapped_column`` (the canonical, typed target);
# at runtime the branch is chosen by the installed version.
if SA2 or TYPE_CHECKING:  # pragma: no cover
    from sqlalchemy.orm import Mapped, mapped_column
else:  # pragma: no cover
    from sqlalchemy import Column as mapped_column
    from sqlalchemy.orm import Mapped

__all__ = ["Mapped", "mapped_column", "SA2"]
