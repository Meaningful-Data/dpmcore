"""Parametrized semantic tests for all OperationVersion expressions in test_data.db.

Skipped automatically when tests/fixtures/test_data.db is absent.

Some published expressions do not validate, because of engine limitations or
dictionary data errors. Those are listed, with the error code each one fails
with, in ``semantic_all_known_failures.csv``. A listed
expression must keep failing with that code; anything else must be valid. So
the sweep fails on a new failure, on a known one whose code changes, and on a
known one that now passes (remove it from the list).

The list belongs to one fixture DB. After regenerating it, rebuild the list with
``scripts/check_semantic.py --known-failures <this list>`` (see
``tests/fixtures/README.md``).
"""

import csv
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from dpmcore.services.semantic import SemanticService

_DB = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "test_data.db"
)
_KNOWN_FAILURES = Path(__file__).with_name("semantic_all_known_failures.csv")

_REFRESH_HINT = (
    "refresh the list with `python scripts/check_semantic.py "
    "--known-failures tests/integration/validation/"
    "semantic_all_known_failures.csv`"
)


def _missing_reason() -> str | None:
    if not _DB.exists():
        return f"db not found: {_DB}"
    return None


_MISSING = _missing_reason()


def _load_known_failures() -> dict[int, str]:
    """Map each known-failing OperationVID to the error code it fails with."""
    with _KNOWN_FAILURES.open(newline="", encoding="utf-8") as fh:
        return {
            int(row["operation_vid"]): row["error_code"]
            for row in csv.DictReader(fh)
        }


_KNOWN = _load_known_failures()


def _load_rows():
    engine = create_engine(f"sqlite:///{_DB}")
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT
                    ov.OperationVID,
                    o.Code,
                    r.Code AS ReleaseCode,
                    ov.Expression
                FROM OperationVersion ov
                JOIN Operation o ON o.OperationID = ov.OperationID
                LEFT JOIN Release r ON r.ReleaseID = ov.StartReleaseID
                WHERE ov.Expression IS NOT NULL
                  AND trim(ov.Expression) != ''
                """
            )
        ).fetchall()
    engine.dispose()
    return rows


_ROWS = [] if _MISSING else _load_rows()


def _load_params():
    if _MISSING:
        return [
            pytest.param(
                0, "", "", "", marks=pytest.mark.skip(reason=_MISSING)
            )
        ]

    params = []
    for operation_vid, op_code, release_code, expression in _ROWS:
        params.append(
            pytest.param(
                operation_vid,
                op_code or str(operation_vid),
                release_code or "",
                expression.strip(),
                id=f"{op_code or operation_vid}-{operation_vid}",
            )
        )
    return params


@pytest.fixture(scope="module")
def semantic_service():
    if _MISSING:
        pytest.skip(_MISSING)
    engine = create_engine(f"sqlite:///{_DB}")
    Session = sessionmaker(bind=engine)
    session = Session()
    svc = SemanticService(session)
    yield svc
    session.close()
    engine.dispose()


@pytest.mark.parametrize(
    ("operation_vid", "code", "release", "expression"), _load_params()
)
def test_semantic(operation_vid, code, release, expression, semantic_service):
    result = semantic_service.validate(
        expression, release_code=release or None
    )
    expected_code = _KNOWN.get(operation_vid)
    if expected_code is None:
        assert result.is_valid, f"{code} | {result.error_message}"
        return

    assert not result.is_valid, (
        f"{code} is listed as a known failure ({expected_code}) but is now "
        f"valid: remove it from {_KNOWN_FAILURES.name}"
    )
    assert result.error_code == expected_code, (
        f"{code} is listed as failing with {expected_code} but now fails "
        f"with {result.error_code}: {result.error_message}"
    )


def test_known_failures_match_the_fixture_db():
    """Every listed failure is an expression of this fixture DB.

    A list built from another DB would quietly excuse nothing and flag
    everything; fail once, up front, instead.
    """
    if _MISSING:
        pytest.skip(_MISSING)
    vids = {operation_vid for operation_vid, *_ in _ROWS}
    stale = sorted(set(_KNOWN) - vids)
    assert not stale, (
        f"{len(stale)} listed failure(s) are not in {_DB.name} "
        f"(e.g. {stale[:5]}): {_REFRESH_HINT}"
    )
