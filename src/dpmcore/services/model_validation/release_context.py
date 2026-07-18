"""Release semantics shared by the modelling services.

The original SQL stored procedures resolve ``@CurrentRelease`` from
``Release.IsCurrent = 1`` and use the literal release id ``9999`` as an
"open / draft" sentinel throughout their ``WHERE`` clauses. dpmcore's
ORM expresses row currency as ``end_release_id IS NULL``, but migrated
EBA databases may still contain a release row with id 9999. This module
centralises those semantics so no rule code ever compares against a
literal sentinel.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

#: Reserved id of the sandbox/draft ("playground") release in EBA
#: DPM databases. Only meaningful when such a release row exists.
DRAFT_RELEASE_ID = 9999


@dataclass(frozen=True)
class ReleaseContext:
    """Resolved release under validation plus sentinel predicates.

    Attributes:
        current_release_id: The release the model is validated against.
        draft_release_id: Id of the draft/playground release when one
            exists in the database (``9999``), else None.
    """

    current_release_id: int
    draft_release_id: Optional[int] = None

    def is_draft(self, release_id: Optional[int]) -> bool:
        """True when ``release_id`` is the draft/playground release."""
        return (
            self.draft_release_id is not None
            and release_id == self.draft_release_id
        )

    def is_current(self, release_id: Optional[int]) -> bool:
        """True when ``release_id`` is the release under validation.

        Mirrors the SQL pattern ``X = @CurrentRelease OR X = 9999``:
        the draft sentinel always counts as "current".
        """
        return release_id == self.current_release_id or self.is_draft(
            release_id
        )

    def is_open(self, end_release_id: Optional[int]) -> bool:
        """True when a version row is still open (not expired).

        Mirrors the SQL pattern
        ``EndReleaseID IS NULL OR EndReleaseID = 9999``.
        """
        return end_release_id is None or self.is_draft(end_release_id)

    def starts_in_current(self, start_release_id: Optional[int]) -> bool:
        """True when a version row starts in the release under test.

        Mirrors the SQL pattern
        ``StartReleaseID = @CurrentRelease OR StartReleaseID = 9999``.
        """
        return self.is_current(start_release_id)

    def ends_in_current(self, end_release_id: Optional[int]) -> bool:
        """True when a version row was closed by the release under test.

        Mirrors the SQL pattern ``EndReleaseID = @CurrentRelease``:
        such a row is the *predecessor* superseded in this release.
        """
        return (
            end_release_id is not None and self.is_current(end_release_id)
        )
