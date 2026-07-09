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
    Tuple,
)

from dpmcore.dpm_xl.ast.operands import OperandsChecking
from dpmcore.dpm_xl.utils.filters import resolve_release_id
from dpmcore.dpm_xl.utils.scopes_calculator import (
    OperationScopeService,
)
from dpmcore.errors import SemanticError
from dpmcore.orm.glossary import Property
from dpmcore.orm.infrastructure import DataType, Release
from dpmcore.orm.packaging import (
    ModuleVersion,
    ModuleVersionComposition,
)
from dpmcore.orm.query_utils import chunked_in
from dpmcore.orm.rendering import (
    TableVersion,
    TableVersionCell,
)
from dpmcore.orm.variables import Variable, VariableVersion
from dpmcore.services._open_keys import (
    get_open_keys_for_tables as _get_open_keys_for_tables,
)
from dpmcore.services.syntax import SyntaxService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class ScopeResult:
    """Outcome of a scope calculation."""

    scopes: list[Any] = field(default_factory=list)
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

    def __init__(self, session: "Session") -> None:
        """Build the service bound to ``session``."""
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
    def _compute_cross_module(scopes: list[Any]) -> bool:
        """Return True if any scope spans more than one module."""
        return any(
            len(
                {
                    c.module_vid
                    for c in getattr(s, "operation_scope_compositions", [])
                }
            )
            > 1
            for s in scopes
        )

    def calculate_from_expression(
        self,
        expression: str,
        release_id: Optional[int] = None,
        precondition_items: Optional[List[str]] = None,
        release_code: Optional[str] = None,
    ) -> ScopeResult:
        """Calculate scopes for *expression*.

        Parses the expression, runs OperandsChecking to extract table
        codes, then delegates to :class:`OperationScopeService`.
        ``precondition_items`` is the list of precondition variable
        codes that gate the validation; pass ``None`` or ``[]`` if
        the validation has no preconditions.
        """
        try:
            release_id = resolve_release_id(
                self.session,
                release_id=release_id,
                release_code=release_code,
            )
            self._check_release_exists(release_id)
            ast = self._syntax.parse(expression)
            oc = OperandsChecking(
                session=self.session,
                expression=expression,
                ast=ast,
                release_id=release_id,
            )

            table_codes: list[str] = (
                list(oc.tables.keys()) if oc.tables else []
            )

            scope_svc = OperationScopeService(session=self.session)
            scopes, _ = scope_svc.calculate_operation_scope(
                tables_vids=[],
                precondition_items=precondition_items or [],
                release_id=release_id,
                table_codes=table_codes,
            )

            mvids: List[int] = []
            for scope in scopes:
                for comp in getattr(scope, "operation_scope_compositions", []):
                    vid = comp.module_vid
                    if vid not in mvids:
                        mvids.append(vid)

            return ScopeResult(
                scopes=scopes,
                total_scopes=len(scopes),
                is_cross_module=self._compute_cross_module(scopes),
                module_versions=mvids,
            )

        except (SemanticError, Exception) as exc:
            return ScopeResult(
                has_error=True,
                error_message=str(exc),
            )

    def calculate_from_tables(
        self,
        table_vids: List[int],
        precondition_items: Optional[List[str]] = None,
        release_id: Optional[int] = None,
        table_codes: Optional[List[str]] = None,
        release_code: Optional[str] = None,
    ) -> ScopeResult:
        """Calculate scopes directly from table version IDs."""
        try:
            release_id = resolve_release_id(
                self.session,
                release_id=release_id,
                release_code=release_code,
            )
            self._check_release_exists(release_id)
            scope_svc = OperationScopeService(session=self.session)
            scopes, _ = scope_svc.calculate_operation_scope(
                tables_vids=table_vids,
                precondition_items=precondition_items or [],
                release_id=release_id,
                table_codes=table_codes,
            )

            mvids: List[int] = []
            for scope in scopes:
                for comp in getattr(scope, "operation_scope_compositions", []):
                    vid = comp.module_vid
                    if vid not in mvids:
                        mvids.append(vid)

            return ScopeResult(
                scopes=scopes,
                total_scopes=len(scopes),
                is_cross_module=self._compute_cross_module(scopes),
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
        for scope in scope_result.scopes or []:
            scope_vids = {
                c.module_vid
                for c in getattr(scope, "operation_scope_compositions", [])
            }
            if primary_module_vid in scope_vids and len(scope_vids) > 1:
                valid.update(scope_vids - {primary_module_vid})
        return valid

    def detect_cross_module_dependencies(
        self,
        scope_result: ScopeResult,
        primary_module_vid: int,
        operation_code: Optional[str] = None,
        release_id: Optional[int] = None,
        time_shifts: Optional[Dict[str, str]] = None,
        compute_alternative_deps: bool = True,
        release_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build dependency information for a scope result.

        Args:
            scope_result: The computed scope result.
            primary_module_vid: VID of the primary module.
            operation_code: Current operation code (if any).
            release_id: Optional release filter.
            time_shifts: Optional mapping of table codes to
                ref-period strings (e.g. ``{"C_01.00": "T-1Q"}``).
                Tables not present default to ``"T"``.
            compute_alternative_deps: When True (default) the returned
                ``alternative_dependencies`` is populated from this
                single ``scope_result``. Aggregating callers that
                compute alternatives across many scope results should
                pass ``False`` to avoid the per-call work.
            release_code: Optional release code; resolved to
                ``release_id`` via :class:`Release.code`. Mutually
                exclusive with ``release_id``.

        Returns a dict with:
        - ``intra_instance_validations``
        - ``cross_instance_dependencies``
        - ``alternative_dependencies``
        - ``dependency_modules``
        """
        release_id = resolve_release_id(
            self.session, release_id=release_id, release_code=release_code
        )
        empty_result: Dict[str, Any] = {
            "intra_instance_validations": [],
            "cross_instance_dependencies": [],
            "alternative_dependencies": [],
            "dependency_modules": {},
        }
        is_cross = scope_result.is_cross_module
        ts = time_shifts or {}

        # Issue #120: when the primary module can evaluate the operation
        # on its own (it appears as a single-module scope), prefer the
        # intra-instance reading even if cross-instance scopes also exist
        # for other modules. Only when the primary appears *solely* in
        # multi-module scopes is it a genuine cross-instance dependency.
        primary_has_intra = not scope_result.has_error and any(
            {
                c.module_vid
                for c in getattr(s, "operation_scope_compositions", [])
            }
            == {primary_module_vid}
            for s in scope_result.scopes or []
        )

        if scope_result.has_error or not is_cross or primary_has_intra:
            alternative_deps: List[List[str]] = []
            if compute_alternative_deps and not scope_result.has_error:
                alternative_deps = self.detect_alternative_dependencies(
                    scope_results=[scope_result],
                    primary_module_vid=primary_module_vid,
                    release_id=release_id,
                )
            return {
                **empty_result,
                "intra_instance_validations": (
                    [operation_code]
                    if operation_code and (not is_cross or primary_has_intra)
                    else []
                ),
                "alternative_dependencies": alternative_deps,
            }

        valid_vids = self.filter_valid_dependency_modules(
            scope_result, primary_module_vid
        )
        if not valid_vids:
            # Scopes exist, but the primary module hosts none of the
            # referenced tables and so participates in none of them: it is
            # neither the intra-instance owner nor a cross-instance partner.
            return {**empty_result}

        # Build cross_instance_dependencies and dependency_modules
        cross_deps: List[Dict[str, Any]] = []
        dep_modules: Dict[str, Any] = {}

        sorted_vids = sorted(valid_vids)
        mv_rows = chunked_in(
            self.session.query(ModuleVersion),
            ModuleVersion.module_vid,
            sorted_vids,
        )
        mv_by_vid = {mv.module_vid: mv for mv in mv_rows}

        for vid in sorted_vids:
            mv = mv_by_vid.get(vid)
            if not mv:
                continue
            entry = self._build_dependency_entry(
                vid=vid,
                mv=mv,
                release_id=release_id,
                ts=ts,
                operation_code=operation_code,
            )
            if entry is None:
                continue
            cross_dep, uri, dep_module = entry
            cross_deps.append(cross_dep)
            dep_modules[uri] = dep_module

        alternative_deps = (
            self.detect_alternative_dependencies(
                scope_results=[scope_result],
                primary_module_vid=primary_module_vid,
                release_id=release_id,
            )
            if compute_alternative_deps
            else []
        )

        return {
            "intra_instance_validations": [],
            "cross_instance_dependencies": cross_deps,
            "alternative_dependencies": alternative_deps,
            "dependency_modules": dep_modules,
        }

    def _build_dependency_entry(
        self,
        vid: int,
        mv: Any,
        release_id: Optional[int],
        ts: Dict[str, str],
        operation_code: Optional[str],
    ) -> Optional[Tuple[Dict[str, Any], str, Dict[str, Any]]]:
        """Build a single (cross_dep, uri, dependency_module) triple.

        Returns ``None`` when the module has no resolvable URI or
        when every one of its tables is variable-less (and therefore
        dropped, since the engine schema requires
        ``minProperties: 1`` on each table's variables map).
        """
        uri = self._get_module_uri(module_vid=vid, mv=mv)
        if not uri:
            return None

        tables_dict_full = self._get_module_tables(vid, release_id=release_id)
        tables_dict = {
            tcode: tdata
            for tcode, tdata in tables_dict_full.items()
            if tdata.get("variables")
        }
        if not tables_dict:
            return None

        ref_period = "T"
        for tbl_code in tables_dict:
            rp = ts.get(tbl_code)
            if rp and rp != "T":
                ref_period = rp

        module_entry: Dict[str, Any] = {
            "URI": uri,
            "ref_period": ref_period,
        }
        if mv.version_number:
            module_entry["module_version"] = mv.version_number

        from_date = mv.from_reference_date
        to_date = mv.to_reference_date
        cross_dep = {
            "modules": [module_entry],
            "affected_operations": (
                [operation_code] if operation_code else []
            ),
            "from_reference_date": (str(from_date) if from_date else ""),
            "to_reference_date": (str(to_date) if to_date else ""),
        }
        dep_module = {
            "tables": tables_dict,
            "variables": {
                k: v
                for tbl in tables_dict.values()
                for k, v in tbl.get("variables", {}).items()
            },
        }
        return cross_dep, uri, dep_module

    # ------------------------------------------------------------------ #
    # Alternative dependency detection (Fix 3)
    # ------------------------------------------------------------------ #

    def detect_alternative_dependencies(
        self,
        scope_results: List[ScopeResult],
        primary_module_vid: int,
        release_id: Optional[int] = None,
        release_code: Optional[str] = None,
    ) -> List[List[str]]:
        """Detect pairs of external modules that are alternatives.

        Two external modules are alternatives if they each appear as
        the sole external module alongside the primary module in
        separate scopes, but never co-exist in the same scope.

        Returns a list of ``[uri_a, uri_b]`` pairs (sorted).
        """
        # Validate the release inputs (rejects an unknown code, or both
        # arguments at once). The resolved id is not threaded further:
        # each module version's URI roots at its own start release, not
        # the report release.
        resolve_release_id(
            self.session, release_id=release_id, release_code=release_code
        )
        single_ext_vids, all_ext_vid_sets = self._collect_external_vid_sets(
            scope_results, primary_module_vid
        )
        if len(single_ext_vids) < 2:
            return []

        alt_pairs = self._find_alternative_pairs(
            single_ext_vids, all_ext_vid_sets
        )
        if not alt_pairs:
            return []

        return self._map_pairs_to_uris(alt_pairs)

    @staticmethod
    def _collect_external_vid_sets(
        scope_results: List[ScopeResult],
        primary_module_vid: int,
    ) -> tuple[Set[int], List[frozenset[int]]]:
        """Extract external VID sets from scopes."""
        single_ext_vids: Set[int] = set()
        all_ext_vid_sets: List[frozenset[int]] = []

        for sr in scope_results:
            for scope in sr.scopes or []:
                scope_vids = {
                    c.module_vid
                    for c in getattr(
                        scope,
                        "operation_scope_compositions",
                        [],
                    )
                }
                if primary_module_vid not in scope_vids or len(scope_vids) < 2:
                    continue
                ext_vids = frozenset(scope_vids - {primary_module_vid})
                all_ext_vid_sets.append(ext_vids)
                if len(ext_vids) == 1:
                    single_ext_vids.update(ext_vids)

        return single_ext_vids, all_ext_vid_sets

    @staticmethod
    def _find_alternative_pairs(
        single_ext_vids: Set[int],
        all_ext_vid_sets: List[frozenset[int]],
    ) -> List[tuple[int, int]]:
        """Find VID pairs that are sole-external and never co-occur."""
        co_occurring: Set[tuple[int, int]] = set()
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
        pairs: List[tuple[int, int]],
    ) -> List[List[str]]:
        """Resolve VID pairs to sorted URI pairs."""
        needed: Set[int] = set()
        for v1, v2 in pairs:
            needed.add(v1)
            needed.add(v2)

        mv_by_vid: Dict[int, Any] = {}
        if needed:
            mv_rows = chunked_in(
                self.session.query(ModuleVersion),
                ModuleVersion.module_vid,
                needed,
            )
            mv_by_vid = {mv.module_vid: mv for mv in mv_rows}

        vid_to_uri: Dict[int, str] = {}
        for vid in needed:
            uri = self._get_module_uri(
                module_vid=vid,
                mv=mv_by_vid.get(vid),
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

    def _get_module_tables(
        self,
        module_vid: int,
        release_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Return tables for a module with their variables and open keys.

        Returns::

            {table_code: {"variables": {var_id: type_code},
                          "open_keys": {property_code: data_type_code}}}

        ``release_id`` filters the open-keys query by release window.
        """
        # Get table codes + VIDs for this module
        tv_rows = (
            self.session.query(
                TableVersion.code,
                TableVersion.table_vid,
            )
            .join(
                ModuleVersionComposition,
                TableVersion.table_vid == ModuleVersionComposition.table_vid,
            )
            .filter(ModuleVersionComposition.module_vid == module_vid)
            .all()
        )

        table_vids = [r.table_vid for r in tv_rows if r.table_vid]
        vid_to_code = {r.table_vid: r.code for r in tv_rows if r.code}

        # Batch-fetch variables for all tables at once
        variables_by_tvid: Dict[int, Dict[str, str]] = {
            tvid: {} for tvid in table_vids
        }
        if table_vids:
            var_base = (
                self.session.query(
                    TableVersionCell.table_vid,
                    Variable.variable_id,
                    DataType.code,
                )
                .select_from(TableVersionCell)
                .join(
                    VariableVersion,
                    TableVersionCell.variable_vid
                    == VariableVersion.variable_vid,
                )
                .join(
                    Variable,
                    VariableVersion.variable_id == Variable.variable_id,
                )
                .join(
                    Property,
                    VariableVersion.property_id == Property.property_id,
                )
                .join(
                    DataType,
                    Property.data_type_id == DataType.data_type_id,
                )
                .distinct()
            )
            var_rows = chunked_in(
                var_base, TableVersionCell.table_vid, table_vids
            )
            for row in var_rows:
                tvid = row[0]
                var_id = str(row[1])
                type_code = row[2] or ""
                if tvid in variables_by_tvid:
                    variables_by_tvid[tvid][var_id] = type_code

        # Open keys per table_code
        open_keys_by_code = _get_open_keys_for_tables(
            self.session,
            list(vid_to_code.values()),
            release_id=release_id,
        )

        tables: Dict[str, Any] = {}
        for tvid, code in vid_to_code.items():
            tables[code] = {
                "variables": variables_by_tvid.get(tvid, {}),
                "open_keys": open_keys_by_code.get(code, {}),
            }
        return tables

    def _get_module_uri(
        self,
        module_vid: int,
        mv: Optional[Any] = None,
    ) -> Optional[str]:
        """Resolve a module VID to its EBA taxonomy URI.

        The URI's release segment always comes from the release in which
        the module version was introduced (its start release), resolved
        via :meth:`_resolve_uri_release_id`. A module version's taxonomy
        is published under that release, so an unchanged module keeps its
        original release segment even inside a later report: e.g. an
        unchanged ``ae`` stays at ``.../ae/4.2/mod/ae`` in a 4.2.1 report,
        because no ``ae`` taxonomy exists at 4.2.1. The report release is
        deliberately not an input: it never sets the release segment, and
        it would not pick the module version either — the lookup filters
        by ``module_vid`` alone.

        Resolution order (in :meth:`_resolve_uri_release_id`): the static
        CSV mapping by ``(module_code, version_number)`` first; on a miss,
        the module version's ``start_release_id``.

        When *mv* is supplied the initial DB lookup is skipped.
        """
        try:
            if mv is None:
                mv = (
                    self.session.query(ModuleVersion)
                    .filter(ModuleVersion.module_vid == module_vid)
                    .first()
                )
            if not mv or not mv.module:
                return None

            module_code = mv.code
            if not module_code:
                return None

            framework = mv.module.framework
            if not framework or not framework.code:
                return None

            csv_or_release_id = self._resolve_uri_release_id(mv, module_code)
            if isinstance(csv_or_release_id, str):
                return csv_or_release_id  # CSV hit (already final URI).
            if csv_or_release_id is None:
                return None

            release_row = (
                self.session.query(Release.code)
                .filter(Release.release_id == csv_or_release_id)
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
                "Failed to resolve URI for module VID %s: %s",
                module_vid,
                exc,
            )
            return None

    @staticmethod
    def _resolve_uri_release_id(
        mv: Any,
        module_code: str,
    ) -> Optional[Any]:
        """Pick the release that seeds the URL's release segment.

        A module version's taxonomy is published under the release in
        which that version was introduced (its ``start_release_id``), not
        under the report release. Seeding the segment from the report
        release would build URIs like ``.../ae/4.2.1/mod/ae`` for modules
        that did not change since 4.2 and therefore have no taxonomy at
        4.2.1. So the segment is resolved from the module version itself,
        the same way for every caller.

        Returns one of:

        - ``str`` — a final URI (CSV hit, ``.json`` suffix already
          stripped). The caller must short-circuit and return it.
        - ``int`` — the release_id whose ``Release.code`` should fill
          the ``/{release}/`` segment.
        - ``None`` — nothing resolvable; caller returns ``None``.
        """
        from dpmcore.data import (
            get_module_schema_ref_by_version,
        )

        if mv.version_number:
            static = get_module_schema_ref_by_version(
                module_code, mv.version_number
            )
            if static:
                return static.removesuffix(".json")
        return mv.start_release_id
