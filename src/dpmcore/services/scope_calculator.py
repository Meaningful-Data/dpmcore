"""Operation scope calculation service."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    List,
    Optional,
    Set,
)

from dpmcore.dpm_xl.ast.operands import OperandsChecking
from dpmcore.dpm_xl.utils.scopes_calculator import OperationScopeService
from dpmcore.errors import SemanticError
from dpmcore.orm.infrastructure import Release
from dpmcore.orm.packaging import ModuleVersion
from dpmcore.services.syntax import SyntaxService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class ScopeResult:
    """Outcome of a scope calculation."""

    existing_scopes: list = field(default_factory=list)
    new_scopes: list = field(default_factory=list)
    total_scopes: int = 0
    is_cross_module: bool = False
    module_versions: List[int] = field(default_factory=list)
    has_error: bool = False
    error_message: Optional[str] = None


class ScopeCalculatorService:
    """Calculate operation scopes for DPM-XL expressions.

    Determines which module versions are involved in an operation
    based on table references and precondition items.

    Args:
        session: An open SQLAlchemy session.
    """

    def __init__(self, session: "Session") -> None:  # noqa: D107
        self.session = session
        self._syntax = SyntaxService()

    def _check_release_exists(self, release_id: Optional[int]) -> None:
        """Raise SemanticError if *release_id* does not exist."""
        if release_id is None:
            return
        exists = (
            self.session.query(Release.release_id)
            .filter(Release.release_id == release_id)
            .first()
        )
        if exists is None:
            raise SemanticError("1-21", release_id=release_id)

    @staticmethod
    def _compute_cross_module(all_scopes: list) -> bool:
        """Return True if any scope spans more than one module."""
        return any(
            len(
                {
                    c.module_vid
                    for c in getattr(
                        s, "operation_scope_compositions", []
                    )
                }
            )
            > 1
            for s in all_scopes
        )

    def calculate_from_expression(
        self,
        expression: str,
        operation_version_id: int,
        release_id: Optional[int] = None,
        severity: Optional[str] = None,
    ) -> ScopeResult:
        """Calculate scopes for *expression*.

        Parses the expression, runs OperandsChecking to extract table
        version IDs and precondition items, then delegates to
        :class:`OperationScopeService`.
        """
        try:
            self._check_release_exists(release_id)
            ast = self._syntax.parse(expression)
            oc = OperandsChecking(
                session=self.session,
                expression=expression,
                ast=ast,
                release_id=release_id,
            )

            table_vids = list(oc.tables.keys()) if oc.tables else []
            precondition_items = oc.preconditions or []

            scope_svc = OperationScopeService(
                operation_version_id=operation_version_id,
                session=self.session,
            )
            existing, new = scope_svc.calculate_operation_scope(
                tables_vids=table_vids,
                precondition_items=precondition_items,
                release_id=release_id,
            )

            all_scopes = existing + new
            mvids: List[int] = []
            for scope in all_scopes:
                for comp in getattr(
                    scope, "operation_scope_compositions", []
                ):
                    vid = comp.module_vid
                    if vid not in mvids:
                        mvids.append(vid)

            return ScopeResult(
                existing_scopes=existing,
                new_scopes=new,
                total_scopes=len(all_scopes),
                is_cross_module=self._compute_cross_module(
                    all_scopes
                ),
                module_versions=mvids,
            )

        except (SemanticError, Exception) as exc:
            return ScopeResult(
                has_error=True,
                error_message=str(exc),
            )

    def calculate_from_tables(
        self,
        operation_version_id: int,
        table_vids: List[int],
        precondition_items: Optional[List[str]] = None,
        release_id: Optional[int] = None,
        table_codes: Optional[List[str]] = None,
    ) -> ScopeResult:
        """Calculate scopes directly from table version IDs."""
        try:
            self._check_release_exists(release_id)
            scope_svc = OperationScopeService(
                operation_version_id=operation_version_id,
                session=self.session,
            )
            existing, new = scope_svc.calculate_operation_scope(
                tables_vids=table_vids,
                precondition_items=precondition_items or [],
                release_id=release_id,
                table_codes=table_codes,
            )

            all_scopes = existing + new
            mvids: List[int] = []
            for scope in all_scopes:
                for comp in getattr(
                    scope, "operation_scope_compositions", []
                ):
                    vid = comp.module_vid
                    if vid not in mvids:
                        mvids.append(vid)

            return ScopeResult(
                existing_scopes=existing,
                new_scopes=new,
                total_scopes=len(all_scopes),
                is_cross_module=self._compute_cross_module(
                    all_scopes
                ),
                module_versions=mvids,
            )

        except Exception as exc:
            return ScopeResult(
                has_error=True,
                error_message=str(exc),
            )

    # ------------------------------------------------------------------ #
    # Cross-module dependency detection (Fix 2)
    # ------------------------------------------------------------------ #

    def filter_valid_dependency_modules(
        self,
        scope_result: ScopeResult,
        primary_module_vid: int,
    ) -> Set[int]:
        """Return module VIDs that co-occur with *primary_module_vid*.

        Only modules that actually appear alongside the primary module
        in a multi-module scope are valid cross-module partners.
        This filters out sibling modules that share tables but are
        not actual cross-module dependencies.
        """
        valid: Set[int] = set()
        all_scopes = (scope_result.existing_scopes or []) + (
            scope_result.new_scopes or []
        )
        for scope in all_scopes:
            scope_vids = {
                c.module_vid
                for c in getattr(
                    scope, "operation_scope_compositions", []
                )
            }
            if (
                primary_module_vid in scope_vids
                and len(scope_vids) > 1
            ):
                valid.update(scope_vids - {primary_module_vid})
        return valid

    def detect_cross_module_dependencies(
        self,
        scope_result: ScopeResult,
        primary_module_vid: int,
        operation_code: Optional[str] = None,
        release_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Build dependency information for a scope result.

        Returns a dict with:
        - ``intra_instance_validations``: operation codes for
          intra-module validations.
        - ``cross_instance_dependencies``: list of external module
          dependency dicts.
        - ``alternative_dependencies``: pairs of alternative modules.
        """
        is_cross = scope_result.is_cross_module

        if not is_cross or scope_result.has_error:
            alternative_deps: List[List[str]] = []
            if not scope_result.has_error:
                alternative_deps = (
                    self.detect_alternative_dependencies(
                        scope_results=[scope_result],
                        primary_module_vid=primary_module_vid,
                        release_id=release_id,
                    )
                )
            return {
                "intra_instance_validations": (
                    []
                    if is_cross or not operation_code
                    else [operation_code]
                ),
                "cross_instance_dependencies": [],
                "alternative_dependencies": alternative_deps,
            }

        valid_vids = self.filter_valid_dependency_modules(
            scope_result, primary_module_vid
        )
        if not valid_vids:
            return {
                "intra_instance_validations": (
                    [operation_code] if operation_code else []
                ),
                "cross_instance_dependencies": [],
                "alternative_dependencies": [],
            }

        # Build cross_instance_dependencies from valid external modules
        cross_deps: List[Dict[str, Any]] = []
        for vid in sorted(valid_vids):
            mv = (
                self.session.query(ModuleVersion)
                .filter(ModuleVersion.module_vid == vid)
                .first()
            )
            if not mv:
                continue

            uri = self._get_module_uri(
                module_vid=vid,
                release_id=release_id,
                mv=mv,
            )
            if not uri:
                continue

            module_entry: Dict[str, Any] = {"URI": uri}
            if mv.version_number:
                module_entry["module_version"] = (
                    mv.version_number
                )

            from_date = mv.from_reference_date
            to_date = mv.to_reference_date
            cross_deps.append(
                {
                    "modules": [module_entry],
                    "affected_operations": (
                        [operation_code]
                        if operation_code
                        else []
                    ),
                    "from_reference_date": (
                        str(from_date) if from_date else ""
                    ),
                    "to_reference_date": (
                        str(to_date) if to_date else ""
                    ),
                }
            )

        alternative_deps = self.detect_alternative_dependencies(
            scope_results=[scope_result],
            primary_module_vid=primary_module_vid,
            release_id=release_id,
        )

        return {
            "intra_instance_validations": [],
            "cross_instance_dependencies": cross_deps,
            "alternative_dependencies": alternative_deps,
        }

    # ------------------------------------------------------------------ #
    # Alternative dependency detection (Fix 3)
    # ------------------------------------------------------------------ #

    def detect_alternative_dependencies(
        self,
        scope_results: List[ScopeResult],
        primary_module_vid: int,
        release_id: Optional[int] = None,
    ) -> List[List[str]]:
        """Detect pairs of external modules that are alternatives.

        Two external modules are alternatives if they each appear as
        the sole external module alongside the primary module in
        separate scopes, but never co-exist in the same scope.

        Returns a list of ``[uri_a, uri_b]`` pairs (sorted).
        """
        single_ext_vids, all_ext_vid_sets = (
            self._collect_external_vid_sets(
                scope_results, primary_module_vid
            )
        )
        if len(single_ext_vids) < 2:
            return []

        alt_pairs = self._find_alternative_pairs(
            single_ext_vids, all_ext_vid_sets
        )
        if not alt_pairs:
            return []

        return self._map_pairs_to_uris(alt_pairs, release_id)

    @staticmethod
    def _collect_external_vid_sets(
        scope_results: List[ScopeResult],
        primary_module_vid: int,
    ) -> tuple:
        """Extract external VID sets from scopes."""
        single_ext_vids: Set[int] = set()
        all_ext_vid_sets: List[frozenset] = []

        for sr in scope_results:
            all_scopes = (sr.existing_scopes or []) + (
                sr.new_scopes or []
            )
            for scope in all_scopes:
                scope_vids = {
                    c.module_vid
                    for c in getattr(
                        scope,
                        "operation_scope_compositions",
                        [],
                    )
                }
                if (
                    primary_module_vid not in scope_vids
                    or len(scope_vids) < 2
                ):
                    continue
                ext_vids = frozenset(
                    scope_vids - {primary_module_vid}
                )
                all_ext_vid_sets.append(ext_vids)
                if len(ext_vids) == 1:
                    single_ext_vids.update(ext_vids)

        return single_ext_vids, all_ext_vid_sets

    @staticmethod
    def _find_alternative_pairs(
        single_ext_vids: Set[int],
        all_ext_vid_sets: List[frozenset],
    ) -> List[tuple]:
        """Find VID pairs that are sole-external and never co-occur."""
        co_occurring: Set[tuple] = set()
        for ext_set in all_ext_vid_sets:
            if len(ext_set) > 1:
                sorted_vids = sorted(ext_set)
                for i, v1 in enumerate(sorted_vids):
                    for v2 in sorted_vids[i + 1 :]:
                        co_occurring.add((v1, v2))

        pairs = []
        sorted_singles = sorted(single_ext_vids)
        for i, v1 in enumerate(sorted_singles):
            for v2 in sorted_singles[i + 1 :]:
                pair = (v1, v2) if v1 < v2 else (v2, v1)
                if pair not in co_occurring:
                    pairs.append(pair)
        return pairs

    def _map_pairs_to_uris(
        self,
        pairs: List[tuple],
        release_id: Optional[int],
    ) -> List[List[str]]:
        """Resolve VID pairs to sorted URI pairs."""
        needed: Set[int] = set()
        for v1, v2 in pairs:
            needed.add(v1)
            needed.add(v2)

        vid_to_uri: Dict[int, str] = {}
        for vid in needed:
            uri = self._get_module_uri(
                module_vid=vid, release_id=release_id
            )
            if uri:
                vid_to_uri[vid] = uri

        result: List[List[str]] = []
        for v1, v2 in pairs:
            uri1 = vid_to_uri.get(v1)
            uri2 = vid_to_uri.get(v2)
            if uri1 and uri2:
                result.append(sorted([uri1, uri2]))

        return result

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _get_module_uri(
        self,
        module_vid: int,
        release_id: Optional[int] = None,
        mv: Optional[Any] = None,
    ) -> Optional[str]:
        """Resolve a module VID to its EBA taxonomy URI.

        Constructs a URI of the form::

            http://www.eba.europa.eu/eu/fr/xbrl/crr/fws/
            {framework}/{release}/mod/{module}

        When *mv* is supplied the DB lookup is skipped.
        """
        try:
            if mv is None:
                mv = (
                    self.session.query(ModuleVersion)
                    .filter(
                        ModuleVersion.module_vid
                        == module_vid
                    )
                    .first()
                )
            if not mv or not mv.module:
                return None

            framework = mv.module.framework
            if not framework or not framework.code:
                return None

            module_code = mv.code
            if not module_code:
                return None

            effective_release_id = (
                release_id or mv.start_release_id
            )
            release_row = (
                self.session.query(Release.code)
                .filter(
                    Release.release_id
                    == effective_release_id
                )
                .first()
            )
            if not release_row or not release_row.code:
                return None

            return (
                "http://www.eba.europa.eu/eu/fr/xbrl/crr"
                "/fws/"
                f"{framework.code.lower()}/"
                f"{release_row.code}/mod/"
                f"{module_code.lower()}"
            )

        except Exception as exc:
            logger.warning(
                "Failed to resolve URI for module VID"
                " %s: %s",
                module_vid,
                exc,
            )
            return None
