from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, DefaultDict, Dict, Iterable, List, Optional, Set, Tuple

from sqlalchemy.orm import Session, selectinload

from dpmcore.orm.infrastructure import Concept, Organisation
from dpmcore.orm.operations import (
    OperandReference,
    OperandReferenceLocation,
    Operation,
    OperationNode,
    OperationScope,
    OperationScopeComposition,
    OperationVersion,
)
from dpmcore.orm.packaging import Module, ModuleVersion


class MeiliJsonError(Exception):
    """Raised when JSON generation for Meilisearch cannot proceed."""


@dataclass(frozen=True)
class MeiliJsonResult:
    """Outcome of a Meilisearch JSON generation run."""

    operations_written: int
    output_file: Path


@dataclass
class BulkDataContext:
    """Container for all pre-loaded lookup dictionaries."""

    scopes_by_opvid: DefaultDict[int, List[OperationScope]] = field(
        default_factory=lambda: defaultdict(list)
    )
    compositions_by_scopeid: DefaultDict[
        int, List[OperationScopeComposition]
    ] = field(default_factory=lambda: defaultdict(list))
    parent_first_versions: Dict[int, OperationVersion] = field(
        default_factory=dict
    )
    all_versions_by_opid: DefaultDict[int, List[OperationVersion]] = field(
        default_factory=lambda: defaultdict(list)
    )
    nodes_by_opvid: DefaultDict[int, List[OperationNode]] = field(
        default_factory=lambda: defaultdict(list)
    )
    refs_by_nodeid: DefaultDict[int, List[OperandReference]] = field(
        default_factory=lambda: defaultdict(list)
    )
    operand_ref_map: Dict[int, Optional[int]] = field(default_factory=dict)
    locations_by_refid: DefaultDict[int, List[OperandReferenceLocation]] = (
        field(default_factory=lambda: defaultdict(list))
    )


def create_substrings(text: Optional[str]) -> str:
    """Generate all possible substrings from *text*."""
    if not text:
        return ""

    stripped = str(text).strip()
    substrings: Set[str] = set()

    for start in range(len(stripped)):
        for end in range(start + 1, len(stripped) + 1):
            substrings.add(stripped[start:end])

    return " ".join(sorted(substrings))


def get_scope_module_key(
    modules: List[Dict[str, Any]],
) -> Tuple[Tuple[str, str], ...]:
    """Generate a stable key from scope modules for deduplication."""
    return tuple(
        sorted(
            (
                str(module.get("code") or ""),
                str(module.get("moduleVersionNumber") or ""),
            )
            for module in modules
        )
    )


def _iso_date(value: Any) -> Optional[str]:
    """Serialize date-like objects to ISO strings."""
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def calculate_applicable(modules: List[Dict[str, Any]]) -> bool:
    """Calculate the ``applicable`` field from module reference dates."""
    if len(modules) == 0:
        return False

    if len(modules) == 1:
        from_date = modules[0].get("moduleVersionFromReferenceDate")
        to_date = modules[0].get("moduleVersionToReferenceDate")

        if not from_date:
            return False
        if not to_date:
            return True
        if from_date == to_date:
            return False
        return str(from_date) < str(to_date)

    max_from_date: Optional[str] = None
    min_to_date: Optional[str] = None
    all_to_dates_null = True

    for module in modules:
        module_from_date = module.get("moduleVersionFromReferenceDate")
        if module_from_date:
            module_from_date_str = str(module_from_date)
            if max_from_date is None or module_from_date_str > max_from_date:
                max_from_date = module_from_date_str

        module_to_date = module.get("moduleVersionToReferenceDate")
        if module_to_date is not None:
            module_to_date_str = str(module_to_date)
            all_to_dates_null = False
            if min_to_date is None or module_to_date_str < min_to_date:
                min_to_date = module_to_date_str

    if not max_from_date:
        return False
    if all_to_dates_null:
        return True
    if max_from_date == min_to_date:
        return False
    return max_from_date < str(min_to_date)


_SQLITE_CHUNK_SIZE = 999


