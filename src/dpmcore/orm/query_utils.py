"""Helpers for building backend-safe ORM queries.

SQL Server caps a single statement at 2,100 bound parameters, so an
unbounded ``IN (...)`` filter (one bound parameter per element) fails on
the ``mssql+pyodbc`` backend once the collection grows past that limit.
:func:`chunked_in` splits such a filter into fixed-size batches that stay
well below the cap on every supported backend.
"""

from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy.orm import Query

IN_CHUNK_SIZE = 900
"""Maximum number of values bound into a single ``IN (...)`` clause.

SQL Server caps a statement at 2,100 bound parameters and SQLite's
default limit is 999. 900 is safe on every supported backend and still
leaves headroom for the other bound parameters in the same statement
(release filters, literal codes, and so on).
"""


def chunked_in(
    query: Query[Any],
    column: Any,
    values: Iterable[Any],
) -> list[Any]:
    """Run *query* once per :data:`IN_CHUNK_SIZE` batch of *values*.

    Works around SQL Server's 2,100-bound-parameter-per-statement limit
    by splitting ``column.in_(values)`` into batches and concatenating
    the rows. This is only valid when the result is the simple *union*
    of the rows matching the ``IN`` set — i.e. the query has no
    ``LIMIT``/``OFFSET``, no aggregate or ``GROUP BY`` over the set, and
    no globally-significant ``ORDER BY``. Because the batches partition
    *values* disjointly, each matching row appears in exactly one batch,
    so the concatenation equals the single-statement result.

    Args:
        query: A query that does **not** already contain the chunked
            filter; the ``column.in_(...)`` filter is added per batch.
        column: The column the ``IN`` filter applies to.
        values: The collection bound into the ``IN`` clause. An empty
            collection issues no query and yields an empty list.

    Returns:
        The concatenated rows from every batch, in batch order.
    """
    values = list(values)
    rows: list[Any] = []
    for start in range(0, len(values), IN_CHUNK_SIZE):
        chunk = values[start : start + IN_CHUNK_SIZE]
        rows.extend(query.filter(column.in_(chunk)).all())
    return rows
