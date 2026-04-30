"""Query functions for the DPM-XL engine.

Provides standalone query functions and query classes that
replicate the class methods previously embedded in the old
``py_dpm.dpm.models`` ORM models.  All functions accept a
SQLAlchemy *session* as first positional argument and use the
legacy ``session.query()`` API for compatibility.
"""

from __future__ import annotations

import warnings
from typing import (
    TYPE_CHECKING,
    Any,
    Hashable,
    Sequence,
)

import pandas as pd
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import aliased

from dpmcore.orm.glossary import (
    Item,
    ItemCategory,
    Property,
)
from dpmcore.orm.infrastructure import (
    DataType,
    Release,
)
from dpmcore.orm.operations import (
    Operation,
    OperationScope,
    OperationScopeComposition,
    OperationVersion,
    Operator,
    OperatorArgument,
)
from dpmcore.orm.packaging import (
    ModuleParameters,
    ModuleVersion,
    ModuleVersionComposition,
)
from dpmcore.orm.rendering import (
    Cell,
    HeaderVersion,
    TableVersion,
    TableVersionCell,
    TableVersionHeader,
)
from dpmcore.orm.variables import (
    KeyComposition,
    Variable,
    VariableVersion,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Query, Session

# ------------------------------------------------------------------ #
# Helper utilities
# ------------------------------------------------------------------ #


def _get_engine_cache_key(session: "Session") -> Hashable:
    """Return a hashable key that identifies the engine.

    Args:
        session: SQLAlchemy session.

    Returns:
        A hashable value derived from the bound engine URL.
    """
    bind = session.get_bind()
    return getattr(bind, "url", repr(bind))


def read_sql_with_connection(
    sql: str,
    session: "Session",
) -> pd.DataFrame:
    """Execute ``pd.read_sql`` with proper connection handling.

    Uses the raw DBAPI connection to avoid the pandas 2.x
    deprecation warning about ``DBAPI2`` connections.

    Args:
        sql: Compiled SQL string.
        session: SQLAlchemy session.

    Returns:
        DataFrame with query results.
    """
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=".*pandas only supports SQLAlchemy.*",
            category=UserWarning,
        )
        # pandas accepts DBAPI2 connections at runtime; its type stubs
        # only advertise SQLAlchemy Connection so we sidestep the mismatch.
        raw_conn: Any = session.connection().connection
        return pd.read_sql(sql, raw_conn)


def compile_query_for_pandas(
    query_statement: Any,
    session: "Session",
) -> str:
    """Compile a query statement to a SQL string.

    Performs literal-bind compilation so that the resulting
    string can be fed directly to ``pd.read_sql``.

    Args:
        query_statement: SQLAlchemy statement object.
        session: SQLAlchemy session.

    Returns:
        Compiled SQL string.
    """
    return str(
        query_statement.compile(
            dialect=session.get_bind().dialect,
            compile_kwargs={"literal_binds": True},
        )
    )


# ------------------------------------------------------------------ #
# Private helpers
# ------------------------------------------------------------------ #


def _filter_elements(
    query: "Query[Any]",
    # column is either a SQLAlchemy ColumnElement or an InstrumentedAttribute
    # on an ORM model; they do not share a typed base, so we accept Any here.
    column: Any,
    values: Sequence[str],
) -> "Query[Any]":
    """Apply flexible element filtering (single, range, list).

    Args:
        query: SQLAlchemy query.
        column: Column to filter on.
        values: List of filter values (may include ranges).

    Returns:
        Filtered query.
    """
    if len(values) == 1:
        if values[0] == "*":
            return query.filter(column.is_not(None))
        elif "-" in values[0]:
            limits = values[0].split("-")
            return query.filter(column.between(limits[0], limits[1]))
        else:
            return query.filter(column == values[0])
    range_control = any("-" in x for x in values)
    if not range_control:
        return query.filter(column.in_(values))
    dynamic_filter: list[Any] = []
    for x in values:
        if "-" in x:
            limits = x.split("-")
            dynamic_filter.append(column.between(limits[0], limits[1]))
        else:
            dynamic_filter.append(column == x)
    return query.filter(or_(*dynamic_filter))


def _check_ranges_values_are_present(
    data: pd.DataFrame,
    data_column: str,
    values: Sequence[str] | None,
) -> pd.DataFrame:
    """Validate range boundaries exist in returned data.

    Args:
        data: DataFrame from the query.
        data_column: Column name to validate.
        values: Filter values (may contain ranges).

    Returns:
        Original data if valid, empty DataFrame otherwise.
    """
    if values is None or len(values) == 0:
        return data
    actual_values = list(data[data_column].values)
    for value in values:
        if "-" in value:
            limits = value.split("-")
            if (
                limits[0] not in actual_values
                or limits[1] not in actual_values
            ):
                return pd.DataFrame(columns=data.columns)
    return data


def _old_filter_by_release(
    query: "Query[Any]",
    # start/end_release are ORM InstrumentedAttributes; see _filter_elements.
    start_release: Any,
    end_release: Any,
    release_id: int | None,
) -> "Query[Any]":
    """Legacy release filter (inlined from old models).

    Args:
        query: SQLAlchemy query.
        start_release: Start release column.
        end_release: End release column.
        release_id: Release ID or None.

    Returns:
        Filtered query.
    """
    if release_id is None:
        return query.filter(end_release.is_(None))
    return query.filter(
        and_(
            start_release <= release_id,
            or_(
                end_release > release_id,
                end_release.is_(None),
            ),
        )
    )


# ------------------------------------------------------------------ #
# ItemCategory queries
# ------------------------------------------------------------------ #


