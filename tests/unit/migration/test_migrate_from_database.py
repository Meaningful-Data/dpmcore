"""Tests for ``MigrationService.migrate_from_database``."""

import sqlite3
from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, insert, select, text

from dpmcore.loaders import migration as migration_module
from dpmcore.loaders.migration import MigrationError, MigrationService
from dpmcore.orm.base import Base

RELEASE = Base.metadata.tables["Release"]
HEADER_VERSION = Base.metadata.tables["HeaderVersion"]

RELEASES = [
    {
        "ReleaseID": 1,
        "Code": "4.1",
        "Date": date(2025, 5, 28),
        "IsCurrent": False,
        "ErrorDate": datetime(2025, 6, 1, 13, 45, 10),
    },
    {
        "ReleaseID": 1010000003,
        "Code": "4.2.1",
        "Date": date(2026, 2, 20),
        "IsCurrent": True,
        "ErrorDate": None,
    },
    {
        "ReleaseID": 7,
        "Code": "Playground",
        "Date": None,
        "IsCurrent": None,
        "ErrorDate": None,
    },
]
HEADER_VERSIONS = [
    {"HeaderVID": 1, "Code": "0010", "Label": "≤ 30 days"},
    {"HeaderVID": 2, "Code": "010", "Label": None},
    {"HeaderVID": 3, "Code": "999", "Label": "Фондът"},
    {"HeaderVID": 4, "Code": "0", "Label": ""},
    {"HeaderVID": 5, "Code": None, "Label": "x"},
]


def _file_engine(path):
    return create_engine(f"sqlite:///{path}")


@pytest.fixture
def source(tmp_path):
    """A SQLite DPM database with a few typed rows."""
    engine = _file_engine(tmp_path / "source.db")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(insert(RELEASE), RELEASES)
        conn.execute(insert(HEADER_VERSION), HEADER_VERSIONS)
    return engine


@pytest.fixture
def target(tmp_path):
    return _file_engine(tmp_path / "target.db")


def _raw_rows(path, table):
    """Rows exactly as stored, with each value's storage class."""
    with sqlite3.connect(path) as conn:
        columns = [
            row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')
        ]
        selected = ", ".join(f'"{c}", typeof("{c}")' for c in columns)
        return conn.execute(
            f'SELECT {selected} FROM "{table}" ORDER BY 1'  # noqa: S608
        ).fetchall()


