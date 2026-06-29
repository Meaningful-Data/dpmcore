from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from datetime import date, datetime
from itertools import product
from typing import TYPE_CHECKING, Any, cast

import numpy
import pandas as pd

from dpmcore import errors
from dpmcore.dpm_xl.model_queries import ModuleVersionQuery
from dpmcore.dpm_xl.utils.tokens import VARIABLE_VID
from dpmcore.orm.operations import (
    OperationScope,
    OperationScopeComposition,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

FROM_REFERENCE_DATE = "FromReferenceDate"
TO_REFERENCE_DATE = "ToReferenceDate"
MODULE_VID = "ModuleVID"


class OperationScopeService:
    """Synthesize ``OperationScope`` instances in memory for a DPM-XL expression.

    Computes which module versions are involved in an operation given
    its table references and precondition items. The resulting
    ``OperationScope`` / ``OperationScopeComposition`` objects are
    in-memory carriers used downstream to classify cross-module
    dependencies — they are never persisted and the service does not
    mutate the SQLAlchemy session.
    """

    def __init__(self, session: Session | None = None) -> None:
        self.session = session
        self.module_vids: list[int] = []
        self.current_date = datetime.today().date()

        self.operation_scopes: list[OperationScope] = []

    def _require_session(self) -> Session:
        if self.session is None:
            raise RuntimeError(
                "OperationScopeService.session is required for this operation"
            )
        return self.session

    def calculate_operation_scope(
        self,
        tables_vids: Sequence[int],
        precondition_items: Sequence[str],
        release_id: int | None = None,
        table_codes: Sequence[str] | None = None,
    ) -> tuple[list[OperationScope], list[OperationScope]]:
        """Calculate OperationScope and OperationScopeComposition tables for an operation version, taking as input
        a list with the operation table version ids in order to calculate the module versions involved in the operation
        :param tables_vids: List with table version ids
        :param precondition_items: List with precondition codes
        :param release_id: Optional release ID to filter modules. If None, defaults to last release.
        :param table_codes: Optional list of table codes. If provided, finds ALL module versions with these table codes in the release.
        :return two list with existing and new scopes.
        """
        # Get last release if not specified
        if release_id is None:
            release_id = ModuleVersionQuery.get_last_release(
                self._require_session()
            )

        modules_info_dataframe = self.extract_module_info(
            tables_vids=tables_vids,
            precondition_items=precondition_items,
            release_id=release_id,
            table_codes=table_codes,
        )  # We extract all the releases from the database
        if modules_info_dataframe is None:
            return [], []

        modules_vids: list[int] = cast(
            list[int],
            modules_info_dataframe[MODULE_VID].unique().tolist(),
        )
        if len(modules_info_dataframe) == 1:
            module_vid = modules_vids[0]
            from_date = modules_info_dataframe["FromReferenceDate"].values[0]
            to_date = modules_info_dataframe["ToReferenceDate"].values[0]
            module_code = modules_info_dataframe["ModuleCode"].values[0]
            version_number = modules_info_dataframe["VersionNumber"].values[0]
            operation_scope = self.create_operation_scope(from_date)
            self.create_operation_scope_composition(
                operation_scope=operation_scope,
                module_vid=int(module_vid),
                module_info={
                    "code": module_code,
                    "version_number": version_number,
                    "from_reference_date": from_date,
                    "to_reference_date": to_date,
                },
            )
        else:
            intra_modules: list[int] = []
            # cross_modules has 3+ distinct runtime shapes: dict[int, list[int]]
            # (table VID -> module VIDs), dict[str, list[int]] (table code ->
            # module VIDs), or dict[str, dict[str, list[int]]] when lifecycle
            # grouping adds "_starting"/"_ending" wrappers. Using Any keeps
            # the branches readable.
            cross_modules: dict[Any, Any] = {}

            # When using table_codes, unique operands are based on table codes, not table VIDs
            if table_codes:
                # A module hosts an intra-instance scope only when it
                # covers every distinct referenced table code AND every
                # distinct precondition (filing-indicator) code.
                unique_operands_number = len(set(table_codes)) + len(
                    set(precondition_items)
                )

                # First pass: categorize modules by table code and lifecycle
                # We track lifecycle to handle version transitions within the SAME module
                # table_code -> [module_vids that START in this release]
                starting_by_code: dict[str, list[int]] = {}
                # table_code -> [module_vids that END or are active]
                ending_by_code: dict[str, list[int]] = {}

                code_groups = cast(
                    Iterable[tuple[int, pd.DataFrame]],
                    modules_info_dataframe.groupby(MODULE_VID),
                )
                for module_vid, group_df in code_groups:
                    # Referenced table codes this module contains. Drop
                    # NaN: precondition rows carry their code in "Code",
                    # not "TableCode", so leaving the NaN in would inflate
                    # the count by one spurious bucket.
                    table_codes_in_module: list[str] = (
                        cast(
                            list[str],
                            group_df["TableCode"].dropna().unique().tolist(),
                        )
                        if "TableCode" in group_df.columns
                        else []
                    )
                    # Distinct precondition codes this module provides
                    # (filing indicators live in the "Code" column).
                    precondition_codes_in_module = (
                        int(group_df["Code"].dropna().nunique())
                        if "Code" in group_df.columns
                        else 0
                    )

                    # Get module lifecycle info
                    start_release = (
                        group_df["StartReleaseID"].values[0]
                        if "StartReleaseID" in group_df.columns
                        else None
                    )

                    # Determine if this is a "new" module starting in this release
                    is_starting = start_release == release_id

                    operands_in_module = (
                        len(table_codes_in_module)
                        + precondition_codes_in_module
                    )
                    if operands_in_module == unique_operands_number:
                        # Intra-module: include ALL modules active in the release
                        intra_modules.append(module_vid)
                    else:
                        # Track modules by table code and lifecycle
                        for table_code in table_codes_in_module:
                            if is_starting:
                                if table_code not in starting_by_code:
                                    starting_by_code[table_code] = []
                                starting_by_code[table_code].append(module_vid)
                            else:
                                if table_code not in ending_by_code:
                                    ending_by_code[table_code] = []
                                ending_by_code[table_code].append(module_vid)

                # Second pass: determine if lifecycle separation is needed
                # Only separate if a table code has modules in BOTH starting and ending
                # (indicating a version transition for that table)
                needs_lifecycle_separation = any(
                    code in starting_by_code and code in ending_by_code
                    for code in set(starting_by_code.keys())
                    | set(ending_by_code.keys())
                )

                if needs_lifecycle_separation:
                    # Separate into starting and ending scopes
                    starting_modules: dict[str, list[int]] = {}
                    ending_modules: dict[str, list[int]] = {}
                    for code, vids in starting_by_code.items():
                        starting_modules[code] = vids
                    for code, vids in ending_by_code.items():
                        ending_modules[code] = vids

                    # Supplement each group with table codes that are NOT
                    # undergoing a lifecycle transition.  Without this,
                    # a group that only covers some table codes would
                    # produce incomplete (single-module) scopes via the
                    # Cartesian product.
                    for code, vids in ending_by_code.items():
                        if code not in starting_modules:
                            starting_modules[code] = vids
                    for code, vids in starting_by_code.items():
                        if code not in ending_modules:
                            ending_modules[code] = vids

                    if starting_modules:
                        cross_modules["_starting"] = starting_modules
                    if ending_modules:
                        cross_modules["_ending"] = ending_modules
                else:
                    # No version transitions - combine all modules by table code
                    all_by_code: dict[str, list[int]] = {}
                    for code, vids in starting_by_code.items():
                        if code not in all_by_code:
                            all_by_code[code] = []
                        all_by_code[code].extend(vids)
                    for code, vids in ending_by_code.items():
                        if code not in all_by_code:
                            all_by_code[code] = []
                        all_by_code[code].extend(vids)
                    cross_modules = dict(all_by_code)
            else:
                # Original logic for table VIDs
                unique_operands_number = len(tables_vids) + len(
                    precondition_items
                )
                vid_groups = cast(
                    Iterable[tuple[int, pd.DataFrame]],
                    modules_info_dataframe.groupby(MODULE_VID),
                )
                for module_vid, group_df in vid_groups:
                    group_vids = cast(
                        list[int],
                        group_df[VARIABLE_VID].unique().tolist(),
                    )
                    if len(group_vids) == unique_operands_number:
                        intra_modules.append(module_vid)
                    else:
                        for table_vid in group_vids:
                            if table_vid not in cross_modules:
                                cross_modules[table_vid] = []
                            cross_modules[table_vid].append(module_vid)

            if len(intra_modules):
                self.process_repeated(intra_modules, modules_info_dataframe)

            required_preconditions = set(precondition_items)
            if cross_modules:
                if table_codes:
                    required_codes = set(table_codes)
                    if (
                        "_starting" in cross_modules
                        or "_ending" in cross_modules
                    ):
                        # Lifecycle grouping: complete and process each
                        # generation independently.
                        for generation in ("_starting", "_ending"):
                            pool = cross_modules.get(generation)
                            if not pool:
                                continue
                            self._supplement_missing_codes(
                                pool, required_codes, modules_info_dataframe
                            )
                            self.process_cross_module(
                                cross_modules=pool,
                                modules_dataframe=modules_info_dataframe,
                                required_keys=required_codes,
                                required_precondition_codes=(
                                    required_preconditions
                                ),
                            )
                    else:
                        # Complete each partial module into a cross-instance
                        # scope by pulling its missing table codes from the
                        # modules that provide them (Issue #119/#120), then
                        # build the combinations.
                        self._supplement_missing_codes(
                            cross_modules,
                            required_codes,
                            modules_info_dataframe,
                        )
                        self.process_cross_module(
                            cross_modules=cross_modules,
                            modules_dataframe=modules_info_dataframe,
                            required_keys=required_codes,
                            required_precondition_codes=required_preconditions,
                        )
                else:
                    # Table-VID path: supplement any referenced table VID
                    # not yet present, then build the cross combinations.
                    self._supplement_missing_codes(
                        cross_modules,
                        set(tables_vids),
                        modules_info_dataframe,
                        key_column=VARIABLE_VID,
                    )
                    self.process_cross_module(
                        cross_modules=cross_modules,
                        modules_dataframe=modules_info_dataframe,
                        required_keys=set(tables_vids),
                        required_precondition_codes=required_preconditions,
                    )

        return self.get_scopes_with_status()

    @staticmethod
    def _supplement_missing_codes(
        pool: dict[Any, list[int]],
        required_codes: set[Any],
        modules_dataframe: pd.DataFrame,
        key_column: str = "TableCode",
    ) -> None:
        """Add providers for referenced operands absent from *pool*.

        A partial module contributes only the operands it actually holds,
        so an operand it lacks would be missing from the Cartesian product
        and yield an incomplete single-module scope. For each such operand,
        register every module that provides it — looked up in *key_column*
        (``"TableCode"`` for the table-code path, the variable-VID column
        for the table-VID path) — so the product pairs the partial module
        with a provider into a complete cross-instance scope
        (Issue #119/#120). Operands already present are left untouched to
        avoid re-pairing a partial module with itself.

        Pairing modules from non-overlapping lifecycle generations is
        prevented downstream: :meth:`process_cross_module` drops any
        combination whose reference-date windows do not overlap.
        """
        if key_column not in modules_dataframe.columns:
            return
        for code in required_codes:
            if code in pool:
                continue
            providers: list[int] = (
                modules_dataframe[modules_dataframe[key_column] == code][
                    MODULE_VID
                ]
                .unique()
                .tolist()
            )
            if providers:
                pool[code] = providers

    def extract_module_info(
        self,
        tables_vids: Sequence[int],
        precondition_items: Sequence[str],
        release_id: int | None = None,
        table_codes: Sequence[str] | None = None,
    ) -> pd.DataFrame | None:
        """Extracts modules information of tables version ids and preconditions from database and
        joins them in a single dataframe
        :param tables_vids: List with table version ids
        :param precondition_items: List with precondition codes
        :param release_id: Optional release ID to filter modules
        :param table_codes: Optional list of table codes. If provided, queries ALL module versions with these codes.
        :return two list with existing and new scopes.
        """
        modules_info_lst: list[pd.DataFrame] = []
        modules_info_dataframe: pd.DataFrame | None = None

        # If table_codes are provided, query by codes to get ALL versions
        session = self._require_session()
        if table_codes and len(table_codes):
            tables_modules_info_dataframe = (
                ModuleVersionQuery.get_from_table_codes(
                    session=session,
                    table_codes=list(table_codes),
                    release_id=release_id,
                )
            )
            if tables_modules_info_dataframe.empty:
                # The "1-13" template is keyed on ``table_version_ids``; pass
                # the table codes under that name (codes ARE table-version
                # identifiers) so the message formats instead of raising a
                # KeyError. Reached now that single-day module versions are
                # excluded from scope and a release may host none.
                raise errors.SemanticError(
                    "1-13", table_version_ids=list(table_codes)
                )
            modules_info_lst.append(tables_modules_info_dataframe)
        # Otherwise use the traditional table VID approach
        elif len(tables_vids):
            tables_modules_info_dataframe = (
                ModuleVersionQuery.get_from_tables_vids(
                    session=session,
                    tables_vids=list(tables_vids),
                    release_id=release_id,
                )
            )
            missing_table_modules: set[int]
            if tables_modules_info_dataframe.empty:
                missing_table_modules = set(tables_vids)
            else:
                modules_tables = tables_modules_info_dataframe[
                    VARIABLE_VID
                ].tolist()
                missing_table_modules = set(tables_vids).difference(
                    set(modules_tables)
                )

            if len(missing_table_modules):
                raise errors.SemanticError(
                    "1-13", table_version_ids=missing_table_modules
                )

            modules_info_lst.append(tables_modules_info_dataframe)

        if len(precondition_items):
            preconditions_modules_info_dataframe = (
                ModuleVersionQuery.get_precondition_module_versions(
                    session=session,
                    precondition_items=list(precondition_items),
                    release_id=release_id,
                )
            )

            missing_precondition_modules: set[str]
            if preconditions_modules_info_dataframe.empty:
                missing_precondition_modules = set(precondition_items)
            else:
                modules_preconditions = preconditions_modules_info_dataframe[
                    "Code"
                ].tolist()
                missing_precondition_modules = set(
                    precondition_items
                ).difference(set(modules_preconditions))

            if missing_precondition_modules:
                raise errors.SemanticError(
                    "1-14", precondition_items=missing_precondition_modules
                )

            modules_info_lst.append(preconditions_modules_info_dataframe)

        if len(modules_info_lst):
            modules_info_dataframe = pd.concat(modules_info_lst)
        return modules_info_dataframe

    def process_repeated(
        self,
        modules_vids: Sequence[int],
        modules_info: pd.DataFrame,
    ) -> None:
        """Method to calculate OperationScope and OperationScopeComposition tables for repeated operations
        :param modules_vids: list with module version ids.
        """
        # Pre-build dict lookup for O(1) access instead of DataFrame boolean filtering per module
        module_lookup: dict[int, pd.Series[Any]] = {}
        for _, row in modules_info.iterrows():
            vid = row[MODULE_VID]
            if vid not in module_lookup:
                module_lookup[vid] = row

        for module_vid in modules_vids:
            module_row = module_lookup[module_vid]
            from_date = module_row["FromReferenceDate"]
            to_date = module_row["ToReferenceDate"]
            module_code = module_row["ModuleCode"]
            version_number = module_row["VersionNumber"]
            operation_scope = self.create_operation_scope(from_date)
            self.create_operation_scope_composition(
                operation_scope=operation_scope,
                module_vid=module_vid,
                module_info={
                    "code": module_code,
                    "version_number": version_number,
                    "from_reference_date": from_date,
                    "to_reference_date": to_date,
                },
            )

    def process_cross_module(
        self,
        cross_modules: dict[Any, list[int]],
        modules_dataframe: pd.DataFrame,
        required_keys: Iterable[Any] | None = None,
        required_precondition_codes: Iterable[Any] | None = None,
    ) -> None:
        """Method to calculate OperationScope and OperationScopeComposition tables for a cross module operation
        :param cross_modules: dictionary with table version ids as key and its module version ids as values
        :param modules_dataframe: dataframe with modules data.
        :param required_keys: full set of referenced operand keys (table
            codes or table VIDs) the combination must cover. When the
            cross-module pool does not span every required key, no single
            module nor combination of modules can evaluate the operation,
            so no scope is emitted. ``None`` disables the check.
        :param required_precondition_codes: gating precondition (filing
            indicator) codes; a combination is emitted only if its modules
            collectively report all of them (Issue #120). ``None``/empty
            disables the check.
        """
        # Table coverage: each generated combination provides exactly the
        # pool's key set (one module per key), and supplementation in
        # ``calculate_operation_scope`` already ensures the pool spans every
        # required table code. This guard is a defensive backstop — if the
        # pool still lacks a required key (a code with no provider at all),
        # no combination can evaluate the operation, so emit nothing.
        if required_keys is not None and not set(cross_modules).issuperset(
            required_keys
        ):
            return

        modules_dataframe[FROM_REFERENCE_DATE] = pd.to_datetime(
            modules_dataframe[FROM_REFERENCE_DATE],
            format="mixed",
            dayfirst=True,
        )
        modules_dataframe[TO_REFERENCE_DATE] = pd.to_datetime(
            modules_dataframe[TO_REFERENCE_DATE], format="mixed", dayfirst=True
        )

        # Pre-build dict lookup for O(1) access instead of DataFrame boolean filtering per module
        module_lookup: dict[int, pd.Series[Any]] = {}
        for _, row in modules_dataframe.iterrows():
            vid = row[MODULE_VID]
            if vid not in module_lookup:
                module_lookup[vid] = row

        # Distinct precondition codes each module reports, so a combination
        # can be checked for full precondition coverage.
        req_preconditions = set(required_precondition_codes or [])
        precond_by_module: dict[int, set[Any]] = {}
        if req_preconditions and "Code" in modules_dataframe.columns:
            code_groups = cast(
                Iterable[tuple[int, pd.DataFrame]],
                modules_dataframe.groupby(MODULE_VID),
            )
            for vid, grp in code_groups:
                precond_by_module[int(vid)] = set(grp["Code"].dropna())

        # Many referenced table codes share the *same* provider list (one
        # FINREP module commonly hosts every F_04.* table). The Cartesian
        # product over the raw per-code lists would then choose a provider
        # for each code independently and emit the identical module set once
        # per redundant choice — thousands of duplicates for the same scope.
        # Collapsing identical provider lists first removes that multiplicity
        # without changing which module sets are reachable: two codes with
        # the same providers impose the same "pick one of these" constraint.
        distinct_lists: list[tuple[int, ...]] = []
        seen_lists: set[frozenset[int]] = set()
        for providers in cross_modules.values():
            list_key = frozenset(providers)
            if list_key in seen_lists:
                continue
            seen_lists.add(list_key)
            distinct_lists.append(tuple(providers))

        # No constraints means no combination to evaluate. An empty
        # ``distinct_lists`` would make ``product()`` yield a single empty
        # tuple, whose empty module set has no reference dates and would
        # raise on ``from_dates.max()``. Real callers never pass an empty
        # pool (each is guarded by ``if cross_modules``), so this is a
        # defensive no-op.
        if not distinct_lists:
            return

        # Collapse each combination to its module set and evaluate only the
        # first occurrence of a given set, so a combination never yields more
        # than one scope.
        seen_sets: set[frozenset[int]] = set()
        valid_sets: list[frozenset[int]] = []
        ref_from_by_set: dict[frozenset[int], Any] = {}
        for combination in product(*distinct_lists):
            module_set = frozenset(combination)
            if module_set in seen_sets:
                continue
            seen_sets.add(module_set)

            combination_info = modules_dataframe[
                modules_dataframe[MODULE_VID].isin(module_set)
            ]
            from_dates = combination_info[FROM_REFERENCE_DATE].to_numpy()
            to_dates = combination_info[TO_REFERENCE_DATE].to_numpy()
            ref_from_date = from_dates.max()
            ref_to_date = to_dates.min()

            # Modules in a combination must share an overlapping
            # reference-date window; otherwise they are never reported
            # together (e.g. different lifecycle generations) and the
            # combination is not a real scope (Issue #119/#120).
            overlaps = all(
                not (
                    to_date < ref_from_date
                    or ((not pd.isna(ref_to_date)) and from_date > ref_to_date)
                )
                for from_date, to_date in zip(
                    from_dates, to_dates, strict=False
                )
            )
            if not overlaps:
                continue

            # Every gating precondition must be reported by some module in
            # the combination, else it cannot evaluate the operation.
            if req_preconditions:
                covered: set[Any] = set()
                for module in module_set:
                    covered |= precond_by_module.get(module, set())
                if not covered.issuperset(req_preconditions):
                    continue

            valid_sets.append(module_set)
            ref_from_by_set[module_set] = ref_from_date

        # Each retained combination already covers every required key (the
        # product picks one provider per distinct constraint). A combination
        # that strictly contains another retained one therefore only pairs in
        # a module a smaller covering combination already does without — e.g.
        # two alternative modules that each host the whole referenced table
        # set. Drop such non-minimal supersets so the alternatives surface as
        # separate scopes instead of one bloated multi-module scope.
        for module_set in valid_sets:
            if any(other < module_set for other in valid_sets):
                continue
            operation_scope = self.create_operation_scope(
                ref_from_by_set[module_set]
            )
            for module in module_set:
                module_row = module_lookup.get(module)
                if module_row is None:
                    continue
                self.create_operation_scope_composition(
                    operation_scope=operation_scope,
                    module_vid=module,
                    module_info={
                        "code": module_row["ModuleCode"],
                        "version_number": module_row["VersionNumber"],
                        "from_reference_date": module_row[FROM_REFERENCE_DATE],
                        "to_reference_date": module_row[TO_REFERENCE_DATE],
                    },
                )

    def create_operation_scope(
        self,
        submission_date: Any,
    ) -> OperationScope:
        """Synthesize an in-memory ``OperationScope`` instance.

        The returned object is appended to ``self.operation_scopes``
        and is **never** added to the SQLAlchemy session. It exists
        solely as a carrier for downstream cross-module dependency
        classification.
        """
        final_date: date | None
        if not pd.isnull(submission_date):
            if isinstance(submission_date, numpy.datetime64):
                submission_date = str(submission_date).split("T")[0]
            if isinstance(submission_date, str):
                final_date = datetime.strptime(
                    submission_date, "%Y-%m-%d"
                ).date()
            elif isinstance(submission_date, datetime):
                final_date = submission_date.date()
            elif isinstance(submission_date, date):
                final_date = submission_date
            else:
                final_date = None
        else:
            final_date = None
        operation_scope = OperationScope(
            is_active=1,  # Use 1 instead of True for PostgreSQL bigint compatibility
            from_submission_date=final_date,
            row_guid=str(uuid.uuid4()),
        )
        self.operation_scopes.append(operation_scope)
        return operation_scope

    def create_operation_scope_composition(
        self,
        operation_scope: OperationScope,
        module_vid: int,
        module_info: dict[str, Any] | None = None,
    ) -> None:
        """Attach an ``OperationScopeComposition`` to ``operation_scope``.

        Builds an in-memory composition link via the SQLAlchemy
        relationship (which auto-populates
        ``operation_scope.operation_scope_compositions``). Never calls
        ``session.add``.
        """
        operation_scope_composition = OperationScopeComposition(
            operation_scope=operation_scope,
            module_vid=module_vid,
            row_guid=str(uuid.uuid4()),
        )
        # Store module info as transient attribute for to_dict() access
        if module_info:
            # _module_info is a runtime-only transient attribute not part of
            # the SQLAlchemy mapped schema.
            operation_scope_composition._module_info = module_info  # type: ignore[attr-defined]

    def get_scopes_with_status(
        self,
    ) -> tuple[list[OperationScope], list[OperationScope]]:
        """Return the synthesized scopes.

        First element of the tuple holds the synthesized scopes;
        second element is always empty (kept for tuple-shape
        compatibility with the pre-stripping API). The persisted
        "existing vs new" classification is no longer relevant —
        this service does not persist anything.
        """
        return list(self.operation_scopes), []