class ItemCategoryQuery:
    """Query helpers around the ItemCategory model."""

    @staticmethod
    def get_items(
        session: "Session",
        items: Sequence[str],
        release_id: int | None = None,
    ) -> pd.DataFrame:
        """Get ItemCategory records for item signatures.

        Args:
            session: SQLAlchemy session.
            items: List of item signatures.
            release_id: Optional release filter.

        Returns:
            DataFrame with Signature, Code, CategoryID.
        """
        query = session.query(
            ItemCategory.signature.label("Signature"),
            ItemCategory.code.label("Code"),
            ItemCategory.category_id.label("CategoryID"),
        )
        if items:
            query = query.filter(ItemCategory.signature.in_(items))
        if release_id is not None:
            query = query.filter(
                and_(
                    ItemCategory.start_release_id <= release_id,
                    or_(
                        ItemCategory.end_release_id > release_id,
                        ItemCategory.end_release_id.is_(None),
                    ),
                )
            )
        else:
            query = query.filter(ItemCategory.end_release_id.is_(None))
        result = query.all()
        if result:
            return pd.DataFrame(
                [
                    {
                        "Signature": r.Signature,
                        "Code": r.Code,
                        "CategoryID": r.CategoryID,
                    }
                    for r in result
                ]
            )
        return pd.DataFrame(columns=["Signature", "Code", "CategoryID"])

    @staticmethod
    def get_property_from_code(
        code: str,
        session: "Session",
    ) -> ItemCategory | None:
        """Look up an ItemCategory by its code.

        Args:
            code: Item category code.
            session: SQLAlchemy session.

        Returns:
            ItemCategory instance or None.
        """
        return (
            session.query(ItemCategory)
            .filter(ItemCategory.code == code)
            .first()
        )

    @staticmethod
    def get_property_id_from_code(
        code: str,
        session: "Session",
    ) -> list[int]:
        """Return item IDs matching a category code.

        Args:
            code: Item category code.
            session: SQLAlchemy session.

        Returns:
            List of item_id values.
        """
        rows = (
            session.query(ItemCategory.item_id)
            .filter(ItemCategory.code == code)
            .all()
        )
        return [r.item_id for r in rows]

    @staticmethod
    def get_item_category_id_from_signature(
        signature: str,
        session: "Session",
    ) -> list[int]:
        """Return item IDs matching a signature.

        Args:
            signature: Item category signature.
            session: SQLAlchemy session.

        Returns:
            List of item_id values.
        """
        rows = (
            session.query(ItemCategory.item_id)
            .filter(ItemCategory.signature == signature)
            .all()
        )
        return [r.item_id for r in rows]


# ------------------------------------------------------------------ #
# VariableVersion queries
# ------------------------------------------------------------------ #


class VariableVersionQuery:
    """Query helpers around the VariableVersion model."""

    @staticmethod
    def check_variable_exists(
        session: "Session",
        variable_code: str,
        release_id: int | None = None,
    ) -> bool:
        """Check whether a variable code exists.

        Args:
            session: SQLAlchemy session.
            variable_code: Code to look up.
            release_id: Optional release filter.

        Returns:
            True if the variable exists.
        """
        query = session.query(VariableVersion).filter(
            VariableVersion.code == variable_code
        )
        if release_id is not None:
            query = query.filter(
                and_(
                    VariableVersion.start_release_id <= release_id,
                    or_(
                        VariableVersion.end_release_id > release_id,
                        VariableVersion.end_release_id.is_(None),
                    ),
                )
            )
        else:
            query = query.filter(VariableVersion.end_release_id.is_(None))
        return query.first() is not None

    @staticmethod
    def check_precondition(
        session: "Session",
        variable_code: str,
        release_id: int | None,
    ) -> Any | None:
        """Find a filing-indicator variable by code.

        Looks for a VariableVersion whose code matches
        *variable_code* and whose Variable type is
        ``'Filing Indicator'``.

        Args:
            session: SQLAlchemy session.
            variable_code: Variable code.
            release_id: Release filter.

        Returns:
            Named-tuple row with VariableID and Code,
            or None.
        """
        query = (
            session.query(
                Variable.variable_id.label("VariableID"),
                VariableVersion.code.label("Code"),
            )
            .join(
                Variable,
                VariableVersion.variable_id == Variable.variable_id,
            )
            .filter(
                VariableVersion.code == variable_code,
                Variable.type == "Filing Indicator",
            )
        )
        if release_id is not None:
            query = query.filter(
                and_(
                    VariableVersion.start_release_id <= release_id,
                    or_(
                        VariableVersion.end_release_id > release_id,
                        VariableVersion.end_release_id.is_(None),
                    ),
                )
            )
        return query.first()

    @staticmethod
    def get_variable_id(
        session: "Session",
        value: str,
        release_id: int | None,
    ) -> list[int] | None:
        """Get variable IDs by code within a release.

        Args:
            session: SQLAlchemy session.
            value: Variable code.
            release_id: Release filter.

        Returns:
            List of variable_id values, or None.
        """
        query = session.query(VariableVersion.variable_id).filter(
            VariableVersion.code == value
        )
        if release_id is not None:
            query = query.filter(
                and_(
                    VariableVersion.start_release_id <= release_id,
                    or_(
                        VariableVersion.end_release_id > release_id,
                        VariableVersion.end_release_id.is_(None),
                    ),
                )
            )
        rows = query.all()
        if not rows:
            return None
        return [r.variable_id for r in rows]

    @staticmethod
    def get_variable_vids_by_codes(
        session: "Session",
        codes: list[str],
        release_id: int | None = None,
    ) -> dict[str, dict[str, int]]:
        """Batch-resolve variable codes to ``(variable_id, variable_vid)``.

        Args:
            session: SQLAlchemy session.
            codes: Variable codes to resolve.
            release_id: Optional release window filter.

        Returns:
            ``{variable_code: {"variable_id": int, "variable_vid": int}}``
            for codes that resolve. Codes that don't resolve are
            silently omitted.
        """
        if not codes:
            return {}
        query = session.query(
            VariableVersion.code,
            VariableVersion.variable_id,
            VariableVersion.variable_vid,
        ).filter(VariableVersion.code.in_(codes))
        if release_id is not None:
            query = query.filter(
                and_(
                    VariableVersion.start_release_id <= release_id,
                    or_(
                        VariableVersion.end_release_id > release_id,
                        VariableVersion.end_release_id.is_(None),
                    ),
                )
            )
        rows = query.all()
        resolved: dict[str, dict[str, int]] = {}
        for row in rows:
            code = row.code
            if not code or code in resolved:
                continue
            resolved[code] = {
                "variable_id": int(row.variable_id),
                "variable_vid": int(row.variable_vid),
            }
        return resolved

    @staticmethod
    def get_all_preconditions(
        session: "Session",
        release_id: int | None,
    ) -> list[Any]:
        """Return all filing-indicator variables.

        Args:
            session: SQLAlchemy session.
            release_id: Release filter.

        Returns:
            List of named-tuple rows (VariableID, Code).
        """
        query = (
            session.query(
                Variable.variable_id.label("VariableID"),
                VariableVersion.code.label("Code"),
            )
            .join(
                Variable,
                VariableVersion.variable_id == Variable.variable_id,
            )
            .filter(Variable.type == "Filing Indicator")
        )
        if release_id is not None:
            query = query.filter(
                and_(
                    VariableVersion.start_release_id <= release_id,
                    or_(
                        VariableVersion.end_release_id > release_id,
                        VariableVersion.end_release_id.is_(None),
                    ),
                )
            )
        return query.all()


