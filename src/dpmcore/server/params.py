"""SDMX URL parameter parser per REST API spec §5.2."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import List, Optional


class VersionKeyword(enum.Enum):
    """Special version tokens from the SDMX URL scheme."""

    LATEST = "~"          # latest (any status)
    LATEST_STABLE = "+"   # latest with status='Final'
    ALL = "*"             # all versions


@dataclass(frozen=True)
class StructureParams:
    """Parsed SDMX-style path parameters."""

    owners: List[str]
    ids: List[str]
    version: Optional[VersionKeyword]
    version_code: Optional[str]

    # -- owner helpers --------------------------------------------------

    @property
    def is_owner_wildcard(self) -> bool:
        """True when owner is the ``*`` wildcard."""
        return self.owners == ["*"]

    # -- id helpers -----------------------------------------------------

    @property
    def is_id_wildcard(self) -> bool:
        """True when id is the ``*`` wildcard."""
        return self.ids == ["*"]

    @property
    def is_single_id(self) -> bool:
        """True when exactly one non-wildcard id was provided."""
        return len(self.ids) == 1 and self.ids[0] != "*"

    # -- version helpers ------------------------------------------------

    @property
    def wants_all_versions(self) -> bool:
        """True when version keyword is ``*`` (all)."""
        return self.version is VersionKeyword.ALL

    @property
    def wants_latest(self) -> bool:
        """True when version keyword is ``~`` (latest any)."""
        return self.version is VersionKeyword.LATEST

    @property
    def wants_latest_stable(self) -> bool:
        """True when version keyword is ``+`` (latest stable)."""
        return self.version is VersionKeyword.LATEST_STABLE


def parse_structure_params(
    owner: str = "*",
    id: str = "*",
    version: str = "~",
) -> StructureParams:
    """Parse raw path segments into a :class:`StructureParams`.

    Supports comma-separated values for *owner* and *id* and the special
    version keywords ``~``, ``+``, ``*``.
    """
    owners = [o.strip() for o in owner.split(",") if o.strip()]
    ids = [i.strip() for i in id.split(",") if i.strip()]

    version_kw: Optional[VersionKeyword] = None
    version_code: Optional[str] = None

    try:
        version_kw = VersionKeyword(version)
    except ValueError:
        version_code = version

    return StructureParams(
        owners=owners or ["*"],
        ids=ids or ["*"],
        version=version_kw,
        version_code=version_code,
    )
