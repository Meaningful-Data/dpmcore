"""Schema-equivalence regression guard (issue #104).

dpmcore's ORM must emit an identical database schema on SQLAlchemy 1.4.50
(the python3-sqlalchemy apt package on Ubuntu 24.04) and on 2.0.x. This
test serialises ``Base.metadata`` to a canonical, dialect-aware
description and compares it to a committed snapshot.

Because 1.4 and 2.0 produce byte-identical canonical output, the snapshot
is a single source of truth: the 2.0 (poetry) CI job and the 1.4 (Noble
apt) CI job each verify their SQLAlchemy version matches it, which
together guarantees the two schemas agree. Types are rendered against
both the PostgreSQL and SQL Server dialects because SQLite — used by the
rest of the suite — ignores ``VARCHAR`` lengths and is lax about
``NOT NULL``, hiding exactly the drift this test exists to catch.

Regenerate after an *intentional* schema change (review the diff!) by
running this module as a script and redirecting stdout to the snapshot
file ``tests/unit/orm/_schema_snapshot.txt``.
"""

from pathlib import Path

from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects import mssql, postgresql

# Importing Base also executes dpmcore.orm.__init__, which registers
# every model on Base.metadata (needed for the full-schema snapshot).
from dpmcore.orm import Base

SNAPSHOT = Path(__file__).parent / "_schema_snapshot.txt"
_DIALECTS = (("pg", postgresql.dialect()), ("mssql", mssql.dialect()))


def canonical_schema() -> str:
    """Return a deterministic, dialect-aware description of the schema."""
    lines: list[str] = []
    for table in sorted(Base.metadata.tables.values(), key=lambda t: t.name):
        lines.append(f"TABLE {table.name}")
        for col in sorted(table.columns, key=lambda c: c.name):
            types = " ".join(
                f"{name}={col.type.compile(dialect=dialect)}"
                for name, dialect in _DIALECTS
            )
            ai = (
                "auto"
                if col.autoincrement in (True, "auto")
                else str(col.autoincrement)
            )
            fks = ",".join(
                sorted(fk.target_fullname for fk in col.foreign_keys)
            )
            lines.append(
                f"  COL {col.name} {types} null={col.nullable} "
                f"pk={col.primary_key} ai={ai} fks={fks}"
            )
        lines.append(
            "  PK " + ",".join(c.name for c in table.primary_key.columns)
        )
        uniques = sorted(
            tuple(c.name for c in con.columns)
            for con in table.constraints
            if isinstance(con, UniqueConstraint)
        )
        for cols in uniques:
            lines.append("  UNIQUE " + ",".join(cols))
        for idx in sorted(table.indexes, key=lambda i: i.name or ""):
            cols = ",".join(c.name for c in idx.columns)
            lines.append(f"  INDEX {idx.name} {cols}")
    return "\n".join(lines) + "\n"


def test_schema_matches_snapshot() -> None:
    """Current ORM schema must match the committed canonical snapshot."""
    expected = SNAPSHOT.read_text()
    actual = canonical_schema()
    assert actual == expected, (
        "ORM schema drifted from tests/unit/orm/_schema_snapshot.txt. "
        "If this change is intentional, regenerate the snapshot (see the "
        "module docstring) and review the diff carefully — it may mean a "
        "1.4/2.0 incompatibility or an unintended NOT NULL/type change."
    )


if __name__ == "__main__":  # pragma: no cover
    print(canonical_schema(), end="")