# ------------------------------------------------------------------ #
# Operation queries
# ------------------------------------------------------------------ #


class OperationQuery:
    """Query helpers around Operation / OperationVersion."""

    @staticmethod
    def get_operations_from_codes(
        session: "Session",
        operation_codes: Sequence[str],
        release_id: int | None,
    ) -> pd.DataFrame:
        """Retrieve operations matching a list of codes.

        Args:
            session: SQLAlchemy session.
            operation_codes: Codes to look up.
            release_id: Release filter.

        Returns:
            DataFrame with OperationVID, Code,
            Expression, StartReleaseID, EndReleaseID.
        """
        query = (
            session.query(
                OperationVersion.operation_vid.label("OperationVID"),
                Operation.code.label("Code"),
                OperationVersion.expression.label("Expression"),
                OperationVersion.start_release_id.label("StartReleaseID"),
                OperationVersion.end_release_id.label("EndReleaseID"),
            )
            .join(
                Operation,
                OperationVersion.operation_id == Operation.operation_id,
            )
            .filter(Operation.code.in_(operation_codes))
        )
        if release_id is not None:
            query = query.filter(
                and_(
                    OperationVersion.start_release_id <= release_id,
                    or_(
                        OperationVersion.end_release_id > release_id,
                        OperationVersion.end_release_id.is_(None),
                    ),
                )
            )
        results = query.all()
        cols = [
            "OperationVID",
            "Code",
            "Expression",
            "StartReleaseID",
            "EndReleaseID",
        ]
        return pd.DataFrame(results, columns=cols)


# ------------------------------------------------------------------ #
# TableVersion queries
# ------------------------------------------------------------------ #


class TableVersionQuery:
    """Query helpers around the TableVersion model."""

    @staticmethod
    def check_table_exists(
        session: "Session",
        table_code: str,
        release_id: int | None,
    ) -> bool:
        """Check whether a table code exists.

        Args:
            session: SQLAlchemy session.
            table_code: Table version code.
            release_id: Release filter.

        Returns:
            True if the table exists.
        """
        query = session.query(TableVersion).filter(
            TableVersion.code == table_code
        )
        if release_id is not None:
            query = query.filter(
                and_(
                    TableVersion.start_release_id <= release_id,
                    or_(
                        TableVersion.end_release_id > release_id,
                        TableVersion.end_release_id.is_(None),
                    ),
                )
            )
        return query.first() is not None


# ------------------------------------------------------------------ #
# Operator / OperatorArgument queries
# ------------------------------------------------------------------ #


class OperatorQuery:
    """Query helpers for Operator and OperatorArgument."""

    @staticmethod
    def get_operators(
        session: "Session",
    ) -> pd.DataFrame:
        """Return all operators as a DataFrame.

        Args:
            session: SQLAlchemy session.

        Returns:
            DataFrame with OperatorID, Name, Symbol,
            Type.
        """
        query = session.query(
            Operator.operator_id.label("OperatorID"),
            Operator.name.label("Name"),
            Operator.symbol.label("Symbol"),
            Operator.type.label("Type"),
        )
        results = query.all()
        return pd.DataFrame(
            results,
            columns=[
                "OperatorID",
                "Name",
                "Symbol",
                "Type",
            ],
        )

    @staticmethod
    def get_arguments(
        session: "Session",
    ) -> pd.DataFrame:
        """Return all operator arguments as a DataFrame.

        Args:
            session: SQLAlchemy session.

        Returns:
            DataFrame with ArgumentID, OperatorID,
            Order, IsMandatory, Name.
        """
        query = session.query(
            OperatorArgument.argument_id.label("ArgumentID"),
            OperatorArgument.operator_id.label("OperatorID"),
            OperatorArgument.order.label("Order"),
            OperatorArgument.is_mandatory.label("IsMandatory"),
            OperatorArgument.name.label("Name"),
        )
        results = query.all()
        return pd.DataFrame(
            results,
            columns=[
                "ArgumentID",
                "OperatorID",
                "Order",
                "IsMandatory",
                "Name",
            ],
        )


