"""SDMX URL parameter parser per REST API spec §5.2."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import List, Optional


class ReleaseKeyword(enum.Enum):
    """Special release tokens from the SDMX URL scheme."""

    LATEST = "~"          # latest (any status)
    LATEST_STABLE = "+"   # latest with status='Final'
    ALL = "*"             # all releases


@dataclass(frozen=True)
class StructureParams:
    """Parsed SDMX-style path parameters."""

    owners: List[str]
    ids: List[str]
    release: Optional[ReleaseKeyword]
    release_code: Optional[str]

    # -- owner helpers ------------------------------------------

    @property
    def is_owner_wildcard(self) -> bool:
        """True when owner is the ``*`` wildcard."""
        return self.owners == ["*"]

    # -- id helpers ---------------------------------------------

    @property
    def is_id_wildcard(self) -> bool:
        """True when id is the ``*`` wildcard."""
        return self.ids == ["*"]

    @property
    def is_single_id(self) -> bool:
        """True when exactly one non-wildcard id."""
        return len(self.ids) == 1 and self.ids[0] != "*"

    # -- release helpers ----------------------------------------

    @property
    def wants_all_releases(self) -> bool:
        """True when release keyword is ``*`` (all)."""
        return self.release is ReleaseKeyword.ALL

    @property
    def wants_latest(self) -> bool:
        """True when release keyword is ``~`` (latest)."""
        return self.release is ReleaseKeyword.LATEST

    @property
    def wants_latest_stable(self) -> bool:
        """True when release keyword is ``+`` (latest stable)."""
        return self.release is ReleaseKeyword.LATEST_STABLE


def parse_structure_params(
    owner: str = "*",
    id: str = "*",
    release: str = "~",
) -> StructureParams:
    """Parse raw path segments into a :class:`StructureParams`.

    Supports comma-separated values for *owner* and *id* and the
    special release keywords ``~``, ``+``, ``*``.
    """
    owners = [o.strip() for o in owner.split(",") if o.strip()]
    ids = [i.strip() for i in id.split(",") if i.strip()]

    release_kw: Optional[ReleaseKeyword] = None
    release_code: Optional[str] = None

    try:
        release_kw = ReleaseKeyword(release)
    except ValueError:
        release_code = release

    return StructureParams(
        owners=owners or ["*"],
        ids=ids or ["*"],
        release=release_kw,
        release_code=release_code,
    )
