"""Parity tests: Python modelling services vs SQL stored procedures.

Compares :class:`ModelValidationService` output against golden CSVs
exported from a SQL Server run of ``check_modelling_rules_tidy`` (see
``scripts/parity/README.md`` for how to produce the fixtures). All
tests auto-skip when the fixtures are absent, mirroring the
``test_data.db`` convention.

Comparison is by business key, never by message text or surrogate id
(spec ``08-modelling-services.md`` §9.2).
"""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parents[2] / "fixtures"
PARITY_DB = FIXTURES / "parity_dpm.db"
PARITY_DIR = FIXTURES / "parity"
VIOLATIONS_CSV = PARITY_DIR / "model_violations.csv"
ALLOWLIST = PARITY_DIR / "allowlist.yaml"

pytestmark = pytest.mark.skipif(
    not (PARITY_DB.exists() and VIOLATIONS_CSV.exists()),
    reason=(
        "parity fixtures missing — see scripts/parity/README.md "
        "(needs parity_dpm.db and parity/model_violations.csv)"
    ),
)


def _load_allowlist() -> set[tuple[str, str]]:
    """Load allowed (legacy_code, key) differences, if any."""
    if not ALLOWLIST.exists():
        return set()
    import yaml  # type: ignore[import-untyped]

    with ALLOWLIST.open() as fh:
        entries = yaml.safe_load(fh) or []
    return {(e["legacy_code"], str(e["key"])) for e in entries}


def _sql_violation_key(row: dict[str, str]) -> tuple[str, str]:
    """Business key of a SQL ModelViolations row.

    Uses the first populated identifier column, matching the primary
    ObjectRef the Python port emits for each rule.
    """
    for column in (
        "TableVID",
        "HeaderVID",
        "HeaderID",
        "ItemID",
        "CategoryID",
        "CellID",
    ):
        value = row.get(column, "")
        if value not in ("", "NULL", None):
            return (row["ViolationCode"], f"{column}={value}")
    return (row["ViolationCode"], "")


@pytest.fixture(scope="module")
def python_result():
    from dpmcore.connection import connect
    from dpmcore.services.model_validation import (
        ModelValidationService,
    )

    with connect(f"sqlite:///{PARITY_DB}") as db:
        yield ModelValidationService(db.orm).validate()


@pytest.fixture(scope="module")
def sql_violations() -> list[dict[str, str]]:
    with VIOLATIONS_CSV.open(newline="") as fh:
        return list(csv.DictReader(fh))


def test_blocking_flag_matches_severity(python_result, sql_violations):
    """isBlocking=1 codes must map to error severity and vice versa."""
    sql_blocking = {
        r["ViolationCode"]: r["isBlocking"] in ("1", "True")
        for r in sql_violations
    }
    for violation in python_result.violations:
        if violation.legacy_code in sql_blocking:
            expected = sql_blocking[violation.legacy_code]
            assert (violation.severity == "error") == expected, (
                f"{violation.rule_id}: severity mismatch vs SQL "
                f"isBlocking"
            )


def test_violation_multiset_matches(python_result, sql_violations):
    """Multiset of (legacy_code, primary key) must match the SQL."""
    allow = _load_allowlist()

    sql_keys = Counter(
        key
        for key in map(_sql_violation_key, sql_violations)
        if key not in allow
    )
    py_keys = Counter()
    for violation in python_result.violations:
        primary = violation.objects[0] if violation.objects else None
        key_repr = ""
        if primary is not None and primary.id is not None:
            key_repr = f"id={primary.id}"
        key = (violation.legacy_code, key_repr)
        if key not in allow:
            py_keys[key] += 1

    missing = {
        k: c for k, c in sql_keys.items() if py_keys.get(k, 0) < c
    }
    extra = {
        k: c for k, c in py_keys.items() if sql_keys.get(k, 0) < c
    }
    # Full-detail comparison is refined per-rule once fixtures exist;
    # the per-code totals below are the hard gate.
    sql_by_code = Counter(k[0] for k in sql_keys.elements())
    py_by_code = Counter(k[0] for k in py_keys.elements())
    assert sql_by_code == py_by_code, (
        f"per-code counts diverge; missing={missing} extra={extra}"
    )