# ------------------------------------------------------------------ #
# ModuleVersion queries
# ------------------------------------------------------------------ #


class ModuleVersionQuery:
    """Query helpers around ModuleVersion."""

    @staticmethod
    def get_last_release(
        session: "Session",
    ) -> int | None:
        """Return the highest release ID.

        Args:
            session: SQLAlchemy session.

        Returns:
            Integer release ID, or None.
        """
        result = session.query(func.max(Release.release_id)).scalar()
        if result is None:
            return None
        return int(result)

    @staticmethod
    def get_from_tables_vids(
        session: "Session",
        tables_vids: Sequence[int],
        release_id: int | None = None,
    ) -> pd.DataFrame:
        """Query modules containing given table VIDs.

        Args:
            session: SQLAlchemy session.
            tables_vids: List of TableVID integers.
            release_id: Optional release filter.

        Returns:
            DataFrame with module version info.
        """
        cols = [
            "ModuleVID",
            "variable_vid",
            "ModuleCode",
            "VersionNumber",
            "FromReferenceDate",
            "ToReferenceDate",
            "StartReleaseID",
            "EndReleaseID",
        ]
        if not tables_vids:
            return pd.DataFrame(columns=cols)

        query = (
            session.query(
                ModuleVersion.module_vid.label("ModuleVID"),
                ModuleVersionComposition.table_vid.label("variable_vid"),
                ModuleVersion.code.label("ModuleCode"),
                ModuleVersion.version_number.label("VersionNumber"),
                ModuleVersion.from_reference_date.label("FromReferenceDate"),
                ModuleVersion.to_reference_date.label("ToReferenceDate"),
                ModuleVersion.start_release_id.label("StartReleaseID"),
                ModuleVersion.end_release_id.label("EndReleaseID"),
            )
            .join(
                ModuleVersionComposition,
                ModuleVersion.module_vid
                == ModuleVersionComposition.module_vid,
            )
            .filter(ModuleVersionComposition.table_vid.in_(tables_vids))
        )
        if release_id is not None:
            query = query.filter(
                and_(
                    ModuleVersion.start_release_id <= release_id,
                    or_(
                        ModuleVersion.end_release_id > release_id,
                        ModuleVersion.end_release_id.is_(None),
                    ),
                )
            )
        results = query.all()
        df = pd.DataFrame(results, columns=cols)
        return _apply_fallback_for_equal_dates(session, df)

    @staticmethod
    def get_from_table_codes(
        session: "Session",
        table_codes: Sequence[str],
        release_id: int | None = None,
    ) -> pd.DataFrame:
        """Query modules by table codes.

        Args:
            session: SQLAlchemy session.
            table_codes: List of table codes.
            release_id: Optional release filter.

        Returns:
            DataFrame with module version info.
        """
        cols = [
            "ModuleVID",
            "variable_vid",
            "ModuleCode",
            "VersionNumber",
            "FromReferenceDate",
            "ToReferenceDate",
            "StartReleaseID",
            "EndReleaseID",
            "TableCode",
        ]
        if not table_codes:
            return pd.DataFrame(columns=cols)

        query = (
            session.query(
                ModuleVersion.module_vid.label("ModuleVID"),
                ModuleVersionComposition.table_vid.label("variable_vid"),
                ModuleVersion.code.label("ModuleCode"),
                ModuleVersion.version_number.label("VersionNumber"),
                ModuleVersion.from_reference_date.label("FromReferenceDate"),
                ModuleVersion.to_reference_date.label("ToReferenceDate"),
                ModuleVersion.start_release_id.label("StartReleaseID"),
                ModuleVersion.end_release_id.label("EndReleaseID"),
                TableVersion.code.label("TableCode"),
            )
            .join(
                ModuleVersionComposition,
                ModuleVersion.module_vid
                == ModuleVersionComposition.module_vid,
            )
            .join(
                TableVersion,
                ModuleVersionComposition.table_vid == TableVersion.table_vid,
            )
            .filter(TableVersion.code.in_(table_codes))
        )
        if release_id is not None:
            query = query.filter(
                and_(
                    ModuleVersion.start_release_id <= release_id,
                    or_(
                        ModuleVersion.end_release_id > release_id,
                        ModuleVersion.end_release_id.is_(None),
                    ),
                )
            )
        results = query.all()
        df = pd.DataFrame(results, columns=cols)
        return _apply_fallback_for_equal_dates(session, df)

    @staticmethod
    def get_precondition_module_versions(
        session: "Session",
        precondition_items: Sequence[str],
        release_id: int | None = None,
    ) -> pd.DataFrame:
        """Query modules for precondition items.

        Args:
            session: SQLAlchemy session.
            precondition_items: Filing indicator codes.
            release_id: Optional release filter.

        Returns:
            DataFrame with module version info.
        """
        cols = [
            "ModuleVID",
            "variable_vid",
            "ModuleCode",
            "VersionNumber",
            "FromReferenceDate",
            "ToReferenceDate",
            "StartReleaseID",
            "EndReleaseID",
            "Code",
        ]
        if not precondition_items:
            return pd.DataFrame(columns=cols)

        query = (
            session.query(
                ModuleVersion.module_vid.label("ModuleVID"),
                VariableVersion.variable_vid.label("variable_vid"),
                ModuleVersion.code.label("ModuleCode"),
                ModuleVersion.version_number.label("VersionNumber"),
                ModuleVersion.from_reference_date.label("FromReferenceDate"),
                ModuleVersion.to_reference_date.label("ToReferenceDate"),
                ModuleVersion.start_release_id.label("StartReleaseID"),
                ModuleVersion.end_release_id.label("EndReleaseID"),
                VariableVersion.code.label("Code"),
            )
            .join(
                ModuleParameters,
                ModuleVersion.module_vid == ModuleParameters.module_vid,
            )
            .join(
                VariableVersion,
                ModuleParameters.variable_vid == VariableVersion.variable_vid,
            )
            .join(
                Variable,
                VariableVersion.variable_id == Variable.variable_id,
            )
            .filter(VariableVersion.code.in_(precondition_items))
            .filter(Variable.type == "Filing Indicator")
        )
        if release_id is not None:
            query = query.filter(
                and_(
                    ModuleVersion.start_release_id <= release_id,
                    or_(
                        ModuleVersion.end_release_id > release_id,
                        ModuleVersion.end_release_id.is_(None),
                    ),
                )
            )
        results = query.all()
        df = pd.DataFrame(results, columns=cols)
        return _apply_fallback_for_equal_dates(session, df)

    @staticmethod
    def get_module_version_by_vid(
        session: "Session",
        vid: int,
    ) -> pd.DataFrame:
        """Query a single module version by VID.

        Args:
            session: SQLAlchemy session.
            vid: ModuleVID integer.

        Returns:
            DataFrame with module information.
        """
        cols = [
            "ModuleVID",
            "Code",
            "Name",
            "FromReferenceDate",
            "ToReferenceDate",
            "StartReleaseID",
            "EndReleaseID",
        ]
        query = session.query(
            ModuleVersion.module_vid.label("ModuleVID"),
            ModuleVersion.code.label("Code"),
            ModuleVersion.name.label("Name"),
            ModuleVersion.from_reference_date.label("FromReferenceDate"),
            ModuleVersion.to_reference_date.label("ToReferenceDate"),
            ModuleVersion.start_release_id.label("StartReleaseID"),
            ModuleVersion.end_release_id.label("EndReleaseID"),
        ).filter(ModuleVersion.module_vid == vid)
        results = query.all()
        return pd.DataFrame(results, columns=cols)