class TestRoundTrip:
    def test_every_orm_table_is_reported(self, source, target, tmp_path):
        out = tmp_path / "out.db"
        result = MigrationService(target).migrate_from_database(
            source, output_path=out
        )

        assert set(result.table_details) == set(Base.metadata.tables)
        assert result.tables_migrated == len(Base.metadata.tables)
        assert result.table_details["Release"] == 3
        assert result.table_details["HeaderVersion"] == 5
        assert result.total_rows == 8
        assert result.backend_used == "sqlite"
        assert result.warnings == []
        assert result.database_path == out

    def test_stored_values_and_types_are_identical(
        self, source, target, tmp_path
    ):
        out = tmp_path / "out.db"
        MigrationService(target).migrate_from_database(source, output_path=out)

        for table in Base.metadata.tables:
            assert _raw_rows(out, table) == _raw_rows(
                source.url.database, table
            ), table

    def test_typed_values_survive(self, source, target, tmp_path):
        out = tmp_path / "out.db"
        MigrationService(target).migrate_from_database(source, output_path=out)

        with _file_engine(out).connect() as conn:
            releases = conn.execute(
                select(
                    RELEASE.c.ReleaseID,
                    RELEASE.c.Code,
                    RELEASE.c.Date,
                    RELEASE.c.IsCurrent,
                    RELEASE.c.ErrorDate,
                ).order_by(RELEASE.c.Code)
            ).all()
            codes = conn.execute(
                select(HEADER_VERSION.c.Code).order_by(
                    HEADER_VERSION.c.HeaderVID
                )
            ).scalars()
            assert list(codes) == ["0010", "010", "999", "0", None]

        assert releases == [
            (
                1,
                "4.1",
                date(2025, 5, 28),
                False,
                datetime(2025, 6, 1, 13, 45, 10),
            ),
            (1010000003, "4.2.1", date(2026, 2, 20), True, None),
            (7, "Playground", None, None, None),
        ]

    def test_default_name_embeds_release(self, source, target, tmp_path):
        with patch.object(
            MigrationService, "_today_token", return_value="20260512"
        ):
            result = MigrationService(target).migrate_from_database(source)

        assert result.database_path == tmp_path / "target_4.2.1_20260512.db"
        assert result.database_path.is_file()

    def test_tables_are_copied_in_chunks(self, source, target, tmp_path):
        service = MigrationService(target)
        with (
            patch.object(migration_module, "_COPY_CHUNK_ROWS", 2),
            patch.object(
                service, "_load_table", wraps=service._load_table
            ) as load_table,
        ):
            result = service.migrate_from_database(
                source, output_path=tmp_path / "out.db"
            )

        sizes = [
            len(call.args[1])
            for call in load_table.call_args_list
            if call.args[0] == "HeaderVersion"
        ]
        assert sizes == [2, 2, 1]
        assert result.table_details["HeaderVersion"] == 5

    def test_numeric_guessing_is_not_applied(self, source, target, tmp_path):
        with patch.object(
            MigrationService, "_coerce_numeric_columns"
        ) as coerce:
            MigrationService(target).migrate_from_database(
                source, output_path=tmp_path / "out.db"
            )

        coerce.assert_not_called()

    def test_previous_target_content_is_replaced(
        self, source, target, tmp_path
    ):
        Base.metadata.create_all(target)
        with target.begin() as conn:
            conn.execute(insert(RELEASE), [{"ReleaseID": 99, "Code": "old"}])

        out = tmp_path / "out.db"
        MigrationService(target).migrate_from_database(source, output_path=out)

        with _file_engine(out).connect() as conn:
            ids = conn.execute(select(RELEASE.c.ReleaseID)).scalars().all()
        assert sorted(ids) == [1, 7, 1010000003]

    def test_source_schema_is_honoured(self, source, target, tmp_path):
        result = MigrationService(target).migrate_from_database(
            source, source_schema="main", output_path=tmp_path / "out.db"
        )

        assert result.table_details["Release"] == 3

    def test_in_memory_source_and_target(self):
        from sqlalchemy.pool import StaticPool

        src = create_engine("sqlite://", poolclass=StaticPool)
        Base.metadata.create_all(src)
        with src.begin() as conn:
            conn.execute(insert(RELEASE), RELEASES)
        dst = create_engine("sqlite://", poolclass=StaticPool)

        result = MigrationService(dst).migrate_from_database(src)

        assert result.table_details["Release"] == 3
        assert result.database_path is None


class TestSourceIsLeftAlone:
    def test_non_orm_tables_are_ignored(self, source, target, tmp_path):
        with source.begin() as conn:
            conn.execute(text("CREATE TABLE auth_user (id INTEGER)"))
            conn.execute(text("INSERT INTO auth_user VALUES (1)"))

        out = tmp_path / "out.db"
        result = MigrationService(target).migrate_from_database(
            source, output_path=out
        )

        assert "auth_user" not in result.table_details
        with sqlite3.connect(out) as conn:
            names = {
                row[0]
                for row in conn.execute("SELECT name FROM sqlite_master")
            }
        assert "auth_user" not in names
        assert result.warnings == []

    def test_source_rows_are_untouched(self, source, target, tmp_path):
        before = _raw_rows(source.url.database, "Release")

        MigrationService(target).migrate_from_database(
            source, output_path=tmp_path / "out.db"
        )

        assert _raw_rows(source.url.database, "Release") == before


