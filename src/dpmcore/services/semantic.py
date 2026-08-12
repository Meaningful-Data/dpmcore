"""Semantic validation service — requires a database session."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
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
from dpmcore.services._parameters import merge_parameters
from dpmcore.services.syntax import SyntaxService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@dataclass(frozen=True)
class ParameterInfo:
    """Declared metadata for a parameter referenced by an expression.

    This is the runtime-binding contract: dpmcore reports which parameters an
    expression needs (and their declared types/defaults); the downstream engine
    resolves and binds their values.

    ``is_set`` is a derived property (``Set`` prefix of the canonical
    ``declared_type``), not a stored field, so there is one source of truth for
    set-ness.
    """

    code: str
    declared_type: str
    default: Any = None

    @property
    def is_set(self) -> bool:
        """``True`` for the set variants.

        The canonical ``declared_type`` is ``SetNumber``/``SetItem``/…; no
        scalar type name starts with ``Set``, so the prefix is unambiguous.
        """
        return self.declared_type.startswith("Set")


@dataclass(frozen=True)
class SemanticResult:
    """Outcome of a semantic validation.

    When a ``precondition_expression`` is supplied, ``is_valid`` is the verdict
    for the **pair**: it is ``False`` if either the expression or its gate
    failed, because a row whose gate does not resolve is not evaluable. The
    gate's own independent verdict is ``precondition``; ``error_source`` says
    which half a failure belongs to — ``"expression"``, ``"precondition"``, or
    ``"both"`` — so attribution never needs string matching. ``error_message``
    names *every* failure that occurred, each from the gate prefixed
    ``"Precondition: "``, and ``warning`` merges both halves' warnings the same
    way, so a caller reading only the outer result never misses half the story.
    ``error_code`` holds a single value: the expression's when it failed,
    otherwise the gate's.

    ``precondition`` is ``None`` exactly when the caller supplied no gate —
    never as a way of signalling that one failed. On that nested result
    ``error_source`` is ``"precondition"`` whenever it failed, since it
    describes the gate alone.
    """

    is_valid: bool
    error_message: Optional[str]
    error_code: Optional[str]
    expression: str
    results: Optional[Any] = None
    warning: Optional[str] = None
    parameters: tuple[ParameterInfo, ...] = field(default_factory=tuple)
    # Populated only when a precondition expression was supplied.
    precondition: Optional["SemanticResult"] = None
    # Which input a failure belongs to: "expression", "precondition", or
    # "both". Set whenever ``is_valid`` is False, matching ``ScopeResult``.
    error_source: Optional[str] = None


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
        declared = canonical_param_type(node.param_type)
        existing = seen.get(node.code)
        if existing is None:
            seen[node.code] = ParameterInfo(
                code=node.code,
                declared_type=declared,
                default=parameter_default_value(node.default),
            )
        elif existing.declared_type != declared:
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


def _as_gate_verdict(result: SemanticResult) -> SemanticResult:
    """Stamp a gate's own verdict with the half it describes.

    A standalone validation attributes its failure to ``"expression"``,
    because that is the only half it knows about. Nested under
    ``SemanticResult.precondition`` that reads as a claim about the *main*
    expression, so the gate's verdict is restamped: on the nested result the
    failing half is always the precondition.
    """
    if result.is_valid:
        return result
    return replace(result, error_source="precondition")


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
        *,
        precondition_expression: Optional[str] = None,
    ) -> SemanticResult:
        """Full semantic validation of *expression* and its optional gate.

        Returns a :class:`SemanticResult` — never raises on validation
        failure.

        A referenced parameter's declared type is also checked against
        co-scoped operations already in the database (raising ``3-8`` on a
        clash). This lookup only runs when the expression actually references a
        parameter and is scoped in SQL to co-located operations, so it adds no
        overhead to a parameter-free database.

        When ``precondition_expression`` is supplied, both halves are validated
        against the same release, resolved once, and ``is_valid`` becomes the
        verdict for the **pair** — ``False`` if either half failed, since a row
        whose gate does not resolve is not evaluable. ``precondition`` carries
        the gate's own verdict and ``error_source`` names the failing half.
        Two checks then apply that a single expression never sees:

        * The gate is validated *as a gate*, so its result must be a boolean
          (``2-1``). A numeric selection is a valid expression but not a valid
          precondition.
        * Parameter declarations are cross-checked across the halves
          (``3-8``). A gate co-executes with its expression, so a parameter
          bound across them must declare one type.

        The halves are evaluated gate-first, so the per-call state this service
        publishes (``ast``, ``oc_data``, ``oc_tables``, ``oc_parameters``)
        describes the *main* expression when the call returns — what existing
        consumers of this method already rely on.

        Args:
            expression: The DPM-XL expression to validate.
            release_id: Optional release ID filter. When neither this nor
                ``release_code`` is given, defaults to the latest release.
            release_code: Optional release code (mutually exclusive
                with ``release_id``).
            precondition_expression: Optional DPM-XL gate expression.
                Keyword-only, and appended after the pre-existing arguments,
                so ``validate(expr, 5)`` still means ``release_id=5``. When
                ``None``, the result is exactly as before this argument
                existed: ``precondition`` is ``None`` and ``is_valid``
                describes ``expression`` alone.
        """
        try:
            resolved = self._resolve_release(release_id, release_code)
        except SemanticError as exc:
            code = getattr(exc, "code", None)
            return self._resolution_failure(
                expression, precondition_expression, exc, code
            )
        except Exception as exc:
            return self._resolution_failure(
                expression, precondition_expression, exc, "UNKNOWN"
            )

        if precondition_expression is None:
            return self._validate_resolved(expression, resolved)

        # Gate first, main expression last: the trailing ``self.ast`` /
        # ``self.oc_*`` must describe the main expression (see docstring).
        precondition = _as_gate_verdict(
            self._validate_resolved(
                precondition_expression, resolved, as_precondition=True
            )
        )
        main = self._validate_resolved(expression, resolved)
        return self._combine(main, self._cross_check(main, precondition))

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _resolve_release(
        self,
        release_id: Optional[int],
        release_code: Optional[str],
    ) -> Optional[int]:
        """Resolve the release once, raising on an unknown or absent one."""
        resolved = resolve_release_id(
            self.session,
            release_id=release_id,
            release_code=release_code,
        )
        # Default to the latest release when none is specified, matching
        # the DPM-XL engine convention (see scopes_calculator). This keeps
        # the co-scope parameter check release-scoped instead of spanning
        # every release. ``None`` only survives on an empty schema.
        if resolved is None:
            resolved = ModuleVersionQuery.get_last_release(self.session)
        if resolved is not None:
            exists = (
                self.session.query(Release.release_id)
                .filter(Release.release_id == resolved)
                .first()
            )
            if exists is None:
                raise SemanticError("1-21", release_id=resolved)
        return resolved

    def _validate_resolved(
        self,
        expression: str,
        release_id: Optional[int],
        *,
        as_precondition: bool = False,
    ) -> SemanticResult:
        """Validate *expression* against an already-resolved release.

        Args:
            expression: The DPM-XL expression to validate.
            release_id: Release the expression is checked against.
            as_precondition: When ``True``, the expression is treated as a
                precondition gate, so the analyzer enforces a boolean result
                (``2-1``) even though the expression itself contains no
                precondition item.
        """
        try:
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
                analyzer.preconditions = as_precondition or oc.preconditions
                analyzer.session = self.session
                analyzer.release_id = release_id

                results = analyzer.visit(ast)

            if self.oc_parameters:
                self._check_persisted_scope(
                    {p.code: p.declared_type for p in self.oc_parameters},
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
            return self._failure(expression, exc, getattr(exc, "code", None))
        except Exception as exc:
            return self._failure(expression, exc, "UNKNOWN")

    def _failure(
        self,
        expression: str,
        exc: Exception,
        error_code: Optional[str],
    ) -> SemanticResult:
        """Clear the published per-call state and build a failing result.

        ``ast`` is cleared alongside ``oc_*``; leaving the previous call's AST
        readable after a failure invited consumers to act on stale state.
        """
        self.ast = None
        self.oc_data = None
        self.oc_tables = None
        self.oc_parameters = None
        return SemanticResult(
            is_valid=False,
            error_message=str(exc),
            error_code=error_code,
            expression=expression,
            error_source="expression",
        )

    def _resolution_failure(
        self,
        expression: str,
        precondition_expression: Optional[str],
        exc: Exception,
        error_code: Optional[str],
    ) -> SemanticResult:
        """Report a release-resolution failure across every supplied half.

        The failure belongs to neither half — no expression was even parsed —
        so it is attributed to ``"expression"`` and mirrored onto the gate's
        own verdict when one was supplied.
        """
        failure = self._failure(expression, exc, error_code)
        if precondition_expression is None:
            return failure
        return replace(
            failure,
            error_source="expression",
            precondition=_as_gate_verdict(
                self._failure(precondition_expression, exc, error_code)
            ),
        )

    @staticmethod
    def _cross_check(
        main: SemanticResult, precondition: SemanticResult
    ) -> SemanticResult:
        """Reject a parameter declared with different types across the halves.

        A gate co-executes with its expression, so a parameter bound across the
        pair must declare one type. The clash is reported on the *precondition*
        half — it carries the second, conflicting declaration — leaving the
        main expression's own verdict intact.
        """
        if not (
            main.is_valid
            and precondition.is_valid
            and main.parameters
            and precondition.parameters
        ):
            return precondition
        accumulated: dict[str, ParameterInfo] = {}
        try:
            merge_parameters(accumulated, main.parameters)
            merge_parameters(accumulated, precondition.parameters)
        except SemanticError as exc:
            return SemanticResult(
                is_valid=False,
                error_message=str(exc),
                error_code=getattr(exc, "code", None),
                expression=precondition.expression,
                error_source="precondition",
            )
        return precondition

    @staticmethod
    def _combine(
        main: SemanticResult, precondition: SemanticResult
    ) -> SemanticResult:
        """Fold the gate's verdict into the pair's result.

        Every summary field on the outer result describes the *pair*, so a
        caller reading only that result never misses half the story:
        ``is_valid`` is pair-wide, warnings from both halves are merged, and
        every failure that occurred is named — so ``is_valid=False`` never
        arrives without a complete explanation. The ``"Precondition: "`` prefix
        matches ``ScopeResult``'s, so both services read the same way.
        """
        warning = main.warning
        if precondition.warning:
            gate_warning = f"Precondition: {precondition.warning}"
            # Newline-joined, matching WarningCollector.get_combined_warning.
            warning = f"{warning}\n{gate_warning}" if warning else gate_warning
        combined = replace(main, warning=warning, precondition=precondition)
        gate_message = f"Precondition: {precondition.error_message}"

        if main.is_valid and precondition.is_valid:
            return combined
        if main.is_valid:
            return replace(
                combined,
                is_valid=False,
                error_message=gate_message,
                error_code=precondition.error_code,
                error_source="precondition",
            )
        if precondition.is_valid:
            return replace(combined, error_source="expression")
        # Both halves failed. Naming only the expression would read as "the
        # gate is fine", costing the caller a round trip to discover it is not,
        # so both messages are surfaced and ``error_source`` says ``"both"``.
        # ``error_code`` holds a single value, so it stays the expression's.
        return replace(
            combined,
            error_message=f"{main.error_message}\n{gate_message}",
            error_source="both",
        )

    def is_valid(
        self,
        expression: str,
        release_id: Optional[int] = None,
        release_code: Optional[str] = None,
        *,
        precondition_expression: Optional[str] = None,
    ) -> bool:
        """Quick boolean check, pair-wide when a gate is supplied."""
        return self.validate(
            expression,
            precondition_expression=precondition_expression,
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
            decls.setdefault(ref.code, canonical_param_type(ref.param_type))
        return decls