def _apply_fallback_for_equal_dates(
    session: "Session",
    df: pd.DataFrame,
    module_vid_col: str = "ModuleVID",
) -> pd.DataFrame:
    """Replace ghost modules where dates are equal.

    When ``FromReferenceDate == ToReferenceDate`` for a
    module version, find the previous version of the same
    module and substitute its metadata while preserving
    association columns.

    Args:
        session: SQLAlchemy session.
        df: DataFrame with module version data.
        module_vid_col: Column holding module VID.

    Returns:
        DataFrame with fallback applied.
    """
    if df.empty:
        return df

    mask = df["FromReferenceDate"] == df["ToReferenceDate"]
    rows_needing = df[mask]
    if rows_needing.empty:
        return df

    vids_needing = [int(v) for v in rows_needing[module_vid_col].unique()]

    current_modules = (
        session.query(
            ModuleVersion.module_vid,
            ModuleVersion.module_id,
            ModuleVersion.start_release_id,
        )
        .filter(ModuleVersion.module_vid.in_(vids_needing))
        .all()
    )
    current_info = {
        r.module_vid: (r.module_id, r.start_release_id)
        for r in current_modules
    }

    unique_mids = list({info[0] for info in current_info.values()})
    prev_versions = (
        session.query(ModuleVersion)
        .filter(ModuleVersion.module_id.in_(unique_mids))
        .order_by(
            ModuleVersion.module_id,
            ModuleVersion.start_release_id.desc(),
        )
        .all()
    )

    by_mid: dict[int, list[ModuleVersion]] = {}
    for mv in prev_versions:
        if mv.module_id is None:
            continue
        by_mid.setdefault(mv.module_id, []).append(mv)

    replacement: dict[int, ModuleVersion] = {}
    for cur_vid, (mid, cur_srid) in current_info.items():
        if mid is None or cur_srid is None:
            continue
        for mv in by_mid.get(mid, []):
            if (
                mv.start_release_id is not None
                and mv.start_release_id < cur_srid
            ):
                if mv.from_reference_date != mv.to_reference_date:
                    replacement[cur_vid] = mv
                    break

    if not replacement:
        return df

    result_df = df.copy()
    for idx, row in result_df.iterrows():
        if row["FromReferenceDate"] == row["ToReferenceDate"]:
            cur_vid = int(row[module_vid_col])
            if cur_vid in replacement:
                prev = replacement[cur_vid]
                result_df.at[idx, "ModuleVID"] = prev.module_vid
                result_df.at[idx, "ModuleCode"] = prev.code
                result_df.at[idx, "VersionNumber"] = prev.version_number
                result_df.at[idx, "FromReferenceDate"] = (
                    prev.from_reference_date
                )
                result_df.at[idx, "ToReferenceDate"] = prev.to_reference_date
                if "StartReleaseID" in result_df.columns:
                    result_df.at[idx, "StartReleaseID"] = prev.start_release_id
                if "EndReleaseID" in result_df.columns:
                    result_df.at[idx, "EndReleaseID"] = prev.end_release_id
    return result_df