class TestSchemaDrift:
    def test_missing_table_is_warned(self, source, target, tmp_path):
        with source.begin() as conn:
            conn.execute(text('DROP TABLE "HeaderVersion"'))

        result = MigrationService(target).migrate_from_database(
            source, output_path=tmp_path / "out.db"
        )

        assert "HeaderVersion" not in result.table_details
        assert result.tables_migrated == len(Base.metadata.tables) - 1
        assert any(
            "'HeaderVersion'" in w and "not found" in w
            for w in result.warnings
        )

    def test_missing_and_extra_columns_are_warned(self, tmp_path, target):
        path = tmp_path / "old.db"
        with sqlite3.connect(path) as conn:
            conn.execute(
                'CREATE TABLE "Release" ("ReleaseID" INTEGER PRIMARY KEY, '
                '"Code" VARCHAR, "Legacy" VARCHAR)'
            )
            conn.execute("INSERT INTO \"Release\" VALUES (1, '4.0', 'x')")

        out = tmp_path / "out.db"
        result = MigrationService(target).migrate_from_database(
            _file_engine(path), output_path=out
        )

        assert result.table_details == {"Release": 1}
        release_warnings = [w for w in result.warnings if "'Release'" in w]
        assert any(
            "'IsCurrent'" in w and "not found" in w for w in release_warnings
        )
        assert any(
            "['Legacy']" in w and "unknown" in w for w in release_warnings
        )
        with _file_engine(out).connect() as conn:
            row = conn.execute(
                select(RELEASE.c.Code, RELEASE.c.IsCurrent)
            ).one()
        assert row == ("4.0", None)


class TestRefusals:
    def test_same_engine(self, source):
        with pytest.raises(MigrationError, match="same database"):
            MigrationService(source).migrate_from_database(source)

        with source.connect() as conn:
            assert conn.execute(select(RELEASE.c.ReleaseID)).all()

    def test_same_file_through_another_engine(self, source, tmp_path):
        other = create_engine(f"sqlite:///{tmp_path}/./source.db")

        with pytest.raises(MigrationError, match="same database"):
            MigrationService(other).migrate_from_database(source)

        assert len(_raw_rows(source.url.database, "Release")) == 3

    def test_source_without_dpm_tables_keeps_the_target(
        self, tmp_path, target
    ):
        Base.metadata.create_all(target)
        with target.begin() as conn:
            conn.execute(insert(RELEASE), [{"ReleaseID": 99, "Code": "old"}])
        empty = _file_engine(tmp_path / "empty.db")

        with pytest.raises(MigrationError, match="No DPM tables"):
            MigrationService(target).migrate_from_database(empty)

        with target.connect() as conn:
            assert conn.execute(select(RELEASE.c.Code)).scalar() == "old"

    def test_unreadable_source(self, tmp_path, target):
        broken = _file_engine(tmp_path / "missing_dir" / "source.db")

        with pytest.raises(MigrationError, match="Database copy failed"):
            MigrationService(target).migrate_from_database(broken)

    def test_target_rejecting_rows(self, source, target, tmp_path):
        service = MigrationService(target)
        with (
            patch("pandas.DataFrame.to_sql", side_effect=RuntimeError("boom")),
            pytest.raises(MigrationError, match="Failed to load table"),
        ):
            service.migrate_from_database(source)


