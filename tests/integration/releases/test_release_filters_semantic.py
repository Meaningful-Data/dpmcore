import pandas as pd
from py_dpm.dpm.models import Base, TableVersion
from py_dpm.dpm.queries.filters import filter_by_release
from py_dpm.dpm_xl.ast import operands as operands_module
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def _make_session():
    """Create a lightweight in-memory SQLAlchemy session for query compilation."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.bind = engine
    Session = sessionmaker(bind=engine)
    return Session()


def test_filter_by_release_uses_is_null_for_end_release():
    """Ensure filter_by_release uses SQLAlchemy .is_(None) semantics for end_col,
    resulting in an 'IS NULL' predicate rather than '= NULL' in the SQL.

    This is important for PostgreSQL, which is strict about boolean expressions
    and NULL comparison semantics.
    """
    session = _make_session()

    query = session.query(TableVersion)
    filtered = filter_by_release(
        query,
        start_col=TableVersion.startreleaseid,
        end_col=TableVersion.endreleaseid,
        release_id=5,
    )

    sql = str(
        filtered.statement.compile(
            dialect=session.get_bind().dialect,
            compile_kwargs={"literal_binds": True},
        )
    ).upper()

    # Ensure NULL handling uses IS NULL rather than = NULL
    assert "IS NULL" in sql
    assert "= NULL" not in sql


def test_operands_check_headers_calls_filter_by_release_with_correct_args(
    monkeypatch,
):
    """Verify that OperandsChecking.check_headers wires filter_by_release correctly:
    - start_col is TableVersion.startreleaseid
    - end_col is TableVersion.endreleaseid
    - release_id matches the instance's release_id.
    """
    called = {}

    def fake_filter_by_release(
        query, start_col, end_col, release_id=None, release_code=None
    ):
        called["query"] = query
        called["start_col"] = start_col
        called["end_col"] = end_col
        called["release_id"] = release_id
        called["release_code"] = release_code
        return query

    monkeypatch.setattr(
        operands_module, "filter_by_release", fake_filter_by_release
    )

    # Stub out the pandas helpers used inside check_headers so that no real DB
    # access is attempted.
    import py_dpm.dpm.models as models

    monkeypatch.setattr(
        models,
        "_compile_query_for_pandas",
        lambda stmt, session: stmt,
    )

    def fake_read_sql(sql, session):
        # Return an empty DataFrame with the expected columns so that
        # check_headers completes without touching self.operands.
        return pd.DataFrame(
            columns=[
                "Code",
                "StartReleaseID",
                "EndReleaseID",
                "Direction",
                "HasOpenRows",
                "HasOpenColumns",
                "HasOpenSheets",
            ]
        )

    monkeypatch.setattr(models, "_read_sql_with_connection", fake_read_sql)

    session = _make_session()

    # Create a minimal OperandsChecking instance without running its __init__,
    # since that would require a fully-populated AST and database.
    oc = object.__new__(operands_module.OperandsChecking)
    oc.session = session
    oc.release_id = 7
    oc.tables = {"DummyTable": {}}  # Only keys are needed by check_headers

    operands_module.OperandsChecking.check_headers(oc)

    assert called["start_col"] is TableVersion.startreleaseid
    assert called["end_col"] is TableVersion.endreleaseid
    assert called["release_id"] == 7
    assert called["release_code"] is None