# ------------------------------------------------------------------ #
# OperationScopeComposition queries
# ------------------------------------------------------------------ #


class OperationScopeCompositionQuery:
    """Query helpers for OperationScopeComposition."""

    @staticmethod
    def get_from_operation_version_id(
        session: "Session",
        operation_version_id: int,
    ) -> pd.DataFrame:
        """Get scope compositions for an operation.

        Args:
            session: SQLAlchemy session.
            operation_version_id: OperationVID.

        Returns:
            DataFrame with OperationScopeID, ModuleVID.
        """
        query = (
            session.query(
                OperationScopeComposition.operation_scope_id.label(
                    "OperationScopeID"
                ),
                OperationScopeComposition.module_vid.label("ModuleVID"),
            )
            .join(
                OperationScope,
                OperationScopeComposition.operation_scope_id
                == OperationScope.operation_scope_id,
            )
            .filter(OperationScope.operation_vid == operation_version_id)
        )
        results = query.all()
        return pd.DataFrame(
            results,
            columns=["OperationScopeID", "ModuleVID"],
        )


# ------------------------------------------------------------------ #
# ViewDatapoints query class
# ------------------------------------------------------------------ #


class ViewDatapointsQuery:
    """Builds and executes the datapoints query.

    Replicates the old ``ViewDatapoints`` ORM view using
    multi-table joins against the normalised schema.
    """

    _TABLE_DATA_CACHE: dict[
        tuple[
            Hashable,
            str,
            tuple[str, ...] | None,
            tuple[str, ...] | None,
            tuple[str, ...] | None,
            int | None,
        ],
        pd.DataFrame,
    ] = {}

    # -- internal helpers ------------------------------------------ #

    @staticmethod
    def _create_base_query_with_aliases(
        session: "Session",
    ) -> tuple["Query[Any]", dict[str, Any]]:
        """Build the base multi-join query.

        Args:
            session: SQLAlchemy session.

        Returns:
            Tuple of (query, aliases dict).
        """
        hvr = aliased(HeaderVersion)
        hvc = aliased(HeaderVersion)
        hvs = aliased(HeaderVersion)
        tvh_row = aliased(TableVersionHeader)
        tvh_col = aliased(TableVersionHeader)
        tvh_sheet = aliased(TableVersionHeader)

        query = (
            session.query()
            .select_from(TableVersion)
            .join(
                ModuleVersionComposition,
                TableVersion.table_vid == ModuleVersionComposition.table_vid,
            )
            .join(
                ModuleVersion,
                ModuleVersionComposition.module_vid
                == ModuleVersion.module_vid,
            )
            .join(
                TableVersionCell,
                and_(
                    TableVersionCell.table_vid == TableVersion.table_vid,
                    TableVersionCell.is_void == 0,
                ),
            )
            .outerjoin(
                VariableVersion,
                TableVersionCell.variable_vid == VariableVersion.variable_vid,
            )
            .outerjoin(
                Property,
                VariableVersion.property_id == Property.property_id,
            )
            .outerjoin(
                DataType,
                Property.data_type_id == DataType.data_type_id,
            )
            .join(
                Cell,
                TableVersionCell.cell_id == Cell.cell_id,
            )
            .outerjoin(
                hvr,
                hvr.header_id == Cell.row_id,
            )
            .outerjoin(
                tvh_row,
                and_(
                    tvh_row.table_vid == TableVersion.table_vid,
                    tvh_row.header_vid == hvr.header_vid,
                ),
            )
            .outerjoin(
                hvc,
                hvc.header_id == Cell.column_id,
            )
            .outerjoin(
                tvh_col,
                and_(
                    tvh_col.table_vid == TableVersion.table_vid,
                    tvh_col.header_vid == hvc.header_vid,
                ),
            )
            .outerjoin(
                hvs,
                hvs.header_id == Cell.sheet_id,
            )
            .outerjoin(
                tvh_sheet,
                and_(
                    tvh_sheet.table_vid == TableVersion.table_vid,
                    tvh_sheet.header_vid == hvs.header_vid,
                ),
            )
        )

        aliases = {
            "hvr": hvr,
            "hvc": hvc,
            "hvs": hvs,
            "tvh_row": tvh_row,
            "tvh_col": tvh_col,
            "tvh_sheet": tvh_sheet,
        }
        return query, aliases

    # -- public methods -------------------------------------------- #

    @classmethod
    def get_table_data(
        cls,
        session: "Session",
        table: str,
        rows: Sequence[str] | None = None,
        cols: Sequence[str] | None = None,
        sheets: Sequence[str] | None = None,
        release_id: int | None = None,
    ) -> pd.DataFrame:
        """Retrieve cell-level data for a table.

        Results are cached per engine + parameters.

        Args:
            session: SQLAlchemy session.
            table: Table version code.
            rows: Optional row-code filter.
            cols: Optional column-code filter.
            sheets: Optional sheet-code filter.
            release_id: Optional release filter.

        Returns:
            DataFrame of cell data.
        """
        engine_key = _get_engine_cache_key(session)
        rows_k = tuple(rows) if rows is not None else None
        cols_k = tuple(cols) if cols is not None else None
        sheets_k = tuple(sheets) if sheets is not None else None
        cache_key = (
            engine_key,
            table,
            rows_k,
            cols_k,
            sheets_k,
            release_id,
        )
        cached = cls._TABLE_DATA_CACHE.get(cache_key)
        if cached is not None:
            return cached

        query, aliases = cls._create_base_query_with_aliases(session)

        query = query.add_columns(
            TableVersionCell.cell_code.label("cell_code"),
            TableVersion.code.label("table_code"),
            aliases["hvr"].code.label("row_code"),
            aliases["hvc"].code.label("column_code"),
            aliases["hvs"].code.label("sheet_code"),
            VariableVersion.variable_id.label("variable_id"),
            DataType.code.label("data_type"),
            TableVersion.table_vid.label("table_vid"),
            TableVersionCell.cell_id.label("cell_id"),
            ModuleVersion.start_release_id.label("start_release_id"),
            ModuleVersion.end_release_id.label("end_release_id"),
        )

        query = query.filter(TableVersion.code == table)

        if release_id is None:
            query = query.filter(TableVersion.end_release_id.is_(None))

        # Row filter
        if rows is not None and rows != ["*"]:
            query = _apply_dimension_filter(query, aliases["hvr"].code, rows)

        # Column filter
        if cols is not None and cols != ["*"]:
            query = _apply_dimension_filter(query, aliases["hvc"].code, cols)

        # Sheet filter
        if sheets is not None and sheets != ["*"]:
            query = _apply_dimension_filter(query, aliases["hvs"].code, sheets)

        if release_id is not None:
            query = _old_filter_by_release(
                query,
                ModuleVersion.start_release_id,
                ModuleVersion.end_release_id,
                release_id,
            )

        data = read_sql_with_connection(
            compile_query_for_pandas(query.statement, session),
            session,
        )

        if len(data) > 0:
            data = data.sort_values("variable_id", na_position="last")
            data = data.drop_duplicates(subset=["cell_code"], keep="first")

        data = _check_ranges_values_are_present(data, "row_code", rows)
        data = _check_ranges_values_are_present(data, "column_code", cols)
        data = _check_ranges_values_are_present(data, "sheet_code", sheets)

        cls._TABLE_DATA_CACHE[cache_key] = data
        return data

    @classmethod
    def get_filtered_datapoints(
        cls,
        session: "Session",
        table: str,
        table_info: dict[str, Any],
        release_id: int | None = None,
    ) -> pd.DataFrame:
        """Retrieve datapoints with dimension filters.

        Args:
            session: SQLAlchemy session.
            table: Table version code.
            table_info: Dict with rows/cols/sheets lists.
            release_id: Optional release filter.

        Returns:
            DataFrame of filtered datapoints.
        """
        query, aliases = cls._create_base_query_with_aliases(session)

        query = query.add_columns(
            TableVersionCell.cell_code.label("cell_code"),
            TableVersion.code.label("table_code"),
            aliases["hvr"].code.label("row_code"),
            aliases["hvc"].code.label("column_code"),
            aliases["hvs"].code.label("sheet_code"),
            VariableVersion.variable_id.label("variable_id"),
            DataType.code.label("data_type"),
            TableVersion.table_vid.label("table_vid"),
            Property.property_id.label("property_id"),
            ModuleVersion.start_release_id.label("start_release"),
            ModuleVersion.end_release_id.label("end_release"),
            TableVersionCell.cell_id.label("cell_id"),
            VariableVersion.context_id.label("context_id"),
            VariableVersion.variable_vid.label("variable_vid"),
        ).distinct()

        query = query.filter(TableVersion.code == table)

        mapping = {
            "rows": aliases["hvr"].code,
            "cols": aliases["hvc"].code,
            "sheets": aliases["hvs"].code,
        }
        for key, values in table_info.items():
            if values is not None and key in mapping:
                col = mapping[key]
                if "-" in values[0]:
                    lo, hi = values[0].split("-")
                    query = query.filter(col.between(lo, hi))
                elif values[0] == "*":
                    continue
                else:
                    query = query.filter(col.in_(values))

        if release_id:
            query = _old_filter_by_release(
                query,
                ModuleVersion.start_release_id,
                ModuleVersion.end_release_id,
                release_id,
            )

        return read_sql_with_connection(
            compile_query_for_pandas(query.statement, session),
            session,
        )


