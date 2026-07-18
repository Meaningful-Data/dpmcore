"""Model-validation service (port of ``check_modelling_rules_tidy``).

Runs the full DPM modelling-rule set against an in-memory snapshot of
the model and returns the violations as data — nothing is written to
the database (the SQL procedure's ``ModelViolations`` result table is
replaced by the returned
:class:`~dpmcore.services.model_validation.types.ModelValidationResult`).
"""

from __future__ import annotations

import time
from typing import List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from dpmcore.errors import Invalid, NotFound
from dpmcore.orm.infrastructure import Release
from dpmcore.services.model_validation import rules as _rules  # noqa: F401
from dpmcore.services.model_validation.registry import (
    RuleContext,
    all_rule_infos,
    evaluate,
    rule_sort_key,
)
from dpmcore.services.model_validation.release_context import (
    DRAFT_RELEASE_ID,
    ReleaseContext,
)
from dpmcore.services.model_validation.snapshot import ModelSnapshot
from dpmcore.services.model_validation.types import (
    SEVERITY_ERROR,
    ModelValidationResult,
    RuleInfo,
    Violation,
)


def _violation_sort_key(
    violation: Violation,
) -> Tuple[Tuple[int, int, str], str, str]:
    """Deterministic ordering: rule id, then primary object, message."""
    primary = ""
    if violation.objects:
        first = violation.objects[0]
        primary = f"{first.kind}:{first.id}:{first.code}"
    return (
        rule_sort_key(violation.rule_id),
        primary,
        violation.message,
    )


class ModelValidationService:
    """DPM model integrity validation.

    Evaluates the modelling rules ported from the EBA
    ``check_modelling_rules_tidy`` stored procedure. Read-only.
    """

    def __init__(self, session: Session) -> None:
        """Bind the service to a SQLAlchemy session.

        Args:
            session: Session on the DPM database. Only read.
        """
        self._session = session

    def validate(
        self,
        release_id: Optional[int] = None,
        release_code: Optional[str] = None,
        rule_ids: Optional[Sequence[str]] = None,
        include_warnings: bool = True,
        snapshot: Optional[ModelSnapshot] = None,
    ) -> ModelValidationResult:
        """Run the modelling rules and collect violations.

        Args:
            release_id: Release to validate against. Defaults to the
                release flagged ``IsCurrent``. Passing the draft
                release id (9999) reproduces the "playground"
                behaviour with the full rule set.
            release_code: Alternative lookup by release code.
            rule_ids: Restrict the run to these rule ids.
            include_warnings: When False, warning-severity rules are
                skipped.
            snapshot: Pre-loaded model snapshot to validate. Used by
                the variable-generation service to avoid loading the
                model twice; normal callers omit it.

        Returns:
            The validation outcome. A model full of violations is a
            *successful* run — no exception is raised for findings.

        Raises:
            Invalid: If both ``release_id`` and ``release_code`` are
                given.
            NotFound: If the requested release does not exist, or no
                current release is flagged.
        """
        start = time.perf_counter()
        release = self._resolve_release(release_id, release_code)
        if snapshot is None:
            snapshot = ModelSnapshot(self._session)
        ctx = RuleContext(
            snapshot=snapshot,
            release=self._release_context(release.release_id),
        )
        violations, rules_run = evaluate(
            ctx, rule_ids=rule_ids, include_warnings=include_warnings
        )
        violations.sort(key=_violation_sort_key)
        errors = sum(
            1 for v in violations if v.severity == SEVERITY_ERROR
        )
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return ModelValidationResult(
            is_valid=errors == 0,
            release_id=release.release_id,
            release_code=release.code,
            violations=tuple(violations),
            error_count=errors,
            warning_count=len(violations) - errors,
            rules_run=rules_run,
            elapsed_ms=elapsed_ms,
        )

    def list_rules(self) -> List[RuleInfo]:
        """Return the catalogue of registered rules, in rule order."""
        return all_rule_infos()

    # --------------------------------------------------------------
    # Internals
    # --------------------------------------------------------------

    def _resolve_release(
        self,
        release_id: Optional[int],
        release_code: Optional[str],
    ) -> Release:
        """Resolve the release under validation.

        Mirrors the SQL: default is ``Release.IsCurrent = 1``.
        """
        if release_id is not None and release_code is not None:
            raise Invalid(
                "Pass either release_id or release_code, not both"
            )
        if release_id is not None:
            found = self._session.get(Release, release_id)
            if found is None:
                raise NotFound(
                    f"Release with id {release_id} does not exist"
                )
            return found
        if release_code is not None:
            stmt = select(Release).where(Release.code == release_code)
            by_code = self._session.execute(stmt).scalars().first()
            if by_code is None:
                raise NotFound(
                    f"Release '{release_code}' does not exist"
                )
            return by_code
        stmt = select(Release).where(Release.is_current.is_(True))
        current = self._session.execute(stmt).scalars().first()
        if current is None:
            raise NotFound("No release is flagged as current")
        return current

    def _release_context(self, current_release_id: int) -> ReleaseContext:
        """Build the release semantics for rule evaluation."""
        draft = self._session.get(Release, DRAFT_RELEASE_ID)
        return ReleaseContext(
            current_release_id=current_release_id,
            draft_release_id=(
                DRAFT_RELEASE_ID if draft is not None else None
            ),
        )
