"""Semantic validation service — requires a database session."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional, cast

from sqlalchemy import func

from dpmcore.dpm_xl.ast.nodes import (
    AST,
    ParameterRef,
    canonical_param_type,
    parameter_default_value,
)
from dpmcore.dpm_xl.ast.operands import OperandsChecking
from dpmcore.dpm_xl.model_queries import ModuleVersionQuery
from dpmcore.dpm_xl.semantic_analyzer import InputAnalyzer
from dpmcore.dpm_xl.utils.filters import resolve_release_id
from dpmcore.dpm_xl.warning_collector import collect_warnings
from dpmcore.errors import SemanticError
from dpmcore.orm.infrastructure import Release
from dpmcore.orm.operations import (
    OperationScope,
    OperationScopeComposition,
    OperationVersion,
)
from dpmcore.orm.query_utils import chunked_in
from dpmcore.services.syntax import SyntaxService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@dataclass(frozen=True)
class ParameterInfo:
    """Declared metadata for a parameter referenced by an expression.

    This is the runtime-binding contract: dpmcore reports which parameters an
    expression needs (and their declared types/defaults); the downstream engine
    resolves and binds their values.

    ``declared_type`` is ``None`` when the parameter was referenced with the
    simplified ``{pCode}`` spelling — the expression pins the identity of the
    parameter but defers its scalar type to the engine's parameter registry.

    ``is_set`` is a derived property (``Set`` prefix of the canonical
    ``declared_type``), not a stored field, so there is one source of truth for
    set-ness; a parameter without a declared type is not classified as a set
    at this stage.
    """

    code: str
    declared_type: Optional[str]
    default: Any = None

    @property
    def is_set(self) -> bool:
        """``True`` for the set variants.

        The canonical ``declared_type`` is ``SetNumber``/``SetItem``/…; no
        scalar type name starts with ``Set``, so the prefix is unambiguous.
        A parameter with no declared type (simplified ``{pCode}`` form) is
        reported as ``False`` here; the engine registry resolves set-ness
        together with the type at binding time.
        """
        return self.declared_type is not None and (
            self.declared_type.startswith("Set")
        )


@dataclass(frozen=True)
class SemanticResult:
    """Outcome of a semantic validation."""

    is_valid: bool
    error_message: Optional[str]
    error_code: Optional[str]
    expression: str
    results: Optional[Any] = None
    warning: Optional[str] = None
    parameters: tuple[ParameterInfo, ...] = field(default_factory=tuple)


def _parameters_from_oc(
    oc: OperandsChecking,
) -> tuple[ParameterInfo, ...]:
    """Collect referenced parameters from an OperandsChecking pass.

    Deduplicated by code, preserving first-seen order. A parameter is an
    execution-time input bound to a single value across every expression that
    co-executes with it, so its declared type is intrinsic: all references to a
    given code must declare the same type. Conflicting redeclarations within an
    expression raise ``3-8``. Defaults are per-reference fallbacks and are
    intentionally *not* compared (they never reach the scope-wide registry).
    """
    seen: dict[str, ParameterInfo] = {}
    for node in oc.parameters:
        # Surface the engine's canonical type name (``number`` -> ``Number``).
        # A simplified ``{pCode}`` reference has no inline type; leave
        # ``declared_type`` as ``None`` and let the engine's parameter
        # registry supply it at binding time. A verbose reference that
        # follows still wins the type declaration on the same code.
        declared: Optional[str] = (
            canonical_param_type(node.param_type)
            if node.param_type is not None
            else None
        )
        existing = seen.get(node.code)
        if existing is None:
            seen[node.code] = ParameterInfo(
                code=node.code,
                declared_type=declared,
                default=parameter_default_value(node.default),
            )
        elif existing.declared_type is None and declared is not None:
            # A later verbose reference upgrades the entry with its declared
            # type; the default carried on the first-seen reference is kept.
            seen[node.code] = ParameterInfo(
                code=existing.code,
                declared_type=declared,
                default=existing.default,
            )
        elif (
            existing.declared_type is not None
            and declared is not None
            and existing.declared_type != declared
        ):
            raise SemanticError(
                "3-8",
                parameter=node.code,
                type_1=existing.declared_type,
                type_2=declared,
            )
    return tuple(seen.values())


# Distinctive opener of a parameter reference, used as a DB-side pre-filter.
# Selection prefixes are t/g/o/v/p, so ``{p`` marks a parameter reference.
_PARAM_MARKER = "%{p%"

# Whitespace characters stripped from an expression before the ``{p`` match.
_WHITESPACE_CHARS = (" ", "\t", "\n", "\r")


def _whitespace_insensitive(column: Any) -> Any:
    """Wrap a text column so a LIKE match ignores whitespace.

    DPM-XL expressions can be hand-written, so a parameter reference may carry
    spaces after the brace (``{ p_x}``) or span lines. Stripping
    space/tab/newline/CR from the column *at query time* lets the ``{p`` marker
    match regardless of layout. The stored expression is untouched — only the
    comparison is normalised — and ``_declarations`` re-parses the raw text
    authoritatively. ``REPLACE`` is standard across SQLite/PostgreSQL/SQL
    Server, and ``NULL`` survives every ``REPLACE`` (so ``NULL`` rows are still
    excluded by ``LIKE``).
    """
    stripped = column
    for whitespace in _WHITESPACE_CHARS:
        stripped = func.replace(stripped, whitespace, "")
    return stripped


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


def _module_vids_for(
    session: "Session", table_codes: list[str], release_id: Optional[int]
) -> frozenset[int]:
    """Resolve the module versions an expression's tables belong to."""
    if not table_codes:
        return frozenset()
    df = ModuleVersionQuery.get_from_table_codes(
        session=session, table_codes=table_codes, release_id=release_id
    )
    if df.empty:
        return frozenset()
    return frozenset(int(vid) for vid in df["ModuleVID"].tolist())


class SemanticService:
    """Validate DPM-XL expressions against the data dictionary.

    Args:
        session: An open SQLAlchemy session bound to a DPM database.
    """

    def __init__(self, session: "Session") -> None:
        """Build the service bound to ``session``."""
        self.session = session
        self._syntax = SyntaxService()
        # Exposed after each validate() call for downstream consumers.
        self.ast: Any = None
        self.oc_data: Any = None
        self.oc_tables: Any = None
        self.oc_parameters: tuple[ParameterInfo, ...] | None = None

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def validate(
        self,
        expression: str,
        release_id: Optional[int] = None,
        release_code: Optional[str] = None,
    ) -> SemanticResult:
        """Full semantic validation of *expression*.

        Returns a :class:`SemanticResult` — never raises on validation
        failure.

        A referenced parameter's declared type is also checked against
        co-scoped operations already in the database (raising ``3-8`` on a
        clash). This lookup only runs when the expression actually references a
        parameter and is scoped in SQL to co-located operations, so it adds no
        overhead to a parameter-free database.

        Args:
            expression: The DPM-XL expression to validate.
            release_id: Optional release ID filter. When neither this nor
                ``release_code`` is given, defaults to the latest release.
            release_code: Optional release code (mutually exclusive
                with ``release_id``).
        """
        try:
            release_id = resolve_release_id(
                self.session,
                release_id=release_id,
                release_code=release_code,
            )
            # Default to the latest release when none is specified, matching
            # the DPM-XL engine convention (see scopes_calculator). This keeps
            # the co-scope parameter check release-scoped instead of spanning
            # every release. ``None`` only survives on an empty schema.
            if release_id is None:
                release_id = ModuleVersionQuery.get_last_release(self.session)
            if release_id is not None:
                exists = (
                    self.session.query(Release.release_id)
                    .filter(Release.release_id == release_id)
                    .first()
                )
                if exists is None:
                    raise SemanticError("1-21", release_id=release_id)

            with collect_warnings() as wc:
                # ``parse`` is inside the collector so warnings emitted from
                # AST construction (e.g. deprecated ``"null"`` string literal
                # in ``visitLiteral``) are captured alongside the ones from
                # the analyzer pass.
                ast = self._syntax.parse(expression)
                self.ast = ast

                oc = OperandsChecking(
                    session=self.session,
                    expression=expression,
                    ast=ast,
                    release_id=release_id,
                )
                self.oc_data = oc.data
                self.oc_tables = oc.tables
                self.oc_parameters = _parameters_from_oc(oc)

                analyzer = InputAnalyzer(expression)
                analyzer.data = oc.data
                analyzer.key_components = oc.key_components
                analyzer.open_keys = oc.open_keys
                analyzer.preconditions = oc.preconditions

                results = analyzer.visit(ast)

            if self.oc_parameters:
                # Feed the cross-op check only the parameters whose type is
                # actually declared here; a simplified ``{pCode}`` reference
                # cannot conflict with a co-scoped op because it has no
                # declared type on our side.
                self._check_persisted_scope(
                    {
                        p.code: p.declared_type
                        for p in self.oc_parameters
                        if p.declared_type is not None
                    },
                    list(oc.tables.keys()) if oc.tables else [],
                    release_id,
                )

            return SemanticResult(
                is_valid=True,
                error_message=None,
                error_code=None,
                expression=expression,
                results=results,
                warning=wc.get_combined_warning(),
                parameters=self.oc_parameters,
            )

        except SemanticError as exc:
            self.oc_data = None
            self.oc_tables = None
            self.oc_parameters = None
            return SemanticResult(
                is_valid=False,
                error_message=str(exc),
                error_code=getattr(exc, "code", None),
                expression=expression,
            )
        except Exception as exc:
            self.oc_data = None
            self.oc_tables = None
            self.oc_parameters = None
            return SemanticResult(
                is_valid=False,
                error_message=str(exc),
                error_code="UNKNOWN",
                expression=expression,
            )

    def is_valid(
        self,
        expression: str,
        release_id: Optional[int] = None,
        release_code: Optional[str] = None,
    ) -> bool:
        """Quick boolean check."""
        return self.validate(
            expression,
            release_id=release_id,
            release_code=release_code,
        ).is_valid

    # ------------------------------------------------------------------ #
    # Scope-wide parameter consistency (against persisted operations)
    # ------------------------------------------------------------------ #

    def _check_persisted_scope(
        self,
        declarations: dict[str, str],
        table_codes: list[str],
        release_id: Optional[int],
    ) -> None:
        """Raise ``3-8`` if a parameter clashes with a co-scoped persisted op.

        Two operations co-execute when their scopes share a module version, so
        a parameter bound across them must declare a single type. This compares
        the expression's parameter declarations against every parameterised
        operation already persisted in a shared module version. The lookup is
        scoped in SQL — only co-located, parameter-bearing rows are fetched —
        so it costs nothing when no such operation exists.

        Args:
            declarations: ``{code: declared_type}`` for the expression.
            table_codes: The table codes the expression selects from.
            release_id: Release used to resolve those tables to modules.
        """
        module_vids = _module_vids_for(self.session, table_codes, release_id)
        if not module_vids:
            return
        for expression in self._co_scoped_parameter_expressions(module_vids):
            for code, other_type in self._declarations(expression).items():
                declared = declarations.get(code)
                if declared is not None and declared != other_type:
                    raise SemanticError(
                        "3-8",
                        parameter=code,
                        type_1=other_type,
                        type_2=declared,
                    )

    def _co_scoped_parameter_expressions(
        self, module_vids: frozenset[int]
    ) -> list[str]:
        """Persisted parameterised expressions sharing a module version.

        The marker match is whitespace-insensitive (see
        :func:`_whitespace_insensitive`) so a hand-written ``{ p_x}`` is still
        found. The ``LIKE`` filter guarantees a non-null expression (``LIKE``
        rejects NULL), so the cast to ``str`` is sound.
        """
        base = (
            self.session.query(OperationVersion.expression)
            .join(
                OperationScope,
                OperationVersion.operation_vid == OperationScope.operation_vid,
            )
            .join(
                OperationScopeComposition,
                OperationScope.operation_scope_id
                == OperationScopeComposition.operation_scope_id,
            )
            .filter(
                _whitespace_insensitive(OperationVersion.expression).like(
                    _PARAM_MARKER
                )
            )
            .distinct()
        )
        rows = chunked_in(
            base, OperationScopeComposition.module_vid, module_vids
        )
        # Chunking the module_vid IN clause splits the query, so the
        # per-statement DISTINCT no longer dedups across chunks; collapse
        # repeated expressions here while preserving order.
        return list(
            dict.fromkeys(
                expression for (expression,) in cast("list[tuple[str]]", rows)
            )
        )

    def _declarations(self, expression: str) -> dict[str, str]:
        """Extract ``{code: declared_type}`` from one persisted expression.

        A malformed/legacy persisted expression that fails to parse is skipped
        rather than aborting validation of the current expression.
        """
        try:
            ast = self._syntax.parse(expression)
        except Exception:
            return {}
        decls: dict[str, str] = {}
        for ref in _walk_parameter_refs(ast):
            # Canonical names so the comparison matches ParameterInfo.
            # A simplified ``{pCode}`` reference in the persisted expression
            # carries no declared type, so it contributes nothing to the
            # cross-scope check and is skipped.
            if ref.param_type is None:
                continue
            decls.setdefault(ref.code, canonical_param_type(ref.param_type))
        return decls