def _apply_dimension_filter(
    query: "Query[Any]",
    # column is either a SQLAlchemy ColumnElement or an InstrumentedAttribute
    # from ORM; see _filter_elements for rationale.
    column: Any,
    values: Sequence[str],
) -> "Query[Any]":
    """Apply row/col/sheet dimension filter.

    Args:
        query: SQLAlchemy query.
        column: Header code column.
        values: List of filter values (may have ranges).

    Returns:
        Filtered query.
    """
    if len(values) == 1 and "-" in values[0]:
        lo, hi = values[0].split("-")
        return query.filter(column.between(lo, hi))

    has_range = any("-" in x for x in values)
    if has_range:
        filters: list[Any] = []
        for v in values:
            if "-" in v:
                lo, hi = v.split("-")
                filters.append(column.between(lo, hi))
            else:
                filters.append(column == v)
        return query.filter(or_(*filters))
    return query.filter(column.in_(values))


# ------------------------------------------------------------------ #
# ViewKeyComponents query class
# ------------------------------------------------------------------ #


class ViewKeyComponentsQuery:
    """Builds and executes the key_components query."""

    @staticmethod
    def _create_view_query(session: "Session") -> "Query[Any]":
        """Build the base key-components query.

        Args:
            session: SQLAlchemy session.

        Returns:
            SQLAlchemy query with joins configured.
        """
        return (
            session.query()
            .select_from(TableVersion)
            .join(
                KeyComposition,
                TableVersion.key_id == KeyComposition.key_id,
            )
            .join(
                VariableVersion,
                VariableVersion.variable_vid == KeyComposition.variable_vid,
            )
            .join(
                Item,
                VariableVersion.property_id == Item.item_id,
            )
            .join(
                ItemCategory,
                ItemCategory.item_id == Item.item_id,
            )
            .join(
                Property,
                VariableVersion.property_id == Property.property_id,
            )
            .outerjoin(
                DataType,
                Property.data_type_id == DataType.data_type_id,
            )
            .join(
                ModuleVersionComposition,
                TableVersion.table_vid == ModuleVersionComposition.table_vid,
            )
            .join(
                ModuleVersion,
                ModuleVersionComposition.module_vid
                == ModuleVersion.module_vid,
            )
        )

    @classmethod
    def get_by_table(
        cls,
        session: "Session",
        table: str,
        release_id: int | None,
    ) -> pd.DataFrame:
        """Get key components for a single table.

        Args:
            session: SQLAlchemy session.
            table: Table version code.
            release_id: Release filter.

        Returns:
            DataFrame with table_code, property_code,
            data_type.
        """
        query = cls._create_view_query(session)
        query = query.add_columns(
            TableVersion.code.label("table_code"),
            ItemCategory.code.label("property_code"),
            DataType.code.label("data_type"),
        )
        query = query.filter(TableVersion.code == table)
        query = _old_filter_by_release(
            query,
            ItemCategory.start_release_id,
            ItemCategory.end_release_id,
            release_id,
        )
        query = _old_filter_by_release(
            query,
            ModuleVersion.start_release_id,
            ModuleVersion.end_release_id,
            release_id,
        )
        query = query.distinct()
        return read_sql_with_connection(
            compile_query_for_pandas(query.statement, session),
            session,
        )