class TestDatabaseIdentity:
    @staticmethod
    def _pg(url="postgresql://u:p@Host:5432/dpm"):
        return create_engine(url)

    def test_server_databases_compare_by_location(self):
        a = MigrationService._database_identity(self._pg())
        b = MigrationService._database_identity(
            self._pg("postgresql://other:x@host:5432/dpm")
        )
        c = MigrationService._database_identity(
            self._pg("postgresql://u:p@host:5432/other")
        )

        assert a == b
        assert a != c

    def test_in_memory_sqlite_has_no_shared_identity(self):
        engine = create_engine("sqlite://")
        assert MigrationService._database_identity(engine) is None

    def test_same_server_and_schema_is_refused(self):
        service = MigrationService(self._pg(), schema="dpm")

        with pytest.raises(MigrationError, match="same database"):
            service._ensure_distinct_database(self._pg(), "dpm")

    def test_same_server_other_schema_is_allowed(self):
        service = MigrationService(self._pg(), schema="staging")

        service._ensure_distinct_database(self._pg(), "dpm")

    def test_other_server_is_allowed_without_connecting(self):
        service = MigrationService(self._pg())

        service._ensure_distinct_database(
            self._pg("postgresql://u:p@elsewhere/dpm"), None
        )

    def test_default_schema_is_looked_up(self):
        engine = self._pg()
        with patch.object(migration_module, "inspect") as inspect_mock:
            inspect_mock.return_value.default_schema_name = "public"
            assert MigrationService._effective_schema(engine, None) == "public"
            assert MigrationService._effective_schema(engine, "x") == "x"


class TestSnapshotReader:
    @staticmethod
    def _engine(dialect, snapshot_state=None):
        engine = MagicMock()
        engine.dialect.name = dialect
        conn = engine.connect.return_value.__enter__.return_value
        conn.execute.return_value.scalar.return_value = snapshot_state
        return engine

    def test_sqlite_is_returned_unchanged(self):
        engine = self._engine("sqlite")
        warnings = []

        assert (
            MigrationService._snapshot_reader(engine, None, warnings) is engine
        )
        assert warnings == []

    def test_schema_is_translated(self):
        engine = self._engine("sqlite")

        MigrationService._snapshot_reader(engine, "dpm", [])

        engine.execution_options.assert_called_once_with(
            schema_translate_map={None: "dpm"}
        )

    def test_postgresql_uses_repeatable_read(self):
        engine = self._engine("postgresql")

        MigrationService._snapshot_reader(engine, None, [])

        engine.execution_options.assert_called_once_with(
            isolation_level="REPEATABLE READ"
        )

    def test_sqlserver_uses_snapshot_when_enabled(self):
        engine = self._engine("mssql", snapshot_state=1)
        warnings = []

        MigrationService._snapshot_reader(engine, "dbo", warnings)

        engine.execution_options.assert_called_once_with(
            schema_translate_map={None: "dbo"}, isolation_level="SNAPSHOT"
        )
        assert warnings == []

    def test_sqlserver_falls_back_with_a_warning(self):
        engine = self._engine("mssql", snapshot_state=0)
        warnings = []

        reader = MigrationService._snapshot_reader(engine, None, warnings)

        assert reader is engine
        engine.execution_options.assert_not_called()
        assert len(warnings) == 1
        assert "SNAPSHOT isolation is not enabled" in warnings[0]


class TestTargetSpecifics:
    def test_sqlserver_identity_columns_are_looked_up(self, source, target):
        service = MigrationService(target)
        plan = [(RELEASE, ["ReleaseID", "Code"])]
        with (
            patch.object(
                service, "_mssql_identity_columns", return_value={"R": "id"}
            ) as identity,
            patch.object(service, "_load_table") as load_table,
            patch.object(target.dialect, "name", "mssql"),
            source.connect() as conn,
        ):
            details = service._copy_tables(conn, plan, [])

        identity.assert_called_once_with()
        assert load_table.call_args.args[3] == {"R": "id"}
        assert details == {"Release": 3}


class TestOtherSourceDialects:
    def test_no_explicit_begin_outside_sqlite(self, source, target, tmp_path):
        with (
            patch.object(
                MigrationService, "_snapshot_reader", return_value=source
            ),
            patch.object(source.dialect, "name", "other"),
        ):
            result = MigrationService(target).migrate_from_database(
                source, output_path=tmp_path / "out.db"
            )

        assert result.backend_used == "other"
        assert result.table_details["Release"] == 3
