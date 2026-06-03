"""Scope-wide parameter type-consistency checking.

A DPM-XL parameter (``{p_code, type}``) is an execution-time input bound to a
single value across every operation it co-executes with. Two operations
co-execute when their operation scopes share a module version, so a parameter's
declared type is intrinsic: it must be identical wherever such operations
reference it.

Single-expression semantic validation can only enforce this *within* one
expression. This module extends the check to operations already persisted in
the database: when a new expression references a parameter, it must not clash
with the declared type any co-scoped persisted operation gives the same code.

Performance is built on three ideas:

* **Early exit** — expressions that reference no parameters never touch this
  code, and one with no resolvable scope (no tables) returns immediately.
* **Cheap DB pre-filter** — only operations whose stored expression contains a
  parameter reference (``LIKE '%{p%'``; selection prefixes are ``t/g/o/v/p``,
  so ``{p`` is distinctive) are ever fetched or parsed.
* **Lazy, connection-scoped index** — the parameterised operations are parsed
  once and cached as ``code -> [(declared_type, module_vids)]`` for the
  connection's lifetime, so the cost is amortised across a whole validation
  session. The index is release-agnostic; release-awareness comes for free
  because the expression's own module versions are resolved for its release.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from dpmcore.dpm_xl.ast.nodes import AST, ParameterRef
from dpmcore.dpm_xl.model_queries import ModuleVersionQuery
from dpmcore.errors import SemanticError
from dpmcore.orm.operations import (
    OperationScope,
    OperationScopeComposition,
    OperationVersion,
)
from dpmcore.services.syntax import SyntaxService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# Distinctive opener of a parameter reference, used as a DB-side pre-filter.
_PARAM_MARKER = "%{p%"


def _walk_parameter_refs(node: object) -> list[ParameterRef]:
    """Collect every ``ParameterRef`` in an AST (no DB lookups)."""
    found: list[ParameterRef] = []

    def walk(current: object) -> None:
        if isinstance(current, ParameterRef):
            found.append(current)
        if isinstance(current, AST):
            for value in vars(current).values():
                walk(value)
        elif isinstance(current, list):
            for item in current:
                walk(item)

    walk(node)
    return found


class ParameterScopeIndex:
    """Lazy, connection-scoped index of persisted parameter declarations.

    Maps each parameter code to the ``(declared_type, module_vids)`` pairs of
    every persisted operation that declares it -- ``module_vids`` being the
    module versions the operation is scoped to. Built once on first use and
    cached; call :meth:`reset` if the underlying operations are mutated.

    Args:
        session: An open SQLAlchemy session bound to a DPM database.
    """

    def __init__(self, session: "Session") -> None:
        """Build the index bound to ``session`` (no query until first use)."""
        self.session = session
        self._syntax = SyntaxService()
        self._index: dict[str, list[tuple[str, frozenset[int]]]] | None = None

    def reset(self) -> None:
        """Drop the cached index (e.g. after operations are written)."""
        self._index = None

    def module_vids_for(
        self, table_codes: list[str], release_id: int | None
    ) -> frozenset[int]:
        """Resolve the module versions an expression's tables belong to."""
        if not table_codes:
            return frozenset()
        df = ModuleVersionQuery.get_from_table_codes(
            session=self.session,
            table_codes=table_codes,
            release_id=release_id,
        )
        if df.empty:
            return frozenset()
        return frozenset(int(vid) for vid in df["ModuleVID"].tolist())

    def check(
        self, declarations: dict[str, str], module_vids: frozenset[int]
    ) -> None:
        """Raise ``3-8`` on a clash with a co-scoped persisted operation.

        Args:
            declarations: ``{code: declared_type}`` for the expression being
                validated.
            module_vids: The module versions that expression is scoped to. A
                clash requires both a shared code and a shared module version.
        """
        if not module_vids:
            return
        index = self._index if self._index is not None else self._build()
        self._index = index
        for code, declared_type in declarations.items():
            for other_type, other_mvids in index.get(code, ()):
                if other_type != declared_type and (other_mvids & module_vids):
                    raise SemanticError(
                        "3-8",
                        parameter=code,
                        type_1=other_type,
                        type_2=declared_type,
                    )

    # ------------------------------------------------------------------ #
    # Index construction
    # ------------------------------------------------------------------ #

    def _build(self) -> dict[str, list[tuple[str, frozenset[int]]]]:
        """Query parameterised operations and index their declarations."""
        return self._index_from_rows(self._query_parameter_rows())

    def _query_parameter_rows(self) -> list[tuple[int, str, int]]:
        """Fetch ``(operation_vid, expression, module_vid)`` for param ops.

        The ``LIKE`` filter guarantees a non-null expression, so the cast to
        ``str`` is sound.
        """
        rows = (
            self.session.query(
                OperationVersion.operation_vid,
                OperationVersion.expression,
                OperationScopeComposition.module_vid,
            )
            .join(
                OperationScope,
                OperationVersion.operation_vid == OperationScope.operation_vid,
            )
            .join(
                OperationScopeComposition,
                OperationScope.operation_scope_id
                == OperationScopeComposition.operation_scope_id,
            )
            .filter(OperationVersion.expression.like(_PARAM_MARKER))
            .all()
        )
        return cast("list[tuple[int, str, int]]", rows)

    def _index_from_rows(
        self, rows: list[tuple[int, str, int]]
    ) -> dict[str, list[tuple[str, frozenset[int]]]]:
        """Group rows by operation, then index code -> (type, module_vids)."""
        by_op: dict[int, tuple[str, set[int]]] = {}
        for op_vid, expression, module_vid in rows:
            by_op.setdefault(op_vid, (expression, set()))[1].add(module_vid)

        index: dict[str, list[tuple[str, frozenset[int]]]] = {}
        for expression, module_vids in by_op.values():
            mvids = frozenset(module_vids)
            for code, declared_type in self._declarations(expression).items():
                index.setdefault(code, []).append((declared_type, mvids))
        return index

    def _declarations(self, expression: str) -> dict[str, str]:
        """Extract ``{code: declared_type}`` from one expression (no DB).

        A malformed/legacy persisted expression that fails to parse is skipped
        rather than aborting the whole index build.
        """
        try:
            ast = self._syntax.parse(expression)
        except Exception:
            return {}
        decls: dict[str, str] = {}
        for ref in _walk_parameter_refs(ast):
            decls.setdefault(ref.code, ref.param_type)
        return decls
