"""Import ECB validation rules from a CSV file into the DPM database."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from hashlib import md5
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import Engine, func
from sqlalchemy.orm import Session, sessionmaker

from dpmcore.dpm_xl.ast.operands import OperandsChecking
from dpmcore.orm.infrastructure import Concept, DpmClass, Organisation, Release
from dpmcore.orm.operations import (
    OperandReference,
    OperandReferenceLocation,
    Operation,
    OperationNode,
    OperationVersion,
)
from dpmcore.orm.rendering import Cell, TableVersion
from dpmcore.services.scope_calculator import ScopeCalculatorService
from dpmcore.services.syntax import SyntaxService

_RELEASE_CODE_MAP = {"3.2": "3.4"}


class EcbValidationsImportError(Exception):
    """Raised when ECB validations cannot be imported."""


@dataclass(frozen=True)
class EcbValidationsImportResult:
    """Outcome of a successful ECB validations import run."""

    operations_created: int
    operation_versions_created: int
    preconditions_created: int
    references_created: int
    scopes_created: int
    scope_compositions_created: int
    warnings: List[str] = field(default_factory=list)


class EcbValidationsImportService:
    """Import ECB validation rules from a CSV export into a DPM database."""

    def __init__(self, engine: Engine) -> None:
        """Initialise the service with a SQLAlchemy engine."""
        self._engine = engine

    def import_csv(self, csv_path: str) -> EcbValidationsImportResult:
        """Parse *csv_path* and persist the ECB validations it contains."""
        path = Path(csv_path)
        if not path.exists():
            raise EcbValidationsImportError(
                f"ECB validations file '{csv_path}' does not exist."
            )
        if not path.is_file():
            raise EcbValidationsImportError(
                f"ECB validations file path '{csv_path}' is not a file."
            )

        import pandas as pd  # lazy

        df = pd.read_csv(
            path, dtype=str, keep_default_na=False, na_values=[""]
        )

        df.columns = df.columns.str.strip().str.lower()

        session = sessionmaker(bind=self._engine)()
        try:
            result = self._import_ecb_validations_df(session, df)
            session.commit()
            return result
        except Exception as exc:
            session.rollback()
            if isinstance(exc, EcbValidationsImportError):
                raise
            raise EcbValidationsImportError(
                f"Failed to import ECB validations from '{csv_path}': {exc}"
            ) from exc
        finally:
            session.close()

    @staticmethod
    def _normalize_text(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        if not text or text.lower() == "nan":
            return None
        return text

    @staticmethod
    def _is_active_value(value: Any) -> int:
        text = str(value).strip().lower()
        return -1 if text in {"active", "yes", "-1", "true", "1"} else 0

    @staticmethod
    def _parse_submission_date(value: Any) -> Optional[date]:
        text = EcbValidationsImportService._normalize_text(value)
        if text is None or text == "-":
            return None
        for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, fmt).date()  # noqa: DTZ007
            except ValueError:  # noqa: PERF203
                continue
        raise EcbValidationsImportError(
            f"Unsupported submission date {value!r}"
        )

    @staticmethod
    def _is_parent_operation_code(code: str) -> bool:
        return re.search(r"_\d+$", code) is None

    @staticmethod
    def _get_parent_operation_code(code: str) -> Optional[str]:
        match = re.match(r"^(.+)_\d+$", code)
        return match.group(1) if match else None

    @staticmethod
    def _next_int_id(session: Session, model: Any, attr_name: str) -> int:
        column = getattr(model, attr_name)
        current = session.query(func.max(column)).scalar()
        return int(current or 0) + 1

    def _create_operation_concept(
        self,
        session: Session,
        *,
        operation_class: Optional[DpmClass],
        owner: Optional[Organisation],
    ) -> Optional[str]:
        if operation_class is None or owner is None:
            return None

        concept_guid = str(uuid.uuid4())
        session.add(
            Concept(
                concept_guid=concept_guid,
                class_id=operation_class.class_id,
                owner_id=owner.org_id,
            )
        )
        return concept_guid

    def _get_or_create_ecb_organisation(
        self, session: Session
    ) -> Organisation:
        org = (
            session.query(Organisation)
            .filter(Organisation.acronym == "ECB")
            .one_or_none()
        )
        if org is not None:
            return org

        next_org_id = self._next_int_id(session, Organisation, "org_id")
        max_prefix = session.query(func.max(Organisation.id_prefix)).scalar()

        org = Organisation(
            org_id=next_org_id,
            name="European Central Bank",
            acronym="ECB",
            id_prefix=int(max_prefix or 0) + 1,
        )
        session.add(org)
        session.flush()
        return org

    @staticmethod
    def _resolve_release(
        release_cache: Dict[str, Release], raw_value: Any
    ) -> Optional[Release]:
        text = EcbValidationsImportService._normalize_text(raw_value)
        if text is None:
            return None
        return release_cache.get(_RELEASE_CODE_MAP.get(text, text))

    @staticmethod
    def _get_valid_release_ids(
        session: Session,
        *,
        start_release_id: int,
        end_release_id: Optional[int],
    ) -> List[int]:
        """Release IDs in [start, end) ordered by semver sort_order.

        Comparison runs against ``Release.sort_order`` so backports
        (e.g. a hypothetical ``4.0.1`` post-``4.2.1``) place correctly
        within their version lineage. The start/end bounds are
        resolved to integer ``sort_order`` values once before the main
        query rather than via correlated subqueries.
        """
        start_sort = (
            session.query(Release.sort_order)
            .filter(Release.release_id == start_release_id)
            .scalar()
        )
        if start_sort is None:
            raise EcbValidationsImportError(
                f"Release {start_release_id} has no sort_order — its "
                "code could not be parsed as MAJOR.MINOR[.PATCH]."
            )
        query = (
            session.query(Release.release_id)
            .filter(Release.sort_order >= start_sort)
            .order_by(Release.sort_order)
        )
        if end_release_id is not None:
            end_sort = (
                session.query(Release.sort_order)
                .filter(Release.release_id == end_release_id)
                .scalar()
            )
            if end_sort is None:
                raise EcbValidationsImportError(
                    f"Release {end_release_id} has no sort_order — "
                    "its code could not be parsed as "
                    "MAJOR.MINOR[.PATCH]."
                )
            query = query.filter(Release.sort_order < end_sort)
        return [row[0] for row in query.all()]

    def _collect_table_codes_from_ast(self, node: Any) -> Set[str]:
        table_codes: Set[str] = set()

        def visit(obj: Any) -> None:
            if obj is None:
                return

            table = getattr(obj, "table", None)
            is_table_group = getattr(obj, "is_table_group", False)
            if isinstance(table, str) and table and not is_table_group:
                table_codes.add(table)

            if not hasattr(obj, "__dict__"):
                return

            for value in vars(obj).values():
                if isinstance(value, list):
                    for item in value:
                        visit(item)
                else:
                    visit(value)

        visit(node)
        return table_codes

    def _extract_table_codes_for_expression(
        self,
        session: Session,
        *,
        expression: Optional[str],
        start_release_id: int,
        latest_release_id: Optional[int],
    ) -> Set[str]:
        if expression is None or not str(expression).strip():
            return set()

        syntax = SyntaxService()
        ast = syntax.parse(str(expression))

        def try_with_release(release_id: Optional[int]) -> Set[str]:
            if release_id is None:
                return set()

            checker = OperandsChecking(
                session=session,
                expression=str(expression),
                ast=ast,
                release_id=release_id,
            )
            return set(checker.tables.keys())

        try:
            table_codes = try_with_release(start_release_id)
        except Exception:
            table_codes = set()

        if not table_codes and latest_release_id not in {
            None,
            start_release_id,
        }:
            try:
                table_codes = try_with_release(latest_release_id)
            except Exception:
                table_codes = set()

        return table_codes

    @staticmethod
    def _table_version_for_release_query(query: Any, release_id: int) -> Any:
        return query.filter(
            TableVersion.start_release_id <= release_id,
            func.coalesce(TableVersion.end_release_id, 999999999) > release_id,
        )

    def _find_table_version(
        self, session: Session, *, table_code: str
    ) -> Optional[TableVersion]:
        return (
            session.query(TableVersion)
            .filter(TableVersion.code == table_code)
            .order_by(TableVersion.start_release_id.asc())
            .first()
        )

    def _create_table_references(
        self, session: Session, *, operation_vid: int, table_codes: Set[str]
    ) -> int:
        if not table_codes:
            return 0

        next_node_id = self._next_int_id(session, OperationNode, "node_id")
        next_ref_id = self._next_int_id(
            session, OperandReference, "operand_reference_id"
        )

        node = OperationNode(
            node_id=next_node_id,
            operation_vid=operation_vid,
            use_interval_arithmetics=False,
            is_leaf=True,
        )
        session.add(node)

        created = 0
        for table_code in sorted(table_codes):
            table_version = self._find_table_version(
                session, table_code=table_code
            )
            if table_version is None or table_version.table_id is None:
                continue

            cell = (
                session.query(Cell)
                .filter(Cell.table_id == table_version.table_id)
                .order_by(Cell.cell_id)
                .first()
            )

            ref = OperandReference(
                operand_reference_id=next_ref_id,
                node_id=next_node_id,
                operand_reference=table_code,
            )
            session.add(ref)
            session.add(
                OperandReferenceLocation(
                    operand_reference_id=next_ref_id,
                    cell_id=cell.cell_id if cell is not None else None,
                    table=table_code,
                )
            )

            next_ref_id += 1
            created += 1

        return created

    def _get_or_create_precondition_version(
        self,
        session: Session,
        *,
        expression: Any,
        release: Release,
        operation_class: Optional[DpmClass],
        owner: Optional[Organisation],
        counters: Dict[str, int],
        cache: Dict[tuple[str, int], int],
    ) -> tuple[Optional[int], int]:
        text = self._normalize_text(expression)
        if text is None:
            return None, 0

        cache_key = (text, release.release_id)
        if cache_key in cache:
            return cache[cache_key], 0

        precondition_code = (
            "precond_EGDQ_"
            + md5(text.encode(), usedforsecurity=False).hexdigest()[:8]
        )
        operation = (
            session.query(Operation)
            .filter(
                Operation.code == precondition_code,
                Operation.type == "precondition",
            )
            .one_or_none()
        )

        created_count = 0
        if operation is None:
            concept_guid = self._create_operation_concept(
                session,
                operation_class=operation_class,
                owner=owner,
            )
            operation = Operation(
                operation_id=counters["operation_id"],
                code=precondition_code,
                type="precondition",
                source="user_defined",
                row_guid=concept_guid,
                owner_id=owner.org_id if owner is not None else None,
            )
            session.add(operation)
            counters["operation_id"] += 1

        existing_version = (
            session.query(OperationVersion)
            .filter(
                OperationVersion.operation_id == operation.operation_id,
                OperationVersion.start_release_id == release.release_id,
                OperationVersion.expression == text,
            )
            .one_or_none()
        )
        if existing_version is not None:
            cache[cache_key] = existing_version.operation_vid
            return existing_version.operation_vid, 0

        op_version = OperationVersion(
            operation_vid=counters["operation_vid"],
            operation_id=operation.operation_id,
            start_release_id=release.release_id,
            expression=text,
            description=f"Precondition: {text}",
        )
        session.add(op_version)
        cache[cache_key] = counters["operation_vid"]
        counters["operation_vid"] += 1
        created_count += 1

        return op_version.operation_vid, created_count

    def _import_ecb_validations_df(  # noqa: C901
        self, session: Session, df: Any
    ) -> EcbValidationsImportResult:
        required_columns = {"vr_code", "start_release"}
        missing = required_columns - set(df.columns)
        if missing:
            raise EcbValidationsImportError(
                "ECB validations file is missing required"
                f" columns: {sorted(missing)}"
            )

        ecb_org = self._get_or_create_ecb_organisation(session)
        operation_class = (
            session.query(DpmClass)
            .filter(DpmClass.name == "Operation")
            .one_or_none()
        )

        releases = session.query(Release).all()
        release_cache = {
            str(release.code).strip(): release
            for release in releases
            if release.code is not None
        }
        latest_release_id = max(
            (release.release_id for release in releases),
            default=None,
        )

        warnings: List[str] = []
        counters = {
            "operation_id": self._next_int_id(
                session, Operation, "operation_id"
            ),
            "operation_vid": self._next_int_id(
                session,
                OperationVersion,
                "operation_vid",
            ),
        }
        operations_created = 0
        versions_created = 0
        preconditions_created = 0
        references_created = 0
        scopes_created = 0
        compositions_created = 0

        unique_codes: Set[str] = set()
        for raw_code in df["vr_code"].tolist():
            code = self._normalize_text(raw_code)
            if code is None:
                continue
            unique_codes.add(code)
            parent_code = self._get_parent_operation_code(code)
            if parent_code is not None:
                unique_codes.add(parent_code)

        operations_by_code: Dict[str, Operation] = {}
        for code in sorted(unique_codes):
            existing = (
                session.query(Operation)
                .filter(Operation.code == code)
                .one_or_none()
            )
            if existing is not None:
                operations_by_code[code] = existing
                continue

            concept_guid = self._create_operation_concept(
                session,
                operation_class=operation_class,
                owner=ecb_org,
            )
            operation = Operation(
                operation_id=counters["operation_id"],
                code=code,
                type="validation",
                source="user_defined",
                row_guid=concept_guid,
                owner_id=ecb_org.org_id,
            )
            session.add(operation)
            operations_by_code[code] = operation
            counters["operation_id"] += 1
            operations_created += 1

        session.flush()

        for code, operation in operations_by_code.items():
            if self._is_parent_operation_code(code):
                continue
            parent_code = self._get_parent_operation_code(code)
            if parent_code and parent_code in operations_by_code:
                operation.group_operation_id = operations_by_code[
                    parent_code
                ].operation_id

        session.flush()

        precondition_cache: Dict[tuple[str, int], int] = {}
        created_versions: Dict[tuple[str, int], OperationVersion] = {}

        for row in df.to_dict(orient="records"):
            code = self._normalize_text(row.get("vr_code"))
            if code is None:
                continue

            release = self._resolve_release(
                release_cache, row.get("start_release")
            )
            if release is None:
                warnings.append(
                    f"Skipping validation '{code}': release "
                    f"{row.get('start_release')!r} not found"
                )
                continue

            version_key = (code, release.release_id)
            if version_key in created_versions:
                continue

            if code not in operations_by_code:
                continue
            operation = operations_by_code[code]

            end_release = self._resolve_release(
                release_cache,
                row.get("end_release"),
            )

            precondition_vid, precondition_created = (
                self._get_or_create_precondition_version(
                    session,
                    expression=row.get("precondition"),
                    release=release,
                    operation_class=operation_class,
                    owner=ecb_org,
                    counters=counters,
                    cache=precondition_cache,
                )
            )
            preconditions_created += precondition_created

            expression = self._normalize_text(row.get("expression")) or ""
            description = self._normalize_text(row.get("description"))

            existing_version = (
                session.query(OperationVersion)
                .filter(
                    OperationVersion.operation_id == operation.operation_id,
                    OperationVersion.start_release_id == release.release_id,
                )
                .one_or_none()
            )
            if existing_version is not None:
                created_versions[version_key] = existing_version
                continue

            operation_version = OperationVersion(
                operation_vid=counters["operation_vid"],
                operation_id=operation.operation_id,
                precondition_operation_vid=precondition_vid,
                start_release_id=release.release_id,
                end_release_id=(
                    end_release.release_id if end_release is not None else None
                ),
                expression=expression,
                description=description,
            )
            session.add(operation_version)
            created_versions[version_key] = operation_version
            counters["operation_vid"] += 1
            versions_created += 1

            table_codes = self._extract_table_codes_for_expression(
                session,
                expression=expression,
                start_release_id=release.release_id,
                latest_release_id=latest_release_id,
            )
            references_created += self._create_table_references(
                session,
                operation_vid=operation_version.operation_vid,
                table_codes=table_codes,
            )

            session.flush()

            if expression:
                valid_release_ids = self._get_valid_release_ids(
                    session,
                    start_release_id=release.release_id,
                    end_release_id=(
                        end_release.release_id
                        if end_release is not None
                        else None
                    ),
                )
                active_value = self._is_active_value(row.get("is_active"))
                severity_value = (
                    self._normalize_text(row.get("severity")) or "warning"
                ).lower()
                submission_date = self._parse_submission_date(
                    row.get("from_submission_date")
                )

                for release_id in valid_release_ids:
                    scope_result = ScopeCalculatorService(
                        session
                    ).calculate_from_expression(
                        expression=expression,
                        release_id=release_id,
                    )
                    if scope_result.has_error:
                        warnings.append(
                            f"Scope calculation failed for '{code}' in"
                            f" release {release_id}:"
                            f" {scope_result.error_message}"
                        )
                        continue

                    for scope in scope_result.scopes:
                        scope.operation_vid = operation_version.operation_vid
                        scope.is_active = active_value
                        scope.severity = severity_value
                        scope.from_submission_date = submission_date
                        session.add(scope)
                        for comp in scope.operation_scope_compositions:
                            session.add(comp)
                            compositions_created += 1
                        scopes_created += 1

                    session.flush()

        return EcbValidationsImportResult(
            operations_created=operations_created,
            operation_versions_created=versions_created,
            preconditions_created=preconditions_created,
            references_created=references_created,
            scopes_created=scopes_created,
            scope_compositions_created=compositions_created,
            warnings=warnings,
        )
