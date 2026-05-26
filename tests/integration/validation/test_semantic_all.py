"""Parametrized semantic tests for all OperationVersion expressions in test_data.db.

Skipped automatically when tests/fixtures/test_data.db is absent.
"""

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from dpmcore.services.semantic import SemanticService

_DB = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "test_data.db"
)


def _missing_reason() -> str | None:
    if not _DB.exists():
        return f"db not found: {_DB}"
    return None


_MISSING = _missing_reason()


def _load_params():
    if _MISSING:
        return [
            pytest.param("", "", "", marks=pytest.mark.skip(reason=_MISSING))
        ]

    from sqlalchemy import text

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

    params = []
    for operation_vid, op_code, release_code, expression in rows:
        params.append(
            pytest.param(
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


@pytest.mark.parametrize(("code", "release", "expression"), _load_params())
def test_semantic(code, release, expression, semantic_service):
    result = semantic_service.validate(
        expression, release_code=release or None
    )
    assert result.is_valid, f"{code} | {result.error_message}"
