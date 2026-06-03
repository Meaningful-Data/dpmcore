"""Semantic validation service — requires a database session."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

from dpmcore.dpm_xl.ast.nodes import parameter_default_value
from dpmcore.dpm_xl.ast.operands import OperandsChecking
from dpmcore.dpm_xl.semantic_analyzer import InputAnalyzer
from dpmcore.dpm_xl.utils.filters import resolve_release_id
from dpmcore.dpm_xl.warning_collector import collect_warnings
from dpmcore.errors import SemanticError
from dpmcore.orm.infrastructure import Release
from dpmcore.services.parameter_scope import ParameterScopeIndex
from dpmcore.services.syntax import SyntaxService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@dataclass(frozen=True)
class ParameterInfo:
    """Declared metadata for a parameter referenced by an expression.

    This is the runtime-binding contract: dpmcore reports which parameters an
    expression needs (and their declared types/defaults); the downstream engine
    resolves and binds their values.
    """

    code: str
    declared_type: str
    is_set: bool
    default: Any = None


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
        existing = seen.get(node.code)
        if existing is None:
            seen[node.code] = ParameterInfo(
                code=node.code,
                declared_type=node.param_type,
                is_set=node.is_set,
                default=parameter_default_value(node.default),
            )
        elif existing.declared_type != node.param_type:
            raise SemanticError(
                "3-8",
                parameter=node.code,
                type_1=existing.declared_type,
                type_2=node.param_type,
            )
    return tuple(seen.values())


class SemanticService:
    """Validate DPM-XL expressions against the data dictionary.

    Args:
        session: An open SQLAlchemy session bound to a DPM database.
    """

    def __init__(self, session: "Session") -> None:
        """Build the service bound to ``session``."""
        self.session = session
        self._syntax = SyntaxService()
        self._scope_index = ParameterScopeIndex(session)
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
        check_scope: bool = True,
    ) -> SemanticResult:
        """Full semantic validation of *expression*.

        Returns a :class:`SemanticResult` — never raises on validation
        failure.

        Args:
            expression: The DPM-XL expression to validate.
            release_id: Optional release ID filter.
            release_code: Optional release semver code (mutually exclusive
                with ``release_id``).
            check_scope: When True (default), a referenced parameter's
                declared type is also checked against co-scoped operations
                already in the database (raising ``3-8`` on a clash). Bulk
                paths that enforce consistency over their own batch (e.g.
                script generation) pass ``False`` to skip the DB lookup.
        """
        try:
            release_id = resolve_release_id(
                self.session,
                release_id=release_id,
                release_code=release_code,
            )
            if release_id is not None:
                exists = (
                    self.session.query(Release.release_id)
                    .filter(Release.release_id == release_id)
                    .first()
                )
                if exists is None:
                    raise SemanticError("1-21", release_id=release_id)

            ast = self._syntax.parse(expression)
            self.ast = ast

            with collect_warnings() as wc:
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

            if check_scope and self.oc_parameters:
                self._scope_index.check(
                    {p.code: p.declared_type for p in self.oc_parameters},
                    self._scope_index.module_vids_for(
                        list(oc.tables.keys()) if oc.tables else [],
                        release_id,
                    ),
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
