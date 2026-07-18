"""Variable-generation service (port of ``variable_generation_tidy``).

Computes the complete variable-generation *plan* for a release —
which Variable/VariableVersion every table cell maps to, plus the
supporting key variables, compound keys, filing indicators and
contexts — **without writing anything to the database**. Every SQL
step that mutated the model either becomes part of the returned plan
or is applied virtually to the in-memory snapshot so later stages see
its effect.

Dropped SQL steps (persistence-only, no Python counterpart):

* the destructive "cleaning stage" that deletes a previous generation
  run for the current release — this computation is stateless and
  assumes a pre-generation database;
* ``Aux_CellStatus`` writes (subsumed by ``CellAssignment.outcome``);
* real id allocation (``MAX + ROW_NUMBER``) and sequence realignment
  (replaced by deterministic plan-local temp ids, spec section 5.5);
* the final ``Cleaning_Service_01`` call (spec decision 7);
* the ``ItemCategory.Signature`` refresh — signatures are computed
  where needed, never stored.
"""

from __future__ import annotations

import time
from datetime import date
from typing import Dict, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from dpmcore.orm.infrastructure import Release
from dpmcore.services.model_validation.release_context import (
    ReleaseContext,
)
from dpmcore.services.model_validation.service import (
    ModelValidationService,
)
from dpmcore.services.model_validation.snapshot import ModelSnapshot
from dpmcore.services.model_validation.types import (
    SEVERITY_ERROR,
    ModelValidationResult,
    Violation,
)
from dpmcore.services.variable_generation import (
    aspects,
    assignment,
    checks,
    filing_indicators,
    header_dedup,
    keys,
    reporting,
)
from dpmcore.services.variable_generation.state import GenerationState
from dpmcore.services.variable_generation.types import (
    GenerationStatus,
    VariableGenerationResult,
)


def _resolve_release(
    session: Session,
    release_id: Optional[int],
    release_code: Optional[str],
) -> Tuple[Release, ReleaseContext]:
    """Resolve the release under generation and its semantics.

    Reuses the model-validation service's resolution rules (default
    is the release flagged ``IsCurrent``; ``Invalid``/``NotFound``
    raised exactly as there) so both services behave identically.
    """
    validator = ModelValidationService(session)
    release = validator._resolve_release(  # noqa: SLF001
        release_id, release_code
    )
    context = validator._release_context(  # noqa: SLF001
        release.release_id
    )
    return release, context


class VariableGenerationService:
    """Compute-only variable generation for a release.

    Read-only: the service receives a session, loads the model once
    and returns a
    :class:`~dpmcore.services.variable_generation.types
    .VariableGenerationResult` describing everything the SQL
    procedure would have persisted.
    """

    def __init__(self, session: Session) -> None:
        """Bind the service to a SQLAlchemy session.

        Args:
            session: Session on the DPM database. Only read.
        """
        self._session = session

    def generate(
        self,
        release_id: Optional[int] = None,
        release_code: Optional[str] = None,
        validate_first: bool = True,
    ) -> VariableGenerationResult:
        """Compute the variable-generation plan.

        Args:
            release_id: Release to generate for. Defaults to the
                release flagged ``IsCurrent``.
            release_code: Alternative lookup by release code.
            validate_first: Run the model-validation rule set as a
                gate; any error-severity violation blocks generation
                (``BLOCKED_BY_VALIDATION``).

        Returns:
            The generation plan, or a blocked result carrying the
            validation outcome / consistency violations.

        Raises:
            Invalid: If both ``release_id`` and ``release_code`` are
                given.
            NotFound: If the requested release does not exist, or no
                current release is flagged.
        """
        start = time.perf_counter()
        release, context = _resolve_release(
            self._session, release_id, release_code
        )
        snapshot = ModelSnapshot(self._session)
        snapshot, dedups = header_dedup.detect_and_apply(
            snapshot, context
        )

        validation: Optional[ModelValidationResult] = None
        if validate_first:
            validation = ModelValidationService(
                self._session
            ).validate(
                release_id=release.release_id, snapshot=snapshot
            )
            if validation.error_count > 0:
                return self._blocked(
                    GenerationStatus.BLOCKED_BY_VALIDATION,
                    release,
                    validation,
                    (),
                    start,
                )

        state = GenerationState(release_dates=self._release_dates())
        keys.identify_key_variables(snapshot, context, state)
        keys.generate_compound_keys(snapshot, context, state)
        filing_indicators.generate_filing_indicators(
            snapshot, context, state
        )
        records = assignment.build_working_set(snapshot, context)
        aspects.compute_new_coordinates(
            snapshot, context, records, state
        )
        blocking = checks.blocking_checks(records, snapshot, context)
        if any(v.severity == SEVERITY_ERROR for v in blocking):
            return self._blocked(
                GenerationStatus.BLOCKED_BY_CONSISTENCY,
                release,
                validation,
                tuple(blocking),
                start,
            )
        warnings = assignment.decide_outcomes(
            records, snapshot, context, state
        )
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return VariableGenerationResult(
            status=GenerationStatus.COMPLETED,
            release_id=release.release_id,
            release_code=release.code,
            validation=validation,
            consistency_violations=tuple(blocking) + tuple(warnings),
            new_variables=state.all_variables(),
            new_variable_versions=state.all_variable_versions(),
            new_contexts=state.all_contexts(),
            new_compound_keys=tuple(state.compound_keys),
            new_filing_indicators=tuple(state.filing_indicators),
            cell_assignments=reporting.build_cell_assignments(records),
            header_deduplications=dedups,
            summary=reporting.build_summary(records),
            elapsed_ms=elapsed_ms,
        )

    # --------------------------------------------------------------
    # Internals
    # --------------------------------------------------------------

    def _release_dates(self) -> Dict[int, Optional[date]]:
        """``release_id -> Release.Date`` for recency ordering."""
        stmt = select(Release.release_id, Release.date)
        rows = self._session.execute(stmt).all()
        return {row[0]: row[1] for row in rows}  # noqa: C416

    def _blocked(
        self,
        status: GenerationStatus,
        release: Release,
        validation: Optional[ModelValidationResult],
        violations: Tuple[Violation, ...],
        start: float,
    ) -> VariableGenerationResult:
        """A blocked result: plan fields empty, findings attached."""
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return VariableGenerationResult(
            status=status,
            release_id=release.release_id,
            release_code=release.code,
            validation=validation,
            consistency_violations=violations,
            new_variables=(),
            new_variable_versions=(),
            new_contexts=(),
            new_compound_keys=(),
            new_filing_indicators=(),
            cell_assignments=(),
            header_deduplications=(),
            summary=(),
            elapsed_ms=elapsed_ms,
        )