# ------------------------------------------------------------------ #
# ViewOpenKeys query class
# ------------------------------------------------------------------ #


class ViewOpenKeysQuery:
    """Builds and executes the open_keys query."""

    @staticmethod
    def _create_view_query(session: "Session") -> "Query[Any]":
        """Build the base open-keys query.

        Args:
            session: SQLAlchemy session.

        Returns:
            SQLAlchemy query with joins configured.
        """
        return (
            session.query()
            .select_from(KeyComposition)
            .join(
                VariableVersion,
                VariableVersion.variable_vid == KeyComposition.variable_vid,
            )
            .join(
                Item,
                VariableVersion.property_id == Item.item_id,
            )
            .join(
                ItemCategory,
                ItemCategory.item_id == Item.item_id,
            )
            .join(
                Property,
                VariableVersion.property_id == Property.property_id,
            )
            .outerjoin(
                DataType,
                Property.data_type_id == DataType.data_type_id,
            )
        )

    @classmethod
    def get_keys(
        cls,
        session: "Session",
        dimension_codes: Sequence[str],
        release_id: int | None,
    ) -> pd.DataFrame:
        """Get open keys for given dimension codes.

        Args:
            session: SQLAlchemy session.
            dimension_codes: Property codes to look up.
            release_id: Release filter.

        Returns:
            DataFrame with property_id, property_code,
            data_type.
        """
        query = cls._create_view_query(session)
        query = query.add_columns(
            ItemCategory.item_id.label("property_id"),
            ItemCategory.code.label("property_code"),
            DataType.code.label("data_type"),
        )
        query = query.filter(ItemCategory.code.in_(dimension_codes))
        query = _old_filter_by_release(
            query,
            ItemCategory.start_release_id,
            ItemCategory.end_release_id,
            release_id,
        )
        query = query.distinct()
        return read_sql_with_connection(
            compile_query_for_pandas(query.statement, session),
            session,
        )


# ------------------------------------------------------------------ #
# ViewModules query class
# ------------------------------------------------------------------ #


class ViewModulesQuery:
    """Module-from-table queries using ORM joins.

    Replaces the old ``ViewModules`` view-backed model
    with a direct join through ModuleVersion and
    ModuleVersionComposition.
    """

    @staticmethod
    def get_modules(
        session: "Session",
        tables: Sequence[str],
        release_id: int | None = None,
    ) -> list[str]:
        """Return distinct module codes for tables.

        Args:
            session: SQLAlchemy session.
            tables: List of table codes.
            release_id: Unused (kept for API compat).

        Returns:
            Deduplicated list of module codes.
        """
        query = (
            session.query(
                ModuleVersion.code.label("module_code"),
                TableVersion.code.label("table_code"),
            )
            .join(
                ModuleVersionComposition,
                ModuleVersion.module_vid
                == ModuleVersionComposition.module_vid,
            )
            .join(
                TableVersion,
                ModuleVersionComposition.table_vid == TableVersion.table_vid,
            )
            .filter(TableVersion.code.in_(tables))
        )
        result = query.all()
        if not result:
            return []
        return list({r.module_code for r in result})

    @staticmethod
    def get_all_modules(
        session: "Session",
    ) -> pd.DataFrame:
        """Return all module-to-table mappings.

        Args:
            session: SQLAlchemy session.

        Returns:
            DataFrame with module_code, table_code.
        """
        query = (
            session.query(
                ModuleVersion.code.label("module_code"),
                TableVersion.code.label("table_code"),
            )
            .join(
                ModuleVersionComposition,
                ModuleVersion.module_vid
                == ModuleVersionComposition.module_vid,
            )
            .join(
                TableVersion,
                ModuleVersionComposition.table_vid == TableVersion.table_vid,
            )
            .distinct()
        )
        return read_sql_with_connection(
            compile_query_for_pandas(query.statement, session),
            session,
        )