def _chunked_query(base_query: Any, column: Any, ids: Any) -> List[Any]:
    """Split a large IN clause into 999-item batches for SQLite compatibility."""
    ids_list = list(ids)
    result: List[Any] = []
    for i in range(0, len(ids_list), _SQLITE_CHUNK_SIZE):
        chunk = ids_list[i : i + _SQLITE_CHUNK_SIZE]
        result.extend(base_query.filter(column.in_(chunk)).all())
    return result


class MeiliJsonService:
    """Generate the operations JSON consumed by Meilisearch."""

    def __init__(self, session: Optional[Session] = None) -> None:
        self._session = session

    def generate(self, output_file: str) -> MeiliJsonResult:
        if self._session is None:
            raise MeiliJsonError(
                "A database session is required to generate Meilisearch JSON."
            )

        operation_versions = self._get_operation_versions()

        if not operation_versions:
            path = Path(output_file)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("[]", encoding="utf-8")
            return MeiliJsonResult(
                operations_written=0,
                output_file=path,
            )

        operation_vids = [item.operation_vid for item in operation_versions]
        ctx = self._bulk_load_related_data(
            operation_versions=operation_versions,
            operation_vids=operation_vids,
        )
        payload = self._build_payload(operation_versions, ctx)

        path = Path(output_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))

        return MeiliJsonResult(
            operations_written=len(payload),
            output_file=path,
        )

    def merge_by_owner(
        self,
        *,
        new_file: str,
        existing_file: str,
        output_file: str,
    ) -> MeiliJsonResult:
        try:
            with open(new_file, encoding="utf-8") as handle:
                new_operations = json.load(handle)
            with open(existing_file, encoding="utf-8") as handle:
                existing_operations = json.load(handle)
        except FileNotFoundError as exc:
            raise MeiliJsonError(f"File not found: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise MeiliJsonError(f"Invalid JSON: {exc}") from exc

        new_owners = {
            operation.get("ownerAcronym")
            for operation in new_operations
            if operation.get("ownerAcronym")
        }

        filtered_existing = [
            operation
            for operation in existing_operations
            if operation.get("ownerAcronym") not in new_owners
        ]
        merged = filtered_existing + new_operations
        merged.sort(key=lambda item: item.get("ID", 0))

        path = Path(output_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(merged, handle, sort_keys=True, separators=(",", ":"))

        return MeiliJsonResult(
            operations_written=len(merged),
            output_file=path,
        )

    def _get_operation_versions(self) -> List[OperationVersion]:
        query = (
            self._session.query(OperationVersion)
            .join(OperationVersion.operation)
            .options(
                selectinload(OperationVersion.operation)
                .selectinload(Operation.concept)
                .selectinload(Concept.owner),
                selectinload(OperationVersion.start_release),
                selectinload(OperationVersion.end_release),
                selectinload(OperationVersion.precondition_operation),
            )
            .order_by(OperationVersion.operation_vid)
        )

        return list(query.all())

    def _bulk_load_related_data(
        self,
        *,
        operation_versions: List[OperationVersion],
        operation_vids: List[int],
    ) -> BulkDataContext:
        ctx = BulkDataContext()
        if not operation_vids:
            return ctx

        scopes = _chunked_query(
            self._session.query(OperationScope),
            OperationScope.operation_vid,
            operation_vids,
        )
        for scope in scopes:
            if scope.operation_vid is not None:
                ctx.scopes_by_opvid[scope.operation_vid].append(scope)

        scope_ids = [scope.operation_scope_id for scope in scopes]
        if scope_ids:
            compositions = _chunked_query(
                self._session.query(OperationScopeComposition).options(
                    selectinload(OperationScopeComposition.module_version)
                    .selectinload(ModuleVersion.module)
                    .selectinload(Module.framework),
                    selectinload(
                        OperationScopeComposition.module_version
                    ).selectinload(ModuleVersion.start_release),
                    selectinload(
                        OperationScopeComposition.module_version
                    ).selectinload(ModuleVersion.end_release),
                ),
                OperationScopeComposition.operation_scope_id,
                scope_ids,
            )
            for composition in compositions:
                ctx.compositions_by_scopeid[
                    composition.operation_scope_id
                ].append(composition)

        operation_ids = {
            operation_version.operation_id
            for operation_version in operation_versions
            if operation_version.operation_id is not None
        }
        parent_operation_ids = {
            operation_version.operation.group_operation_id
            for operation_version in operation_versions
            if operation_version.operation is not None
            and operation_version.operation.group_operation_id is not None
        }

        if parent_operation_ids:
            parent_versions = _chunked_query(
                self._session.query(OperationVersion)
                .options(selectinload(OperationVersion.operation))
                .order_by(
                    OperationVersion.operation_id,
                    OperationVersion.operation_vid,
                ),
                OperationVersion.operation_id,
                parent_operation_ids,
            )
            for parent_version in parent_versions:
                if (
                    parent_version.operation_id is not None
                    and parent_version.operation_id
                    not in ctx.parent_first_versions
                ):
                    ctx.parent_first_versions[parent_version.operation_id] = (
                        parent_version
                    )

        all_versions = _chunked_query(
            self._session.query(OperationVersion)
            .options(
                selectinload(OperationVersion.operation)
                .selectinload(Operation.concept)
                .selectinload(Concept.owner),
                selectinload(OperationVersion.start_release),
                selectinload(OperationVersion.end_release),
                selectinload(OperationVersion.precondition_operation),
            )
            .order_by(
                OperationVersion.operation_id,
                OperationVersion.operation_vid,
            ),
            OperationVersion.operation_id,
            operation_ids,
        )
        for version in all_versions:
            if version.operation_id is not None:
                ctx.all_versions_by_opid[version.operation_id].append(version)

        all_opvids_for_info = {
            version.operation_vid for version in operation_versions
        }
        for versions in ctx.all_versions_by_opid.values():
            for version in versions:
                all_opvids_for_info.add(version.operation_vid)

        previous_version_opvids = set(all_opvids_for_info) - set(
            operation_vids
        )
        if previous_version_opvids:
            previous_scopes = _chunked_query(
                self._session.query(OperationScope),
                OperationScope.operation_vid,
                previous_version_opvids,
            )
            for scope in previous_scopes:
                if scope.operation_vid is not None:
                    ctx.scopes_by_opvid[scope.operation_vid].append(scope)

            extra_scope_ids = [
                scope.operation_scope_id for scope in previous_scopes
            ]
            if extra_scope_ids:
                extra_compositions = _chunked_query(
                    self._session.query(OperationScopeComposition).options(
                        selectinload(OperationScopeComposition.module_version)
                        .selectinload(ModuleVersion.module)
                        .selectinload(Module.framework),
                        selectinload(
                            OperationScopeComposition.module_version
                        ).selectinload(ModuleVersion.start_release),
                        selectinload(
                            OperationScopeComposition.module_version
                        ).selectinload(ModuleVersion.end_release),
                    ),
                    OperationScopeComposition.operation_scope_id,
                    extra_scope_ids,
                )
                for composition in extra_compositions:
                    ctx.compositions_by_scopeid[
                        composition.operation_scope_id
                    ].append(composition)

        nodes = _chunked_query(
            self._session.query(OperationNode),
            OperationNode.operation_vid,
            all_opvids_for_info,
        )
        node_ids: List[int] = []
        for node in nodes:
            if node.operation_vid is not None:
                ctx.nodes_by_opvid[node.operation_vid].append(node)
            node_ids.append(node.node_id)

        if node_ids:
            refs = _chunked_query(
                self._session.query(OperandReference),
                OperandReference.node_id,
                node_ids,
            )
            ref_ids: List[int] = []
            for reference in refs:
                ctx.operand_ref_map[reference.operand_reference_id] = (
                    reference.variable_id
                )
                if reference.node_id is not None:
                    ctx.refs_by_nodeid[reference.node_id].append(reference)
                ref_ids.append(reference.operand_reference_id)

            if ref_ids:
                locations = _chunked_query(
                    self._session.query(OperandReferenceLocation),
                    OperandReferenceLocation.operand_reference_id,
                    ref_ids,
                )
                for location in locations:
                    ctx.locations_by_refid[
                        location.operand_reference_id
                    ].append(location)

        return ctx

    def _process_scope_compositions(
        self,
        *,
        scope: OperationScope,
        ctx: BulkDataContext,
        include_release_info: bool,
    ) -> List[Dict[str, Any]]:
        modules: List[Dict[str, Any]] = []
        compositions = sorted(
            ctx.compositions_by_scopeid.get(scope.operation_scope_id, []),
            key=lambda comp: (
                comp.module_vid if comp.module_vid is not None else -1,
                comp.operation_scope_id,
            ),
        )

        for composition in compositions:
            module_version = composition.module_version
            module = (
                module_version.module if module_version is not None else None
            )
            framework = module.framework if module is not None else None

            if module_version is None:
                continue

            payload: Dict[str, Any] = {
                "code": module_version.code,
                "name": module_version.name,
                "moduleVersionNumber": module_version.version_number,
                "frameworkCode": framework.code if framework else None,
                "frameworkName": framework.name if framework else None,
                "hierarchy": (
                    f"{framework.code} > {module_version.code}"
                    if framework and module_version.code
                    else None
                ),
                "moduleVersionFromReferenceDate": _iso_date(
                    module_version.from_reference_date
                ),
                "moduleVersionToReferenceDate": _iso_date(
                    module_version.to_reference_date
                ),
            }

            if include_release_info:
                payload.update(
                    {
                        "moduleVersionStartReleaseCode": (
                            str(module_version.start_release.code)
                            if module_version.start_release
                            and module_version.start_release.code is not None
                            else None
                        ),
                        "moduleVersionStartReleaseId": (
                            module_version.start_release.release_id
                            if module_version.start_release
                            else None
                        ),
                        "moduleVersionEndReleaseCode": (
                            str(module_version.end_release.code)
                            if module_version.end_release
                            and module_version.end_release.code is not None
                            else None
                        ),
                        "moduleVersionEndReleaseId": (
                            module_version.end_release.release_id
                            if module_version.end_release
                            else None
                        ),
                    }
                )

            modules.append(payload)

        modules.sort(
            key=lambda module: (
                module.get("frameworkCode") or "",
                module.get("code") or "",
                module.get("moduleVersionNumber") or "",
                module.get("moduleVersionFromReferenceDate") or "",
                module.get("moduleVersionToReferenceDate") or "",
            )
        )

        return modules

    def _get_operation_info_optimized(
        self, *, operation_vid: int, ctx: BulkDataContext
    ) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        nodes = sorted(
            ctx.nodes_by_opvid.get(operation_vid, []),
            key=lambda node: node.node_id,
        )

        for node in nodes:
            refs = sorted(
                ctx.refs_by_nodeid.get(node.node_id, []),
                key=lambda r: (
                    r.variable_id if r.variable_id is not None else -1,
                    r.operand_reference_id,
                ),
            )
            for reference in refs:
                locations = sorted(
                    ctx.locations_by_refid.get(
                        reference.operand_reference_id, []
                    ),
                    key=lambda loc: (
                        loc.table or "",
                        loc.row or "",
                        loc.column or "",
                        loc.sheet or "",
                        loc.cell_id if loc.cell_id is not None else -1,
                    ),
                )
                for location in locations:
                    result.append(
                        {
                            "cellid_id": location.cell_id,
                            "table": location.table,
                            "row": location.row,
                            "column": location.column,
                            "sheet": location.sheet,
                            "variableid": ctx.operand_ref_map.get(
                                reference.operand_reference_id
                            ),
                        }
                    )
        return result

    def _build_payload(
        self,
        operation_versions: Iterable[OperationVersion],
        ctx: BulkDataContext,
    ) -> List[Dict[str, Any]]:
        payload: List[Dict[str, Any]] = []

        for operation_version in operation_versions:
            operation = operation_version.operation
            if operation is None:
                continue
            if operation.type == "precondition":
                continue
            if (
                not operation_version.expression
                or not operation_version.expression.strip()
            ):
                continue

            operation_references = self._get_operation_info_optimized(
                operation_vid=operation_version.operation_vid,
                ctx=ctx,
            )

            operation_scopes = ctx.scopes_by_opvid.get(
                operation_version.operation_vid,
                [],
            )

            sorted_operation_scopes = sorted(
                operation_scopes,
                key=lambda scope: scope.operation_scope_id,
            )

            operations_scopes_list: List[Dict[str, Any]] = []
            crossmodule = False
            crossmodule_modules: Set[str] = set()
            multiscope = False
            tables = {
                item["table"]
                for item in operation_references
                if item.get("table") is not None
            }
            all_modules: List[str] = []
            seen_scope_keys: Set[Tuple[Tuple[str, str], ...]] = set()

            for operation_scope in sorted_operation_scopes:
                modules = self._process_scope_compositions(
                    scope=operation_scope,
                    ctx=ctx,
                    include_release_info=False,
                )
                scope_key = get_scope_module_key(modules)
                if scope_key in seen_scope_keys:
                    continue
                seen_scope_keys.add(scope_key)

                scope_modules = {
                    str(module["code"])
                    for module in modules
                    if module.get("code") is not None
                }
                all_modules.extend(scope_modules)

                operations_scopes_list.append(
                    {
                        "modules": modules,
                        "operationScopeSeverity": (
                            operation_scope.severity.capitalize()
                            if operation_scope.severity
                            else None
                        ),
                        "isActive": bool(operation_scope.is_active),
                        "applicable": calculate_applicable(modules),
                    }
                )

                if len(scope_modules) > 1:
                    crossmodule = True
                    crossmodule_modules.update(scope_modules)

            unique_modules_across_scopes = set(all_modules)
            if operations_scopes_list:
                first_scope_modules = {
                    str(module.get("code"))
                    for module in operations_scopes_list[0]["modules"]
                    if module.get("code") is not None
                }
                multiscope = len(unique_modules_across_scopes) > len(
                    first_scope_modules
                )

                operations_scopes_list.sort(
                    key=lambda scope: (
                        get_scope_module_key(scope["modules"]),
                        scope.get("operationScopeSeverity") or "",
                        int(bool(scope.get("isActive"))),
                        int(bool(scope.get("applicable"))),
                    )
                )

            multiscope_modules = (
                unique_modules_across_scopes if multiscope else set()
            )

            precondition_data = None
            if operation_version.precondition_operation is not None:
                precondition_data = {
                    "preconditionVID": (
                        operation_version.precondition_operation.operation_vid
                    ),
                    "preconditionExpression": (
                        operation_version.precondition_operation.expression
                    ),
                }

            parent_operation = None
            if operation.group_operation_id is not None:
                parent_operation = ctx.parent_first_versions.get(
                    operation.group_operation_id
                )

            previous_versions_data: List[Dict[str, Any]] = []
            previous_versions = sorted(
                [
                    version
                    for version in ctx.all_versions_by_opid.get(
                        operation_version.operation_id, []
                    )
                    if version.operation_vid != operation_version.operation_vid
                ],
                key=lambda version: version.operation_vid,
            )
            for previous_version in previous_versions:
                previous_scope_list: List[Dict[str, Any]] = []
                seen_previous_scope_keys: Set[Tuple[Tuple[str, str], ...]] = (
                    set()
                )
                previous_scopes = sorted(
                    ctx.scopes_by_opvid.get(
                        previous_version.operation_vid, []
                    ),
                    key=lambda scope: scope.operation_scope_id,
                )
                for previous_scope in previous_scopes:
                    previous_modules = self._process_scope_compositions(
                        scope=previous_scope,
                        ctx=ctx,
                        include_release_info=True,
                    )
                    scope_key = get_scope_module_key(previous_modules)
                    if scope_key in seen_previous_scope_keys:
                        continue
                    seen_previous_scope_keys.add(scope_key)

                    previous_scope_list.append(
                        {
                            "modules": previous_modules,
                            "operationScopeSeverity": (
                                previous_scope.severity.capitalize()
                                if previous_scope.severity
                                else None
                            ),
                            "isActive": bool(previous_scope.is_active),
                            "applicable": calculate_applicable(
                                previous_modules
                            ),
                        }
                    )

                previous_precondition_data = None
                if previous_version.precondition_operation is not None:
                    previous_precondition_data = {
                        "preconditionVID": (
                            previous_version.precondition_operation.operation_vid
                        ),
                        "preconditionExpression": (
                            previous_version.precondition_operation.expression
                        ),
                    }

                previous_parent = None
                if (
                    previous_version.operation is not None
                    and previous_version.operation.group_operation_id
                    is not None
                ):
                    previous_parent = ctx.parent_first_versions.get(
                        previous_version.operation.group_operation_id
                    )

                previous_scope_list.sort(
                    key=lambda scope: (
                        get_scope_module_key(scope["modules"]),
                        scope.get("operationScopeSeverity") or "",
                        int(bool(scope.get("isActive"))),
                        int(bool(scope.get("applicable"))),
                    )
                )

                previous_versions_data.append(
                    {
                        "ID": previous_version.operation_vid,
                        "operationId": previous_version.operation_id,
                        "description": previous_version.description,
                        "expression": previous_version.expression,
                        "operationcode": (
                            previous_version.operation.code
                            if previous_version.operation
                            else None
                        ),
                        "operationsource": (
                            previous_version.operation.source
                            if previous_version.operation
                            else None
                        ),
                        "operationtype": (
                            previous_version.operation.type
                            if previous_version.operation
                            else None
                        ),
                        "endorsement": previous_version.endorsement,
                        "precondition": previous_precondition_data,
                        "startReleaseId": (
                            previous_version.start_release.release_id
                            if previous_version.start_release
                            else None
                        ),
                        "startReleaseCode": (
                            str(previous_version.start_release.code)
                            if previous_version.start_release
                            and previous_version.start_release.code is not None
                            else None
                        ),
                        "endReleaseId": (
                            previous_version.end_release.release_id
                            if previous_version.end_release
                            else None
                        ),
                        "endReleaseCode": (
                            str(previous_version.end_release.code)
                            if previous_version.end_release
                            and previous_version.end_release.code is not None
                            else None
                        ),
                        "parentoperationVID": (
                            previous_parent.operation_vid
                            if previous_parent
                            else None
                        ),
                        "parentoperationexpression": (
                            previous_parent.expression
                            if previous_parent
                            else None
                        ),
                        "operationScopes": previous_scope_list,
                        "operandReferences": self._get_operation_info_optimized(
                            operation_vid=previous_version.operation_vid,
                            ctx=ctx,
                        ),
                    }
                )

            previous_versions_data.sort(key=lambda item: item["ID"])

            owner_concept = operation.concept
            owner_org = owner_concept.owner if owner_concept else None

            payload.append(
                {
                    "ID": operation_version.operation_vid,
                    "operationId": operation_version.operation_id,
                    "description": operation_version.description,
                    "expression": operation_version.expression,
                    "operationcode": operation.code,
                    "searchableOperationCode": create_substrings(
                        operation.code
                    ),
                    "operationsource": operation.source,
                    "operationtype": operation.type,
                    "precondition": precondition_data,
                    "endorsement": operation_version.endorsement,
                    "crossmodule": crossmodule,
                    "crossmodulemodules": sorted(crossmodule_modules),
                    "multiscope": multiscope,
                    "multiscopemodules": sorted(multiscope_modules),
                    "tables": sorted(tables),
                    "startReleaseId": (
                        operation_version.start_release.release_id
                        if operation_version.start_release
                        else None
                    ),
                    "startReleaseCode": (
                        str(operation_version.start_release.code)
                        if operation_version.start_release
                        and operation_version.start_release.code is not None
                        else None
                    ),
                    "endReleaseId": (
                        operation_version.end_release.release_id
                        if operation_version.end_release
                        else None
                    ),
                    "endReleaseCode": (
                        str(operation_version.end_release.code)
                        if operation_version.end_release
                        and operation_version.end_release.code is not None
                        else None
                    ),
                    "ownerAcronym": owner_org.acronym if owner_org else None,
                    "ownerName": owner_org.name if owner_org else None,
                    "versions": previous_versions_data,
                    "parentoperationVID": (
                        parent_operation.operation_vid
                        if parent_operation
                        else None
                    ),
                    "parentoperationexpression": (
                        parent_operation.expression
                        if parent_operation
                        else None
                    ),
                    "operationScopes": operations_scopes_list,
                    "operandReferences": operation_references,
                }
            )

        payload.sort(key=lambda item: item["ID"])

        return payload
