"""Query functions for the DPM-XL engine.

Provides standalone query functions and query classes that
replicate the class methods previously embedded in the old
``py_dpm.dpm.models`` ORM models.  All functions accept a
SQLAlchemy *session* as first positional argument and use the
legacy ``session.query()`` API for compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Collection,
    Hashable,
    NamedTuple,
    Sequence,
)

import pandas as pd
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import aliased

from dpmcore.dpm_xl.utils.filters import (
    filter_by_release,
    filter_live_only,
    release_window_conditions,
)
from dpmcore.dpm_xl.utils.range_resolution import (
    build_axis_order_map,
    build_axis_value_map,
    resolve_range_codes,
)
from dpmcore.orm.glossary import (
    Category,
    Item,
    ItemCategory,
    Property,
    PropertyCategory,
    SubCategoryItem,
    SupercategoryComposition,
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
from dpmcore.orm.query_utils import chunked_in
from dpmcore.orm.release_sort_order import (
    compute_sort_order,
    load_release_sort_orders,
    release_ids_for_sort_order,
    resolve_sort_order,
)
from dpmcore.orm.rendering import (
    Cell,
    HeaderVersion,
    TableGroup,
    TableGroupComposition,
    TableVersion,
    TableVersionCell,
    TableVersionHeader,
)
from dpmcore.orm.supercategories import load_supercategory_member_codes
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

# The DPM 2.0 Refit schema stores the filing-indicator variable type as
# the single token "filingindicator". Some source exports spell it
# "Filing Indicator" (with a space and capitals), so matching is done on
# a case- and whitespace-normalised form rather than a fixed literal.
_FILING_INDICATOR_TYPE = "filingindicator"


def _is_filing_indicator() -> Any:
    """Return a SQLAlchemy clause matching filing-indicator variables.

    Normalises ``Variable.type`` (lower-cased, spaces removed) before
    comparison so the match is robust to spelling variants across DPM
    source exports (``"Filing Indicator"`` vs ``"filingindicator"``).
    """
    normalized = func.lower(func.replace(Variable.type, " ", ""))
    return normalized == _FILING_INDICATOR_TYPE


def _get_engine_cache_key(session: "Session") -> Hashable:
    """Return a hashable key that identifies the engine and its schema.

    Includes ``schema_translate_map`` so that two sessions bound to
    the same URL but scoped to different schemas (e.g. distinct
    staging schemas, or staging vs. the default schema) never share a
    cache entry.

    Args:
        session: SQLAlchemy session.

    Returns:
        A hashable value derived from the bound engine URL and schema
        translation options.
    """
    bind = session.get_bind()
    url = getattr(bind, "url", repr(bind))
    schema_translate_map = bind.get_execution_options().get(
        "schema_translate_map"
    )
    schema_key = (
        frozenset(schema_translate_map.items())
        if schema_translate_map
        else None
    )
    return (url, schema_key)


def read_sql_with_connection(
    query_statement: Any,
    session: "Session",
) -> pd.DataFrame:
    """Execute *query_statement* through *session* and return a DataFrame.

    Goes through ``session.execute()`` rather than compiling to a
    literal SQL string for a raw DBAPI connection (the previous
    approach). SQLAlchemy only resolves the engine's
    ``schema_translate_map`` execution option at actual
    statement-execution time -- compiling standalone with
    ``compile_kwargs={"schema_translate_map": ...}`` does not apply
    it and silently produces unqualified table names, which then
    resolve against the connection's default ``search_path`` (e.g.
    ``public``) instead of a migration's staging schema. Executing
    through the session keeps schema scoping correct for both plain
    and schema-translated engines.

    Args:
        query_statement: SQLAlchemy statement object (e.g.
            ``query.statement``).
        session: SQLAlchemy session.

    Returns:
        DataFrame with query results.
    """
    result = session.execute(query_statement)
    return pd.DataFrame(result.fetchall(), columns=list(result.keys()))


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


# ------------------------------------------------------------------ #
# Category-link domain resolution
# ------------------------------------------------------------------ #


@dataclass(frozen=True)
class PropertyDomains:
    """The categories a component built on a property takes items from.

    ``own`` is the category the property is typed on (a set, because the
    link is release-versioned). ``members`` is what a *super-category*
    among them adds: the categories composing it, which is where
    ``ItemCategory`` actually files most of its value set.

    The two are kept apart rather than unioned because they carry
    different confidence. An item in ``own`` is unconditionally a value
    the component can take; an item in ``members`` is only known to be in
    the super-category's *overall* value set, and a header subcategory
    may narrow which of them a given column actually offers.
    """

    own: frozenset[str]
    members: frozenset[str]

    @property
    def codes(self) -> frozenset[str]:
        """Every category the component may take items from."""
        return self.own | self.members


def _enumerated_domains(
    session: "Session",
    model: Any,
    key_col: Any,
    keys: Sequence[Any],
    release_id: int | None,
    *,
    with_members: bool = False,
) -> tuple[dict[Any, set[str]], dict[Any, set[str]]]:
    """Map the keys of a category link table to enumerated category codes.

    ``ItemCategory`` and ``PropertyCategory`` are the same shape: a
    release-versioned link to ``Category``. Only enumerated categories are
    returned -- a non-enumerated one (dates, identifiers, free text) is not
    a value set. Both links are release-versioned, hence the set-valued
    result.

    Args:
        session: SQLAlchemy session.
        model: Link model holding ``category_id`` and the release columns.
        key_col: Column of *model* the result is keyed on.
        keys: Values of *key_col* to resolve.
        release_id: Release the link is resolved at.
        with_members: Also resolve, in the same statement, the categories
            composing each linked category when it is a *super-category*.
            An outer join, so a key whose category composes nothing is
            still returned; the window on the composition lives in the
            ``ON`` clause, where it cannot narrow that outer join back to
            an inner one.

    Returns:
        ``({key: {category_code, ...}}, {key: {member_code, ...}})``,
        each omitting keys with nothing to report. The second mapping is
        always empty unless *with_members*, and covers one level of
        composition -- :func:`load_supercategory_member_codes` completes
        the closure for the rare nested case.
    """
    # Both windows come from one release load: the link's own, and --
    # when members are wanted -- the composition's, which has to sit in
    # the join's ON clause so the outer join stays outer.
    windows = [(model.start_release_id, model.end_release_id)]
    if with_members:
        windows.append(
            (
                SupercategoryComposition.start_release_id,
                SupercategoryComposition.end_release_id,
            )
        )
    conditions = release_window_conditions(session, windows, release_id)

    query = (
        session.query(
            key_col.label("DomainKey"),
            Category.code.label("CategoryCode"),
        )
        .join(Category, Category.category_id == model.category_id)
        .filter(Category.is_enumerated == True)  # noqa: E712
        .filter(Category.code.isnot(None))
        .filter(conditions[0])
    )
    if with_members:
        query = _add_member_columns(query, conditions[1])
    domains: dict[Any, set[str]] = {}
    members: dict[Any, set[str]] = {}
    for row in chunked_in(query, key_col, keys):
        domains.setdefault(row.DomainKey, set()).add(row.CategoryCode)
        if with_members and row.MemberCode is not None:
            members.setdefault(row.DomainKey, set()).add(row.MemberCode)
    return domains, members


def _add_member_columns(
    query: "Query[Any]",
    composition_window: Any,
) -> "Query[Any]":
    """Outer-join the composing categories of a super-category domain."""
    member = aliased(Category)
    return (
        query.outerjoin(
            SupercategoryComposition,
            and_(
                SupercategoryComposition.supercategory_id
                == Category.category_id,
                composition_window,
            ),
        )
        .outerjoin(
            member,
            and_(
                member.category_id == SupercategoryComposition.category_id,
                member.is_enumerated == True,  # noqa: E712
                member.code.isnot(None),
            ),
        )
        .add_columns(member.code.label("MemberCode"))
    )


def _nested_members(
    session: "Session",
    members: dict[Any, set[str]],
    release_id: int | None,
) -> dict[str, set[str]]:
    """Expand members that are themselves super-categories.

    The single-statement join in :func:`_enumerated_domains` reaches one
    level. This completes the closure -- and issues no query at all when
    nothing composed anything, which is every property typed on an
    ordinary category.
    """
    codes = {code for values in members.values() for code in values}
    if not codes:
        return {}
    return load_supercategory_member_codes(
        session, codes, release_id=release_id
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
            query = filter_by_release(
                query,
                start_col=ItemCategory.start_release_id,
                end_col=ItemCategory.end_release_id,
                release_id=release_id,
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

    @staticmethod
    def get_item_domains(
        session: "Session",
        items: Sequence[str],
        release_id: int | None = None,
    ) -> dict[str, set[str]]:
        """Map item signatures to the code(s) of the categories holding them.

        The category is the item's *domain*: the set of values a component
        typed on that category may take. Only enumerated categories are
        returned -- a non-enumerated one (dates, identifiers, free text) is
        not a value set. An item is normally in exactly one category per
        release, but the mapping is release-versioned, so the value is a set.

        Args:
            session: SQLAlchemy session.
            items: Item signatures to resolve.
            release_id: Release the membership is resolved at.

        Returns:
            ``{signature: {category_code, ...}}``, omitting signatures with
            no category open at ``release_id``.
        """
        if not items:
            return {}
        domains, _members = _enumerated_domains(
            session,
            ItemCategory,
            ItemCategory.signature,
            items,
            release_id,
        )
        return domains


# ------------------------------------------------------------------ #
# PropertyCategory queries
# ------------------------------------------------------------------ #


class PropertyCategoryQuery:
    """Query helpers around the PropertyCategory model."""

    @staticmethod
    def get_property_domains(
        session: "Session",
        property_ids: Sequence[int],
        release_id: int | None = None,
    ) -> dict[int, PropertyDomains]:
        """Map properties to the categories they are typed on.

        A property's category is the domain of every component built on it:
        the items that component may take. Only enumerated categories are
        returned, so a property that holds dates, identifiers or free text
        resolves to no domain at all. Like ``ItemCategory``, the link is
        release-versioned, hence the set-valued result.

        A category that is a *super-category* also contributes the
        categories composing it: the component takes items from any of
        them, while ``ItemCategory`` files each item under the one
        category that owns it. Both halves are reported separately --
        see :class:`PropertyDomains` -- because a caller that can pin the
        component's value set down more precisely needs to know which of
        the two it is looking at.

        The composition is resolved in the same statement as the domain,
        so a property on an ordinary category costs no extra query; only
        the rare nested super-category needs a second round trip.

        Args:
            session: SQLAlchemy session.
            property_ids: Property IDs to resolve.
            release_id: Release the link is resolved at.

        Returns:
            ``{property_id: PropertyDomains}``, omitting properties with
            no category open at ``release_id``.
        """
        if not property_ids:
            return {}
        own, members = _enumerated_domains(
            session,
            PropertyCategory,
            PropertyCategory.property_id,
            property_ids,
            release_id,
            with_members=True,
        )
        nested = _nested_members(session, members, release_id)
        return {
            int(key): PropertyDomains(
                own=frozenset(codes),
                members=frozenset(
                    members.get(key, set()).union(
                        *(
                            nested.get(code, set())
                            for code in members.get(key, set())
                        )
                    )
                    if members.get(key)
                    else ()
                ),
            )
            for key, codes in own.items()
        }


# ------------------------------------------------------------------ #
# SubCategory queries
# ------------------------------------------------------------------ #


class SubCategoryQuery:
    """Query helpers around the header subcategory of a data point.

    A ``Category`` is the widest thing a component may take values from.
    Where a table header names a ``SubCategoryVersion``, the dictionary
    says exactly which of those items *that column* offers -- 18 of
    ``qTU``'s 927, say. Only about 4% of header versions carry one, so
    this is a refinement, never the primary resolution.
    """

    @staticmethod
    def get_cell_subcategory_vids(
        session: "Session",
        cells: Sequence[tuple[int, int]],
        release_id: int | None = None,
    ) -> dict[tuple[int, int, int], int]:
        """Map cells to the subcategory their own header pins down.

        Only a header whose ``property_id`` is the one the caller is
        asking about counts: a cell is bounded by up to three headers,
        and a subcategory on the row says nothing about the value set of
        a column's property.

        Args:
            session: SQLAlchemy session.
            cells: ``(table_vid, cell_id)`` pairs to resolve.
            release_id: Release the header version is resolved at.

        Returns:
            ``{(table_vid, cell_id, property_id): subcategory_vid}``,
            omitting cells whose headers name no subcategory.
        """
        if not cells:
            return {}
        query = (
            session.query(
                TableVersionCell.table_vid.label("TableVid"),
                TableVersionCell.cell_id.label("CellId"),
                HeaderVersion.property_id.label("PropertyId"),
                HeaderVersion.subcategory_vid.label("SubcategoryVid"),
            )
            .join(Cell, Cell.cell_id == TableVersionCell.cell_id)
            .join(
                TableVersionHeader,
                and_(
                    TableVersionHeader.table_vid == TableVersionCell.table_vid,
                    or_(
                        TableVersionHeader.header_id == Cell.column_id,
                        TableVersionHeader.header_id == Cell.row_id,
                        TableVersionHeader.header_id == Cell.sheet_id,
                    ),
                ),
            )
            .join(
                HeaderVersion,
                HeaderVersion.header_vid == TableVersionHeader.header_vid,
            )
            .filter(HeaderVersion.subcategory_vid.isnot(None))
            .filter(HeaderVersion.property_id.isnot(None))
        )
        table_vids = {table_vid for table_vid, _cell_id in cells}
        query = query.filter(TableVersionCell.table_vid.in_(table_vids))
        wanted = set(cells)
        found: dict[tuple[int, int, int], int] = {}
        for row in chunked_in(
            query,
            TableVersionCell.cell_id,
            {cell_id for _table_vid, cell_id in cells},
        ):
            if (row.TableVid, row.CellId) not in wanted:
                continue
            found[(row.TableVid, row.CellId, row.PropertyId)] = (
                row.SubcategoryVid
            )
        return found

    @staticmethod
    def get_subcategory_signatures(
        session: "Session",
        subcategory_vids: Sequence[int],
        release_id: int | None = None,
    ) -> dict[int, set[str]]:
        """Map subcategory versions to the item signatures they list.

        Args:
            session: SQLAlchemy session.
            subcategory_vids: SubCategoryVersion IDs to resolve.
            release_id: Release the item codes are resolved at -- an
                item with no ``ItemCategory`` row open there has no
                signature at that release and is left out.

        Returns:
            ``{subcategory_vid: {signature, ...}}``.
        """
        if not subcategory_vids:
            return {}
        query = (
            session.query(
                SubCategoryItem.subcategory_vid.label("SubcategoryVid"),
                ItemCategory.signature.label("Signature"),
            )
            .join(
                ItemCategory, ItemCategory.item_id == SubCategoryItem.item_id
            )
            .filter(ItemCategory.signature.isnot(None))
        )
        query = filter_by_release(
            query,
            start_col=ItemCategory.start_release_id,
            end_col=ItemCategory.end_release_id,
            release_id=release_id,
            active_only_fallback=True,
        )
        signatures: dict[int, set[str]] = {}
        for row in chunked_in(
            query, SubCategoryItem.subcategory_vid, subcategory_vids
        ):
            signatures.setdefault(row.SubcategoryVid, set()).add(row.Signature)
        return signatures


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
            query = filter_by_release(
                query,
                start_col=VariableVersion.start_release_id,
                end_col=VariableVersion.end_release_id,
                release_id=release_id,
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
        *variable_code* and whose Variable type is a
        filing indicator (see :func:`_is_filing_indicator`).

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
                _is_filing_indicator(),
            )
        )
        query = filter_by_release(
            query,
            start_col=VariableVersion.start_release_id,
            end_col=VariableVersion.end_release_id,
            release_id=release_id,
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
        query = filter_by_release(
            query,
            start_col=VariableVersion.start_release_id,
            end_col=VariableVersion.end_release_id,
            release_id=release_id,
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
            query = filter_by_release(
                query,
                start_col=VariableVersion.start_release_id,
                end_col=VariableVersion.end_release_id,
                release_id=release_id,
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
            .filter(_is_filing_indicator())
        )
        query = filter_by_release(
            query,
            start_col=VariableVersion.start_release_id,
            end_col=VariableVersion.end_release_id,
            release_id=release_id,
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
            query = filter_by_release(
                query,
                start_col=OperationVersion.start_release_id,
                end_col=OperationVersion.end_release_id,
                release_id=release_id,
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
        query = filter_by_release(
            query,
            start_col=TableVersion.start_release_id,
            end_col=TableVersion.end_release_id,
            release_id=release_id,
        )
        return query.first() is not None

    @staticmethod
    def get_abstract_table_codes(
        session: "Session",
        table_codes: Sequence[str],
        release_id: int | None,
    ) -> dict[str, str]:
        """Map each table code to its abstract-table code.

        ``abstract_table_id`` is a FK to the abstract ``Table``, not a
        specific version. Falls back to the table's own code if it has
        none, or none open at ``release_id``.

        Args:
            session: SQLAlchemy session.
            table_codes: Table version codes to resolve.
            release_id: Release filter, applied to both the requested
                tables and their abstract tables independently.

        Returns:
            ``{table_code: abstract_table_code}``, one entry per code in
            ``table_codes`` that actually resolves to a table version.
        """
        if not table_codes:
            return {}
        rows = filter_by_release(
            session.query(
                TableVersion.code,
                TableVersion.abstract_table_id,
            ).filter(TableVersion.code.in_(list(table_codes))),
            TableVersion.start_release_id,
            TableVersion.end_release_id,
            release_id,
        ).all()
        abstract_table_ids = {
            abstract_table_id
            for _code, abstract_table_id in rows
            if abstract_table_id is not None
        }
        abstract_code_by_table_id: dict[int, str] = {}
        if abstract_table_ids:
            abstract_code_by_table_id = dict(
                filter_by_release(
                    session.query(
                        TableVersion.table_id, TableVersion.code
                    ).filter(TableVersion.table_id.in_(abstract_table_ids)),
                    TableVersion.start_release_id,
                    TableVersion.end_release_id,
                    release_id,
                ).all()
            )
        return {
            code: abstract_code_by_table_id.get(abstract_table_id, code)
            for code, abstract_table_id in rows
        }

    @staticmethod
    def get_concrete_table_codes(
        session: "Session",
        codes: Sequence[str],
        release_id: int | None,
    ) -> dict[str, set[str]]:
        """Expand each code to itself plus any concrete tables under it.

        Module composition only links concrete tables, so an abstract
        code needs its concrete children to find any module.

        Args:
            session: SQLAlchemy session.
            codes: Table codes to expand.
            release_id: Release filter, applied independently to the
                requested codes and their concrete children.

        Returns:
            ``{code: {code, *concrete_children}}``, one entry per code.
        """
        if not codes:
            return {}
        table_id_by_code = dict(
            filter_by_release(
                session.query(TableVersion.code, TableVersion.table_id).filter(
                    TableVersion.code.in_(list(codes))
                ),
                TableVersion.start_release_id,
                TableVersion.end_release_id,
                release_id,
            ).all()
        )
        table_ids = {
            tid for tid in table_id_by_code.values() if tid is not None
        }
        children_by_table_id: dict[int, set[str]] = {}
        if table_ids:
            for abstract_table_id, child_code in filter_by_release(
                session.query(
                    TableVersion.abstract_table_id, TableVersion.code
                ).filter(TableVersion.abstract_table_id.in_(table_ids)),
                TableVersion.start_release_id,
                TableVersion.end_release_id,
                release_id,
            ).all():
                children_by_table_id.setdefault(abstract_table_id, set()).add(
                    child_code
                )
        result: dict[str, set[str]] = {}
        for code in codes:
            table_id = table_id_by_code.get(code)
            children = (
                children_by_table_id.get(table_id, set())
                if table_id is not None
                else set()
            )
            result[code] = {code} | children
        return result


class TableGroupQuery:
    """Query helpers around the TableGroup/TableGroupComposition models."""

    @staticmethod
    def get_member_table_codes(
        session: "Session",
        group_code: str,
        release_id: int | None,
    ) -> set[str]:
        """Return the table-version codes belonging to a table group.

        Args:
            session: SQLAlchemy session.
            group_code: The table group's code.
            release_id: Release filter.

        Returns:
            The set of member table-version codes at that release.
        """
        group_ids = [
            gid
            for (gid,) in filter_by_release(
                session.query(TableGroup.table_group_id).filter(
                    TableGroup.code == group_code
                ),
                start_col=TableGroup.start_release_id,
                end_col=TableGroup.end_release_id,
                release_id=release_id,
            ).all()
        ]
        if not group_ids:
            return set()

        table_ids = [
            tid
            for (tid,) in filter_by_release(
                session.query(TableGroupComposition.table_id).filter(
                    TableGroupComposition.table_group_id.in_(group_ids)
                ),
                start_col=TableGroupComposition.start_release_id,
                end_col=TableGroupComposition.end_release_id,
                release_id=release_id,
            ).all()
        ]
        if not table_ids:
            return set()

        codes = filter_by_release(
            session.query(TableVersion.code).filter(
                TableVersion.table_id.in_(table_ids)
            ),
            start_col=TableVersion.start_release_id,
            end_col=TableVersion.end_release_id,
            release_id=release_id,
        ).all()
        return {code for (code,) in codes if code is not None}


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


def _exclude_collapsed_reference_window(query: Any) -> Any:
    """Drop module versions whose reference-date window is a single day.

    Per EBA business rule, a module version with
    ``FromReferenceDate == ToReferenceDate`` describes a single reporting
    reference date and is never used for scope. Open-ended windows
    (``ToReferenceDate IS NULL``) and genuine multi-day ranges are kept.

    Args:
        query: A session-bound ``ModuleVersion``-bearing query (typed
            ``Any`` to match ``filter_by_release`` and allow reassignment
            to the caller's narrowly-typed query variable).

    Returns:
        The query with collapsed-window versions filtered out.
    """
    return query.filter(
        or_(
            ModuleVersion.from_reference_date.is_(None),
            ModuleVersion.to_reference_date.is_(None),
            ModuleVersion.from_reference_date
            != ModuleVersion.to_reference_date,
        )
    )


# ------------------------------------------------------------------ #
# Ghost-module-version fallback (issue #182)
# ------------------------------------------------------------------ #
#
# Some module versions carry a *collapsed* reference-date window
# (``FromReferenceDate == ToReferenceDate``) even though their release
# window genuinely spans several releases -- a known, un-fixable source
# data error. These "ghost" versions are never usable for scope, so when
# the only version whose release window covers a target release is a
# ghost the release would otherwise resolve to an empty scope. Instead we
# fall back to the most recent *prior* non-collapsed version of the same
# module. The search is strictly backward, so it never selects a version
# whose release window begins after the target release (#151 safety).

_MODULE_VID_COL = "ModuleVID"
_FROM_REF_COL = "FromReferenceDate"
_TO_REF_COL = "ToReferenceDate"


def _collapsed_mask(df: pd.DataFrame) -> "pd.Series[bool]":
    """Boolean mask of rows whose reference-date window is collapsed.

    DataFrame-level mirror of :func:`_exclude_collapsed_reference_window`:
    a row is collapsed only when both reference dates are present and
    equal. Open-ended windows (``None``/``NaT`` on either bound) are
    genuine ranges, not collapsed.

    Args:
        df: A module-version DataFrame with ``FromReferenceDate`` and
            ``ToReferenceDate`` columns.

    Returns:
        Boolean Series aligned with ``df``; ``True`` marks a ghost row.
    """
    frm = df[_FROM_REF_COL]
    to = df[_TO_REF_COL]
    return frm.notna() & to.notna() & (frm == to)


def _drop_collapsed_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Return ``df`` without its collapsed (ghost) reference-date rows."""
    if df.empty:
        return df
    return df[~_collapsed_mask(df)]


def _module_ids_for_vids(
    session: "Session", vids: Sequence[int]
) -> dict[int, int]:
    """Map module-version VIDs to their owning module id.

    Args:
        session: SQLAlchemy session.
        vids: Module-version ids to resolve.

    Returns:
        Mapping ``{module_vid: module_id}`` for VIDs that exist and carry
        a module id.
    """
    if not vids:
        return {}
    rows = (
        session.query(ModuleVersion.module_vid, ModuleVersion.module_id)
        .filter(ModuleVersion.module_vid.in_(list(set(vids))))
        .all()
    )
    return {vid: mid for vid, mid in rows if mid is not None}


def _latest_prior_non_collapsed_vids(
    session: "Session",
    module_ids: set[int],
    release_id: int,
) -> dict[int, int]:
    """Latest prior non-ghost version per module for a target release.

    For each module id, return the ``ModuleVID`` of the most recent
    module version that (a) has a genuine (non-collapsed) reference-date
    window and (b) whose release-window start is on or before the target
    release on the date-based sort order. The search is strictly backward: a
    version whose release window begins *after* the target is never
    chosen, preserving the #151 release-axis safety constraint. Modules
    with no such version are omitted, so the caller keeps the clean
    "no module versions" outcome for them.

    Args:
        session: SQLAlchemy session.
        module_ids: Modules whose sole release-covering version is a
            ghost.
        release_id: Target release id.

    Returns:
        Mapping ``{module_id: fallback_module_vid}``.
    """
    if not module_ids:
        return {}
    target = resolve_sort_order(session, release_id)
    sort_orders = load_release_sort_orders(session)
    prior_start_ids = release_ids_for_sort_order(sort_orders, le=target)
    if not prior_start_ids:
        return {}
    query = session.query(
        ModuleVersion.module_id,
        ModuleVersion.module_vid,
        ModuleVersion.start_release_id,
    ).filter(
        ModuleVersion.module_id.in_(module_ids),
        ModuleVersion.start_release_id.in_(prior_start_ids),
    )
    query = _exclude_collapsed_reference_window(query)
    best: dict[int, tuple[int, int]] = {}
    for module_id, vid, start_id in query.all():
        order = sort_orders.get(start_id)
        if order is None:
            continue
        current = best.get(module_id)
        if current is None or (order, vid) > current:
            best[module_id] = (order, vid)
    return {module_id: vid for module_id, (_, vid) in best.items()}


def _release_filter(release_id: int | None) -> Callable[[Any], Any]:
    """Return a module filter narrowing to the target release window."""

    def apply(query: Any) -> Any:
        return filter_by_release(
            query,
            start_col=ModuleVersion.start_release_id,
            end_col=ModuleVersion.end_release_id,
            release_id=release_id,
        )

    return apply


def _vids_filter(vids: Sequence[int]) -> Callable[[Any], Any]:
    """Return a module filter narrowing to an explicit set of VIDs."""

    def apply(query: Any) -> Any:
        return query.filter(ModuleVersion.module_vid.in_(list(vids)))

    return apply


def _resolve_covering(
    build_query: Callable[[Callable[[Any], Any]], Any],
    materialize: Callable[[Any], list[Any]],
    cols: list[str],
    release_id: int | None,
) -> pd.DataFrame:
    """Release-filtered module versions, ghosts included as-is.

    A ghost is still a real module version covering the release window;
    it only lacks a distinct reporting period, which matters for scope
    resolution (see :func:`_resolve_with_ghost_fallback`) but not for a
    plain "does this belong to a live module version" check.
    """
    return pd.DataFrame(
        materialize(build_query(_release_filter(release_id))),
        columns=cols,
    )


def _resolve_with_ghost_fallback(
    session: "Session",
    build_query: Callable[[Callable[[Any], Any]], Any],
    materialize: Callable[[Any], list[Any]],
    cols: list[str],
    release_id: int | None,
) -> pd.DataFrame:
    """Resolve module versions for a release, applying ghost fallback.

    Runs the caller's release-filtered lookup, then for any module whose
    sole release-covering version is a ghost substitutes the latest prior
    non-collapsed version of that module (see
    :func:`_latest_prior_non_collapsed_vids`). Modules with no prior
    non-ghost version are left out, so the caller still reports the clean
    "no module versions" outcome for them. Re-fetching the fallback
    version's operand rows (rather than rewriting the ghost row) means a
    fallback row appears only if that version genuinely contains the
    requested table / precondition.

    Args:
        session: SQLAlchemy session.
        build_query: Builds the lookup's joined query given a
            ``module_filter`` callable that narrows ``ModuleVersion`` to
            either the target release or an explicit set of VIDs.
        materialize: Executes a built query and returns its rows (e.g.
            ``chunked_in`` over the operand column, or ``query.all()``).
        cols: Output DataFrame column names.
        release_id: Target release id, or ``None`` for no release filter.

    Returns:
        DataFrame of resolved module versions, ghosts replaced by their
        prior non-collapsed fallback where one exists.
    """
    covering = _resolve_covering(build_query, materialize, cols, release_id)
    # Without a target release there is no "prior" to fall back to;
    # keep the historical behaviour of simply dropping ghosts.
    if release_id is None or covering.empty:
        return _drop_collapsed_rows(covering)

    ghost = _collapsed_mask(covering)
    non_ghost = covering[~ghost]
    vid_to_module = _module_ids_for_vids(
        session, covering[_MODULE_VID_COL].tolist()
    )
    ghost_modules = {
        vid_to_module[v]
        for v in covering.loc[ghost, _MODULE_VID_COL]
        if v in vid_to_module
    }
    kept_modules = {
        vid_to_module[v]
        for v in non_ghost[_MODULE_VID_COL]
        if v in vid_to_module
    }
    need = ghost_modules - kept_modules
    fallback = _latest_prior_non_collapsed_vids(session, need, release_id)
    if not fallback:
        return non_ghost

    fallback_rows = _drop_collapsed_rows(
        pd.DataFrame(
            materialize(build_query(_vids_filter(list(fallback.values())))),
            columns=cols,
        )
    )
    # The fallback version may not actually host the requested operand (its
    # composition can differ from the ghost's), leaving nothing to add.
    if fallback_rows.empty:
        return non_ghost
    return pd.concat([non_ghost, fallback_rows], ignore_index=True)


class _TableVersionScope(NamedTuple):
    """The table version(s) of one table code effective at a release.

    Attributes:
        table_vids: ``TableVersion.table_vid`` values to read cells from.
        fallback_module_vids: The module versions hosting ``table_vids``
            when the ghost fallback fired, ``None`` when the plain release
            window applies. A fallback version's release window ends
            *before* the target release, so callers must narrow the
            ``ModuleVersion`` join to these VIDs rather than applying
            :func:`filter_by_release`, which would drop every row.
    """

    table_vids: list[int]
    fallback_module_vids: list[int] | None = None


def _is_collapsed_window(from_date: Any, to_date: Any) -> bool:
    """Whether one version's reference-date window is collapsed (ghost).

    Row-level mirror of :func:`_collapsed_mask`: collapsed only when both
    reference dates are present and equal; an open-ended window is a
    genuine range.
    """
    return (
        from_date is not None and to_date is not None and from_date == to_date
    )


def _ghost_module_ids_for_table_vids(
    session: "Session",
    table_vids: Sequence[int],
    release_id: int,
) -> set[int] | None:
    """Modules whose ghosts are the only versions hosting ``table_vids``.

    Args:
        session: SQLAlchemy session.
        table_vids: Table versions open at ``release_id``.
        release_id: Target release id.

    Returns:
        The module ids of those ghosts, or ``None`` as soon as a
        non-ghost module version covering ``release_id`` hosts one of
        ``table_vids`` (the table version is then genuinely live at the
        release and needs no substitution). Also ``None`` when no module
        version hosts them at all.

        The decision is all-or-nothing over ``table_vids``: a live host
        for *any* of them suppresses substitution for the whole set.
        That only matters when one table code has several versions open
        at once, which happens at the perpetual release alone (see
        :meth:`ViewDatapointsQuery._resolve_table_version_scope`), and
        deciding per version would also have to merge the live module
        versions into ``_TableVersionScope.fallback_module_vids`` --
        :meth:`ViewDatapointsQuery._module_membership` restricts
        membership to that list instead of applying the release filter,
        so a live version left out of it would lose its rows.
    """
    rows = (
        filter_by_release(
            session.query(
                ModuleVersion.module_id,
                ModuleVersion.from_reference_date,
                ModuleVersion.to_reference_date,
            )
            .join(
                ModuleVersionComposition,
                ModuleVersion.module_vid
                == ModuleVersionComposition.module_vid,
            )
            .filter(ModuleVersionComposition.table_vid.in_(list(table_vids))),
            start_col=ModuleVersion.start_release_id,
            end_col=ModuleVersion.end_release_id,
            release_id=release_id,
        )
        .distinct()
        .all()
    )
    ghost_module_ids: set[int] = set()
    for module_id, from_date, to_date in rows:
        if not _is_collapsed_window(from_date, to_date):
            return None
        if module_id is not None:
            ghost_module_ids.add(module_id)
    return ghost_module_ids or None


def _apply_table_ghost_fallback(
    session: "Session",
    table: str,
    table_vids: list[int],
    release_id: int,
) -> _TableVersionScope:
    """Substitute a ghost-only table version with its fallback's (#356).

    The table-version mirror of :func:`_resolve_with_ghost_fallback`: when
    every module version hosting ``table_vids`` at ``release_id`` is a
    ghost, the table's cells are read from the latest prior non-ghost
    version of the same module instead, so datapoint resolution and module
    resolution report the same module version. Without it the cells --
    hence their variables, properties and domains -- come from a version
    that has no reporting period of its own.

    Kept separate from that helper rather than calling it: the caller
    needs a scope (the effective ``table_vids`` *and* the module
    versions the ``ModuleVersion`` join must be narrowed to), not the
    operand rows the helper returns; a ghost with no fallback is kept
    here instead of dropped, since dropping it would leave ``table``
    unresolvable rather than merely unscoped; and the decision is made
    once per table code rather than per module.

    Substitution only: when there is nothing to fall back to (no prior
    non-ghost version, or one that does not contain ``table``) the ghost's
    table version is kept, since dropping it would make the table
    unresolvable at that release.

    Args:
        session: SQLAlchemy session.
        table: Table version code being resolved.
        table_vids: The versions of ``table`` open at ``release_id``.
        release_id: Target release id.

    Returns:
        The effective scope, ghost substituted where a fallback exists.
    """
    ghost_module_ids = _ghost_module_ids_for_table_vids(
        session, table_vids, release_id
    )
    if ghost_module_ids is None:
        return _TableVersionScope(table_vids)
    fallback_vids = _latest_prior_non_collapsed_vids(
        session, ghost_module_ids, release_id
    )
    if not fallback_vids:
        return _TableVersionScope(table_vids)
    rows = (
        session.query(
            ModuleVersionComposition.module_vid,
            ModuleVersionComposition.table_vid,
        )
        .join(
            TableVersion,
            TableVersion.table_vid == ModuleVersionComposition.table_vid,
        )
        .filter(
            ModuleVersionComposition.module_vid.in_(
                list(fallback_vids.values())
            ),
            TableVersion.code == table,
        )
        .distinct()
        .all()
    )
    if not rows:
        return _TableVersionScope(table_vids)
    return _TableVersionScope(
        sorted({table_vid for _module_vid, table_vid in rows}),
        sorted({module_vid for module_vid, _table_vid in rows}),
    )


class ModuleVersionQuery:
    """Query helpers around ModuleVersion."""

    @staticmethod
    def ghost_fallbacks(
        session: "Session",
        release_id: int,
    ) -> dict[int, list[int]]:
        """Map each fallback module version to the ghosts it stands in for.

        The module-level statement of the #182 rule, for callers holding
        a ``ModuleVersion`` rather than operand rows: a module whose
        *every* release-covering version is a ghost is represented at
        ``release_id`` by the latest prior non-collapsed version of the
        same module (see :func:`_latest_prior_non_collapsed_vids`).
        Modules with a genuine covering version, and ghosts with nothing
        prior to stand in for them, are left out -- the caller keeps the
        clean "module not present at this release" outcome for the
        latter.

        Where :func:`_resolve_with_ghost_fallback` re-runs the caller's
        operand lookup against the fallback version, this only *reports*
        the substitution, so a caller can both enumerate the fallback as
        the release's export target and read the ghost's operation
        scopes through it (#372).

        The scan is release-wide rather than narrowed to a module: the
        ghost/genuine partition is per-module, so a single module's
        entry is the same either way, and one release-wide result can be
        cached and shared across every module of a sweep.

        Args:
            session: SQLAlchemy session.
            release_id: Target release id.

        Returns:
            Mapping ``{fallback_module_vid: [ghost_module_vid, ...]}``,
            the ghost VIDs sorted.
        """
        query = filter_by_release(
            session.query(
                ModuleVersion.module_id,
                ModuleVersion.module_vid,
                ModuleVersion.from_reference_date,
                ModuleVersion.to_reference_date,
            ),
            start_col=ModuleVersion.start_release_id,
            end_col=ModuleVersion.end_release_id,
            release_id=release_id,
        )
        ghosts: dict[int, list[int]] = {}
        genuine: set[int] = set()
        for module_id, module_vid, from_date, to_date in query.all():
            if module_id is None:
                continue
            if _is_collapsed_window(from_date, to_date):
                ghosts.setdefault(module_id, []).append(module_vid)
            else:
                genuine.add(module_id)
        fallback = _latest_prior_non_collapsed_vids(
            session, set(ghosts) - genuine, release_id
        )
        return {
            module_vid: sorted(ghosts[module_id])
            for module_id, module_vid in fallback.items()
        }

    @staticmethod
    def get_last_release(
        session: "Session",
    ) -> int | None:
        """Return the ID of the latest release by the date sort order.

        Releases are ranked by :func:`compute_sort_order` (from
        ``Release.date``), not the opaque ``release_id`` FK, which is
        non-monotonic from DPM 4.2.1 onwards (e.g. ``4.2.1`` is
        ``ReleaseID 1010000003``), so the highest id is not necessarily
        the latest release. An undated (unpublished) release sorts as the
        latest; ties are broken by ``release_id`` for determinism.

        Args:
            session: SQLAlchemy session.

        Returns:
            Integer release ID of the latest release, or ``None`` when
            there are no releases.
        """
        sort_orders = load_release_sort_orders(session)
        if not sort_orders:
            return None
        return max((so, rid) for rid, so in sort_orders.items())[1]

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

        def build_query(module_filter: Callable[[Any], Any]) -> Any:
            query = session.query(
                ModuleVersion.module_vid.label("ModuleVID"),
                ModuleVersionComposition.table_vid.label("variable_vid"),
                ModuleVersion.code.label("ModuleCode"),
                ModuleVersion.version_number.label("VersionNumber"),
                ModuleVersion.from_reference_date.label("FromReferenceDate"),
                ModuleVersion.to_reference_date.label("ToReferenceDate"),
                ModuleVersion.start_release_id.label("StartReleaseID"),
                ModuleVersion.end_release_id.label("EndReleaseID"),
            ).join(
                ModuleVersionComposition,
                ModuleVersion.module_vid
                == ModuleVersionComposition.module_vid,
            )
            return module_filter(query)

        def materialize(query: Any) -> list[Any]:
            return chunked_in(
                query, ModuleVersionComposition.table_vid, tables_vids
            )

        return _resolve_with_ghost_fallback(
            session, build_query, materialize, cols, release_id
        )

    @staticmethod
    def get_from_table_codes(
        session: "Session",
        table_codes: Sequence[str],
        release_id: int | None = None,
        include_ghosts: bool = False,
    ) -> pd.DataFrame:
        """Query modules by table codes.

        Args:
            session: SQLAlchemy session.
            table_codes: List of table codes.
            release_id: Optional release filter.
            include_ghosts: When True, skip the ghost-fallback
                substitution and return the raw release-covering rows,
                ghosts included. Leave False for scope computation,
                where a ghost has no reporting period of its own.

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

        def build_query(module_filter: Callable[[Any], Any]) -> Any:
            query = (
                session.query(
                    ModuleVersion.module_vid.label("ModuleVID"),
                    ModuleVersionComposition.table_vid.label("variable_vid"),
                    ModuleVersion.code.label("ModuleCode"),
                    ModuleVersion.version_number.label("VersionNumber"),
                    ModuleVersion.from_reference_date.label(
                        "FromReferenceDate"
                    ),
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
                    ModuleVersionComposition.table_vid
                    == TableVersion.table_vid,
                )
            )
            return module_filter(query)

        def materialize(query: Any) -> list[Any]:
            return chunked_in(query, TableVersion.code, table_codes)

        if include_ghosts:
            return _resolve_covering(
                build_query, materialize, cols, release_id
            )
        return _resolve_with_ghost_fallback(
            session, build_query, materialize, cols, release_id
        )

    @staticmethod
    def get_precondition_module_versions(
        session: "Session",
        precondition_items: Sequence[str],
        release_id: int | None = None,
        include_ghosts: bool = False,
    ) -> pd.DataFrame:
        """Query modules for precondition items.

        Args:
            session: SQLAlchemy session.
            precondition_items: Filing indicator codes.
            release_id: Optional release filter.
            include_ghosts: When True, skip the ghost-fallback
                substitution and return the raw release-covering rows,
                ghosts included. Leave False for scope computation,
                where a ghost has no reporting period of its own.

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

        def build_query(module_filter: Callable[[Any], Any]) -> Any:
            query = (
                session.query(
                    ModuleVersion.module_vid.label("ModuleVID"),
                    VariableVersion.variable_vid.label("variable_vid"),
                    ModuleVersion.code.label("ModuleCode"),
                    ModuleVersion.version_number.label("VersionNumber"),
                    ModuleVersion.from_reference_date.label(
                        "FromReferenceDate"
                    ),
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
                    ModuleParameters.variable_vid
                    == VariableVersion.variable_vid,
                )
                .join(
                    Variable,
                    VariableVersion.variable_id == Variable.variable_id,
                )
                .filter(VariableVersion.code.in_(precondition_items))
                .filter(_is_filing_indicator())
            )
            return module_filter(query)

        def materialize(query: Any) -> list[Any]:
            return query.all()

        if include_ghosts:
            return _resolve_covering(
                build_query, materialize, cols, release_id
            )
        return _resolve_with_ghost_fallback(
            session, build_query, materialize, cols, release_id
        )

    @staticmethod
    def get_filing_indicator_codes(
        session: "Session",
        codes: Collection[str],
    ) -> set[str]:
        """Return the subset of ``codes`` that are filing-indicator variables.

        Only filing-indicator preconditions constrain an operation's module
        scope. Precondition variables that are *not* filing indicators (for
        example a business-model attribute compared against a set of values,
        ``{vBM} in {'G-SIB', ...}``) are value conditions, not scoping
        conditions, and must not force module resolution or fail scope
        calculation. This helper lets scope calculation tell the two apart,
        so a genuinely-missing filing indicator still errors while a value
        condition is simply ignored.
        """
        if not codes:
            return set()
        rows = (
            session.query(VariableVersion.code)
            .join(
                Variable,
                VariableVersion.variable_id == Variable.variable_id,
            )
            .filter(VariableVersion.code.in_(list(codes)))
            .filter(_is_filing_indicator())
            .distinct()
            .all()
        )
        return {row[0] for row in rows}

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
            bool,
        ],
        pd.DataFrame,
    ] = {}

    # ``{axis: {code: order}}`` per (engine, table, release). An axis maps to
    # ``None`` when it is not fully ordered (a code without a stored order, or
    # a code with two orders) so range resolution falls back to string
    # comparison for that whole axis.
    _AXIS_ORDER_CACHE: dict[
        tuple[Hashable, str, int | None, bool],
        dict[str, dict[str, int] | None],
    ] = {}

    # Cells of one table-version scope, with their axes resolved, keyed
    # by engine + table + the table versions themselves: every release
    # and ``live`` flag that resolves to the same versions, and every
    # cell selection over them, shares one fetch.
    _CELL_FRAME_CACHE: dict[
        tuple[Hashable, str, tuple[int, ...]],
        pd.DataFrame,
    ] = {}

    # The module versions a (table, release, live) scope resolves to,
    # and with them the table versions to read. Resolving one costs up
    # to four queries, and every cell selection over the same table
    # asked for the same answer.
    _MEMBERSHIP_CACHE: dict[
        tuple[Hashable, str, int | None, bool, bool],
        pd.DataFrame,
    ] = {}

    _AXES: tuple[tuple[str, str], ...] = (
        ("row", "row_id"),
        ("column", "column_id"),
        ("sheet", "sheet_id"),
    )

    # -- internal helpers ------------------------------------------ #

    @staticmethod
    def _pinned_header_pairs(
        session: "Session",
        table_vids: Sequence[int],
    ) -> dict[tuple[int, int], list[tuple[str | None, int | None]]]:
        """Return ``{(table_vid, header_id): [(code, order)]}`` for a scope.

        A table version pins the exact ``HeaderVersion`` of each of its
        headers through its ``TableVersionHeader`` rows, and stores their
        display order there. A table version has a few dozen headers
        against hundreds or thousands of cells, so they are read once
        here and applied to the cells in pandas
        (:meth:`_add_axis_columns`) rather than joined per cell and per
        axis. Those three joins, each of them a disjunction the optimiser
        could not turn into a seek, are what made a call scan millions of
        pages to return a handful of codes (issue #361).

        The join to ``HeaderVersion`` is an outer one: a row that pins no
        version still carries the display order, as it did when this was
        a left join on the cell query.

        Args:
            session: SQLAlchemy session.
            table_vids: The table versions in scope.

        Returns:
            The ``(code, order)`` pairs each header resolves to -- a list
            because nothing stops a header being pinned twice, and the
            join this replaces would have yielded a row for each.
        """
        rows = (
            session.query(
                TableVersionHeader.table_vid,
                TableVersionHeader.header_id,
                HeaderVersion.code,
                TableVersionHeader.order,
            )
            .select_from(TableVersionHeader)
            .outerjoin(
                HeaderVersion,
                HeaderVersion.header_vid == TableVersionHeader.header_vid,
            )
            .filter(TableVersionHeader.table_vid.in_(list(table_vids)))
            .all()
        )
        pinned: dict[tuple[int, int], list[tuple[str | None, int | None]]] = {}
        for table_vid, header_id, code, order in rows:
            pinned.setdefault((int(table_vid), int(header_id)), []).append(
                (code, order)
            )
        return pinned

    @staticmethod
    def _unpinned_header_pairs(
        session: "Session",
        header_ids: Collection[int],
    ) -> dict[int, list[tuple[str | None, int | None]]]:
        """Return ``{header_id: [(code, None)]}`` for unpinned headers.

        A table version with no ``TableVersionHeader`` row for one of the
        headers its cells point at falls back to matching
        ``HeaderVersion.HeaderID`` directly. Nothing then pins a version,
        so every version of that header answers -- and the header carries
        no display order, since the order is stored on the missing row.
        Both were already true of the outer join this replaces.

        Args:
            session: SQLAlchemy session.
            header_ids: The headers left unresolved by
                :meth:`_pinned_header_pairs`.

        Returns:
            The ``(code, None)`` pairs each of them resolves to, empty
            when there is nothing to fall back on.
        """
        if not header_ids:
            return {}
        rows = (
            session.query(HeaderVersion.header_id, HeaderVersion.code)
            .filter(HeaderVersion.header_id.in_(sorted(header_ids)))
            .all()
        )
        unpinned: dict[int, list[tuple[str | None, int | None]]] = {}
        for header_id, code in rows:
            unpinned.setdefault(int(header_id), []).append((code, None))
        return unpinned

    @classmethod
    def _unpinned_header_ids(
        cls,
        frame: pd.DataFrame,
        pinned: dict[tuple[int, int], list[tuple[str | None, int | None]]],
    ) -> set[int]:
        """Return the headers of ``frame``'s cells ``pinned`` does not cover.

        Args:
            frame: Cell frame carrying ``table_vid`` and the three axis
                header id columns.
            pinned: Map from :meth:`_pinned_header_pairs`.

        Returns:
            The header ids needing the direct fallback; a cell that has
            no header on an axis (a table without sheets) contributes
            none.
        """
        missing: set[int] = set()
        for _axis, id_col in cls._AXES:
            for table_vid, header_id in zip(
                frame["table_vid"], frame[id_col], strict=True
            ):
                if pd.isna(header_id):
                    continue
                if (int(table_vid), int(header_id)) not in pinned:
                    missing.add(int(header_id))
        return missing

    @classmethod
    def _add_axis_columns(
        cls,
        session: "Session",
        frame: pd.DataFrame,
        table_vids: Sequence[int],
    ) -> pd.DataFrame:
        """Add ``{row,column,sheet}_{code,order}`` to a cell frame.

        Each axis is resolved through the table version's own pinned
        header, falling back to the header id alone
        (:meth:`_unpinned_header_pairs`). A fallback header can resolve
        to several versions, so the frame is exploded per axis -- the
        same row multiplication the outer join produced, and the reason
        the pairs are kept as lists.

        Args:
            session: SQLAlchemy session.
            frame: Cell frame from :meth:`_cell_frame`, which this may
                modify.
            table_vids: The table versions in scope.

        Returns:
            The frame with the six axis columns added and the working
            columns dropped.
        """
        pinned = cls._pinned_header_pairs(session, table_vids)
        unpinned = cls._unpinned_header_pairs(
            session, cls._unpinned_header_ids(frame, pinned)
        )

        def pairs_of(
            table_vid: Any, header_id: Any
        ) -> list[tuple[str | None, int | None]]:
            if pd.isna(header_id):
                return [(None, None)]
            key = (int(table_vid), int(header_id))
            if key in pinned:
                return pinned[key]
            return unpinned.get(int(header_id), [(None, None)])

        for axis, id_col in cls._AXES:
            candidates = [
                pairs_of(table_vid, header_id)
                for table_vid, header_id in zip(
                    frame["table_vid"], frame[id_col], strict=True
                )
            ]
            if any(len(pair) > 1 for pair in candidates):
                # Only an unpinned header answers with several versions,
                # which is rare enough to be worth not rebuilding the
                # frame for the axes that resolve one to one.
                frame[f"{axis}_pair"] = pd.Series(
                    candidates, index=frame.index, dtype=object
                )
                frame = frame.explode(f"{axis}_pair")
                pairs = list(frame.pop(f"{axis}_pair"))
            else:
                pairs = [pair[0] for pair in candidates]
            frame[f"{axis}_code"] = [pair[0] for pair in pairs]
            frame[f"{axis}_order"] = [pair[1] for pair in pairs]
        return frame.reset_index(drop=True)

    @classmethod
    def _cell_frame(
        cls,
        session: "Session",
        table: str,
        table_vids: Sequence[int],
    ) -> pd.DataFrame:
        """Return every cell of ``table_vids``, with its axes resolved.

        The single query the three public methods are built on: the
        cells of the scoped table versions and the variable payload
        hanging off them, narrowed by nothing but ``table_vid``. Each
        method then selects its columns and applies its own cell
        selection in pandas, which keeps one shape of SQL -- and one
        execution per table version -- behind a whole validation run,
        however many different selections it asks for.

        Args:
            session: SQLAlchemy session.
            table: Table version code; every row carries it, so it is set
                as a column rather than joined back through
                ``TableVersion``.
            table_vids: The table versions to read cells from, already
                scoped by :meth:`_module_membership`.

        Returns:
            The cached frame for this scope. Callers must treat it as
            read-only and derive their result from it.
        """
        cache_key = (
            _get_engine_cache_key(session),
            table,
            tuple(sorted(table_vids)),
        )
        cached = cls._CELL_FRAME_CACHE.get(cache_key)
        if cached is not None:
            return cached

        query = (
            session.query()
            .select_from(TableVersionCell)
            .join(Cell, TableVersionCell.cell_id == Cell.cell_id)
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
            .add_columns(
                TableVersionCell.cell_code.label("cell_code"),
                TableVersionCell.cell_id.label("cell_id"),
                TableVersionCell.table_vid.label("table_vid"),
                Cell.row_id.label("row_id"),
                Cell.column_id.label("column_id"),
                Cell.sheet_id.label("sheet_id"),
                VariableVersion.variable_id.label("variable_id"),
                VariableVersion.variable_vid.label("variable_vid"),
                VariableVersion.context_id.label("context_id"),
                VariableVersion.property_id.label("variable_property_id"),
                Property.property_id.label("property_property_id"),
                DataType.code.label("data_type"),
            )
            .filter(
                TableVersionCell.is_void == False,  # noqa: E712
                TableVersionCell.table_vid.in_(list(table_vids)),
            )
        )
        frame = read_sql_with_connection(query.statement, session)
        frame["table_code"] = table
        frame = cls._add_axis_columns(session, frame, table_vids)
        cls._CELL_FRAME_CACHE[cache_key] = frame
        return frame

    @classmethod
    def _scoped_cell_frame(
        cls,
        session: "Session",
        table: str,
        release_id: int | None,
        live_table_versions: bool,
        scoped: bool = True,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Resolve ``table``'s scope at a release and read its cells.

        Args:
            session: SQLAlchemy session.
            table: Table version code.
            release_id: Release filter.
            live_table_versions: Resolve the table-version axis by
                :func:`~dpmcore.dpm_xl.utils.filters.filter_live_only`.
            scoped: ``False`` accepts every version of ``table`` a module
                version carries, whatever its release window -- what
                :meth:`get_filtered_datapoints` asks for when given
                neither a release nor the ``live`` flag.

        Returns:
            The cell frame of the resolved scope, and the module
            versions it is read through -- one row per module version,
            which :func:`_with_module_windows` fans the cells back out
            over for the frames that report the window.
        """
        cache_key = (
            _get_engine_cache_key(session),
            table,
            release_id,
            live_table_versions,
            scoped,
        )
        membership = cls._MEMBERSHIP_CACHE.get(cache_key)
        if membership is None:
            scope = (
                cls._resolve_table_version_scope(
                    session, table, release_id, live_only=live_table_versions
                )
                if scoped
                else None
            )
            membership = cls._module_membership(
                session, table, scope, release_id
            )
            cls._MEMBERSHIP_CACHE[cache_key] = membership
        table_vids = sorted(set(membership["table_vid"]))
        return cls._cell_frame(session, table, table_vids), membership

    @classmethod
    def _resolve_table_version_scope(
        cls,
        session: "Session",
        table: str,
        release_id: int | None,
        live_only: bool = False,
    ) -> _TableVersionScope:
        """Resolve the table version(s) of ``table`` effective at ``release_id``.

        At the perpetual release, an adopted version and one just started
        there can both compare as "open now". When both are present, only
        the adopted one(s) are kept.

        A version open at ``release_id`` only through a *ghost* module
        version is then substituted with the one the ghost fallback
        resolves to (see :func:`_apply_table_ghost_fallback`), so cells
        resolve through the same module version module resolution reports.

        Args:
            session: SQLAlchemy session.
            table: Table version code.
            release_id: Release filter; ``None`` resolves to whichever
                version(s) are currently open, and applies no ghost
                fallback -- without a target release there is no "prior"
                version to fall back to.
            live_only: Select the *live* version(s) instead -- open now
                and already published (:func:`filter_live_only`) --
                ignoring ``release_id`` on the table-version axis. The
                ghost fallback is skipped too: it substitutes the version
                effective at a release, which a live scope does not have.
                ``release_id`` still windows the module versions the
                cells are read through.

        Returns:
            The effective scope; its ``table_vids`` are empty when
            ``table`` has no version open at ``release_id``.
        """
        query = session.query(
            TableVersion.table_vid, TableVersion.start_release_id
        ).filter(TableVersion.code == table)
        if live_only:
            query = filter_live_only(
                query,
                start_col=TableVersion.start_release_id,
                end_col=TableVersion.end_release_id,
            )
        else:
            query = filter_by_release(
                query,
                start_col=TableVersion.start_release_id,
                end_col=TableVersion.end_release_id,
                release_id=release_id,
                active_only_fallback=True,
            )
        rows = query.all()
        if len(rows) <= 1:
            table_vids = [row.table_vid for row in rows]
        else:
            sort_orders = load_release_sort_orders(session)
            perpetual = compute_sort_order(None, None)
            # A NULL start release means "has always existed", not
            # "unpublished" -- the same rule filter_live_only applies.
            # Without this it misses ``sort_orders`` and falls back to
            # ``perpetual``, so a real version would be dropped here
            # right after being let through.
            adopted = [
                row.table_vid
                for row in rows
                if row.start_release_id is None
                or sort_orders.get(row.start_release_id, perpetual) < perpetual
            ]
            table_vids = adopted or [row.table_vid for row in rows]
        if not table_vids or release_id is None or live_only:
            return _TableVersionScope(table_vids)
        return _apply_table_ghost_fallback(
            session, table, table_vids, release_id
        )

    @staticmethod
    def _module_membership(
        session: "Session",
        table: str,
        scope: _TableVersionScope | None,
        release_id: int | None,
    ) -> pd.DataFrame:
        """Return the module versions carrying each version of ``table``.

        Module membership scopes which *table versions* may be read, not
        which cells: every cell of a table version shares its answer. It
        used to be a join on the cell query, which repeated each cell
        once per module version holding the table and left ``DISTINCT``
        (or the ``cell_code`` de-duplication in :meth:`get_table_data`)
        to collapse the fan-out again -- work proportional to the cells,
        for an answer that has one row per table version. Resolving it
        here costs one small query against ``ModuleVersionComposition``;
        the cell query then takes a plain ``IN`` list, and the frames
        that report the module version's release window rebuild the
        fan-out from these few rows (:func:`_with_module_windows`). This
        is half of issue #361; :meth:`_pinned_header_pairs` is the other
        half.

        Normally membership is windowed by the plain release window. In
        the ghost-fallback case the effective module versions are the
        fallback's, whose window ends *before* ``release_id``, so
        filtering by release would drop every version; membership is
        restricted to those module versions instead.

        Args:
            session: SQLAlchemy session.
            table: Table version code.
            scope: Scope from :meth:`_resolve_table_version_scope`, or
                ``None`` to accept every version of ``table`` that any
                module version carries -- what an unscoped
                :meth:`get_filtered_datapoints` call asks for.
            release_id: Release filter; ``None`` windows nothing.

        Returns:
            One row per (table version, module version carrying it),
            with the module version's release window, sorted by
            ``(table_vid, module_vid)`` -- the order
            :func:`_with_module_windows` fans the cells out in.
        """
        query = (
            session.query(
                ModuleVersionComposition.table_vid.label("table_vid"),
                ModuleVersion.module_vid.label("module_vid"),
                ModuleVersion.start_release_id.label("module_start_release"),
                ModuleVersion.end_release_id.label("module_end_release"),
            )
            .select_from(ModuleVersionComposition)
            .join(
                ModuleVersion,
                ModuleVersionComposition.module_vid
                == ModuleVersion.module_vid,
            )
            .join(
                TableVersion,
                TableVersion.table_vid == ModuleVersionComposition.table_vid,
            )
            .filter(TableVersion.code == table)
            .distinct()
        )
        if scope is not None:
            query = query.filter(
                ModuleVersionComposition.table_vid.in_(scope.table_vids)
            )
            if scope.fallback_module_vids is not None:
                query = query.filter(
                    ModuleVersion.module_vid.in_(scope.fallback_module_vids)
                )
            elif release_id is not None:
                query = filter_by_release(
                    query,
                    start_col=ModuleVersion.start_release_id,
                    end_col=ModuleVersion.end_release_id,
                    release_id=release_id,
                )
        membership = read_sql_with_connection(query.statement, session)
        return membership.sort_values(
            ["table_vid", "module_vid"], kind="stable"
        ).reset_index(drop=True)

    @classmethod
    def get_axis_orders(
        cls,
        session: "Session",
        table: str,
        release_id: int | None = None,
        live_table_versions: bool = False,
    ) -> dict[str, dict[str, int] | None]:
        """Return the ``{code: order}`` display order per axis of a table.

        The stored order is ``TableVersionHeader.Order``; this is the single
        source of truth used to resolve ranges by display order instead of by
        code text (mirroring ``load_release_sort_orders`` for releases).

        An axis maps to ``None`` when it is **not fully ordered** — some code
        lacks a stored order (the column is nullable and some headers have no
        ``TableVersionHeader`` row) or a code carries two different orders.
        Callers then fall back to string comparison for that whole axis, so
        order-based and string-based comparison are never mixed within an axis.

        Results are cached per engine + table + release, over a cell
        frame that is itself cached (:meth:`_cell_frame`), so the map
        matches the code universe of the data query by construction --
        it is read off the same rows.

        Args:
            session: SQLAlchemy session.
            table: Table version code.
            release_id: Optional release filter.
            live_table_versions: Resolve the table-version axis by
                :func:`~dpmcore.dpm_xl.utils.filters.filter_live_only`
                instead of by the release window, as
                :meth:`get_table_data` does under the same flag.

        Returns:
            ``{"rows"/"cols"/"sheets": {code: order} | None}``.
        """
        engine_key = _get_engine_cache_key(session)
        cache_key = (engine_key, table, release_id, live_table_versions)
        cached = cls._AXIS_ORDER_CACHE.get(cache_key)
        if cached is not None:
            return cached

        # No module-version fan-out here: it would repeat rows the map
        # builders already fold together, and contributes no column.
        data, _membership = cls._scoped_cell_frame(
            session, table, release_id, live_table_versions
        )

        axes = {
            "rows": ("row_code", "row_order"),
            "cols": ("column_code", "column_order"),
            "sheets": ("sheet_code", "sheet_order"),
        }
        result: dict[str, dict[str, int] | None] = {}
        for axis, (code_col, order_col) in axes.items():
            result[axis] = _build_axis_order_map(data, code_col, order_col)

        cls._AXIS_ORDER_CACHE[cache_key] = result
        return result

    @classmethod
    def _axis_orders_for(
        cls,
        session: "Session",
        table: str,
        release_id: int | None,
        selections: tuple[Sequence[str] | None, ...],
        live_table_versions: bool = False,
    ) -> dict[str, dict[str, int] | None]:
        """Return per-axis order maps, querying only when a range is present.

        Non-range selectors never consult the display order, so the
        ``get_axis_orders`` query is skipped and every axis maps to ``None``
        (a no-op for plain ``IN`` / ``==`` selectors).
        """
        has_range = any(
            v is not None and any("-" in x for x in v) for v in selections
        )
        if not has_range:
            return {"rows": None, "cols": None, "sheets": None}
        return cls.get_axis_orders(
            session, table, release_id, live_table_versions
        )

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
        live_table_versions: bool = False,
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
            live_table_versions: Read the cells of the table's *live*
                version -- open now and already published
                (:func:`~dpmcore.dpm_xl.utils.filters.filter_live_only`)
                -- instead of the version effective at ``release_id``.
                ``release_id`` still windows the module versions the
                cells are read through, so a draft table version
                introduced only in the working release never
                contributes cells. This is the rule the EBA
                ``drr_datapoints`` view bakes in.

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
            live_table_versions,
        )
        cached = cls._TABLE_DATA_CACHE.get(cache_key)
        if cached is not None:
            return cached

        data, membership = cls._scoped_cell_frame(
            session, table, release_id, live_table_versions
        )

        # Range endpoints are resolved against the stored display order, not
        # the code text; ``get_axis_orders`` supplies the per-axis map (or
        # ``None`` when the axis has no usable order -> string fallback). Only
        # fetch it when a range is actually present.
        axis_orders = cls._axis_orders_for(
            session,
            table,
            release_id,
            (rows, cols, sheets),
            live_table_versions,
        )

        selections = (
            (rows, "row_code", "rows"),
            (cols, "column_code", "cols"),
            (sheets, "sheet_code", "sheets"),
        )
        for values, code_col, axis in selections:
            if values is not None and values != ["*"]:
                data = _narrow_to_dimension(
                    data, code_col, values, axis_orders[axis]
                )

        data = _project(
            _with_module_windows(data, membership), _TABLE_DATA_COLUMNS
        )
        if len(data) > 0:
            # The sort has one job: push the grey cells last, so a cell
            # carrying a variable wins over the same cell rendered grey
            # in another table version. Everything else about it is a
            # tie -- the rows one cell is fanned out into share their
            # ``variable_id`` -- and the tie is meant to be broken by
            # the fan-out order (:func:`_with_module_windows`), so the
            # sort must not reorder ties. The default ``quicksort``
            # does, which left the surviving row to a numpy internal.
            data = data.sort_values(
                "variable_id", na_position="last", kind="stable"
            )
            data = data.drop_duplicates(subset=["cell_code"], keep="first")

        cls._TABLE_DATA_CACHE[cache_key] = data
        return data

    @classmethod
    def get_filtered_datapoints(
        cls,
        session: "Session",
        table: str,
        table_info: dict[str, Any],
        release_id: int | None = None,
        live_table_versions: bool = False,
    ) -> pd.DataFrame:
        """Retrieve datapoints with dimension filters.

        Args:
            session: SQLAlchemy session.
            table: Table version code.
            table_info: Dict with rows/cols/sheets lists.
            release_id: Optional release filter.
            live_table_versions: Restrict the table-version axis to the
                live version(s) -- see :meth:`get_table_data`. Unlike
                ``release_id``, this scopes the table version even when
                no release is given.

        Returns:
            DataFrame of filtered datapoints.
        """
        # Without a release or the ``live`` flag, every version of the
        # table a module version carries is in scope -- the rule the
        # ``ModuleVersion`` join carried on its own.
        data, membership = cls._scoped_cell_frame(
            session,
            table,
            release_id,
            live_table_versions,
            scoped=bool(release_id or live_table_versions),
        )

        axis_orders = cls._axis_orders_for(
            session,
            table,
            release_id,
            (
                table_info.get("rows"),
                table_info.get("cols"),
                table_info.get("sheets"),
            ),
            live_table_versions,
        )
        mapping = {
            "rows": "row_code",
            "cols": "column_code",
            "sheets": "sheet_code",
        }
        for key, values in table_info.items():
            if values is not None and key in mapping:
                mask = _dimension_mask(
                    data[mapping[key]], values, axis_orders[key]
                )
                if mask is not None:
                    data = data[mask]

        return (
            _project(
                _with_module_windows(data, membership, cell_major=True),
                _FILTERED_DATAPOINT_COLUMNS,
            )
            .drop_duplicates()
            .reset_index(drop=True)
        )


def _build_axis_order_map(
    data: pd.DataFrame, code_col: str, order_col: str
) -> dict[str, int] | None:
    """Build ``{code: order}`` for one axis from a code/order frame.

    Prefers each code's own numeric value over its stored display order,
    since some tables show a code out of numeric sequence. Returns ``None`` when neither is
    usable, so the caller falls back to string comparison for that whole axis.
    """
    if code_col not in data.columns:
        return None
    value_map = build_axis_value_map(data[code_col])
    if value_map:
        return value_map
    if order_col not in data.columns:
        return None
    return build_axis_order_map(data[code_col], data[order_col])


def _resolve_dimension_values(
    values: Sequence[str],
    order_map: dict[str, int] | None,
) -> tuple[set[str], list[tuple[str, str]]]:
    """Split axis selectors into concrete codes and unresolved ranges.

    Range selectors are expanded to their spanned codes via the display-order
    map. A range that cannot be resolved by order — reversed, or the axis has
    no usable order — is returned as an ``(lo, hi)`` endpoint pair for the
    caller to handle (widen or string ``between``). Wildcards (``*``) are
    skipped: they mean "the whole axis", i.e. no filter.

    Returns:
        ``(codes, unresolved_ranges)``.
    """
    codes: set[str] = set()
    unresolved: list[tuple[str, str]] = []
    for value in values:
        if value == "*":
            continue
        if "-" in value:
            lo, hi = value.split("-")
            spanned = (
                resolve_range_codes(order_map, lo, hi) if order_map else []
            )
            if spanned:
                codes.update(spanned)
            else:
                unresolved.append((lo, hi))
        else:
            codes.add(value)
    return codes, unresolved


# ``(source column, label)`` of the frames the datapoint methods return.
# The cell frame carries both property ids the two used to select --
# ``VariableVersion``'s and the ``Property`` row's, which differ when a
# variable points at a property that has no row -- so each keeps the one
# it read.
_TABLE_DATA_COLUMNS: tuple[tuple[str, str], ...] = (
    ("cell_code", "cell_code"),
    ("table_code", "table_code"),
    ("row_code", "row_code"),
    ("column_code", "column_code"),
    ("sheet_code", "sheet_code"),
    ("row_order", "row_order"),
    ("column_order", "column_order"),
    ("sheet_order", "sheet_order"),
    ("variable_id", "variable_id"),
    ("variable_property_id", "property_id"),
    ("data_type", "data_type"),
    ("table_vid", "table_vid"),
    ("cell_id", "cell_id"),
    ("module_start_release", "start_release_id"),
    ("module_end_release", "end_release_id"),
)

_FILTERED_DATAPOINT_COLUMNS: tuple[tuple[str, str], ...] = (
    ("cell_code", "cell_code"),
    ("table_code", "table_code"),
    ("row_code", "row_code"),
    ("column_code", "column_code"),
    ("sheet_code", "sheet_code"),
    ("row_order", "row_order"),
    ("column_order", "column_order"),
    ("sheet_order", "sheet_order"),
    ("variable_id", "variable_id"),
    ("data_type", "data_type"),
    ("table_vid", "table_vid"),
    ("property_property_id", "property_id"),
    ("module_start_release", "start_release"),
    ("module_end_release", "end_release"),
    ("cell_id", "cell_id"),
    ("context_id", "context_id"),
    ("variable_vid", "variable_vid"),
)


def _with_module_windows(
    data: pd.DataFrame,
    membership: pd.DataFrame,
    cell_major: bool = False,
) -> pd.DataFrame:
    """Repeat each cell once per module version carrying its table.

    The frames report the release window of the module version the
    cells were read through, and a table version in two module versions
    used to come back twice per cell because the join said so --
    collapsed again by ``DISTINCT`` in
    :meth:`~ViewDatapointsQuery.get_filtered_datapoints` and by the
    ``cell_code`` de-duplication in
    :meth:`~ViewDatapointsQuery.get_table_data`. The join is gone
    (:meth:`~ViewDatapointsQuery._module_membership`), so the same
    multiplicity is rebuilt here from the handful of rows it resolved
    to, rather than being carried through the cell query.

    The order matters, and the two methods need opposite ones -- which
    is what the joins they replace emitted, measured against them over
    the whole 4.2.1 dictionary rather than reasoned about. It matters
    because the rows one cell is repeated into differ in nothing but
    these two columns, so which of them survives the per-cell
    de-duplication in :meth:`~ViewDatapointsQuery.get_table_data`
    follows from their order alone: module-major there reproduces that
    method's answer in all 5,224 non-empty calls the dictionary has,
    where cell-major changes it in 409 of them. For
    :meth:`~ViewDatapointsQuery.get_filtered_datapoints`, whose
    ``DISTINCT`` kept every one of those rows, cell-major is the order
    that matches.

    Args:
        data: Cell frame to fan out.
        membership: One row per (table version, module version),
            sorted by ``(table_vid, module_vid)``.
        cell_major: Group by cell and then by module version, rather
            than the other way round.

    Returns:
        A new frame with the window columns added.
    """
    windows = membership[
        ["table_vid", "module_start_release", "module_end_release"]
    ]
    if cell_major:
        return data.merge(windows, on="table_vid", how="inner")
    return windows.merge(data, on="table_vid", how="inner")


def _project(
    data: pd.DataFrame, columns: Sequence[tuple[str, str]]
) -> pd.DataFrame:
    """Select and label the columns one datapoint method returns.

    Args:
        data: A cell frame from
            :meth:`ViewDatapointsQuery._cell_frame`.
        columns: ``(source column, label)`` pairs, in output order.

    Returns:
        A new frame; the shared cell frame is never handed out or
        modified.
    """
    projected = data[[source for source, _label in columns]]
    return _restore_sql_dtypes(projected.rename(columns=dict(columns)))


def _restore_sql_dtypes(frame: pd.DataFrame) -> pd.DataFrame:
    """Give a selection the dtypes reading it from SQL used to give it.

    pandas infers a frame's dtypes from the rows it is built from, so an
    id column came back ``int64`` when the selected rows carried no
    ``NULL``, ``float64`` when some did and ``object`` when all of them
    did. The cells are now read once per table version and narrowed in
    pandas, where those dtypes are fixed by the whole table rather than
    by the selection: a grey cell anywhere in it would leave a selection
    containing none as ``float64``, handing callers ``1234.0`` where they
    used to get ``1234`` -- and putting that straight into a dependency
    list.

    Args:
        frame: A projected frame, already a copy.

    Returns:
        The same frame, re-typed column by column.
    """
    for column in frame.columns:
        values = frame[column]
        if values.dtype != "float64":
            continue
        if bool(values.isna().all()):
            frame[column] = pd.Series(
                [None] * len(values), index=values.index, dtype=object
            )
        elif bool(values.notna().all()) and bool((values % 1 == 0).all()):
            frame[column] = values.astype("int64")
    return frame


def _narrow_to_dimension(
    data: pd.DataFrame,
    code_col: str,
    values: Sequence[str],
    order_map: dict[str, int] | None,
) -> pd.DataFrame:
    """Apply a row/col/sheet dimension filter for ``get_table_data``.

    Ranges are resolved to concrete codes by display order. If a range
    cannot be resolved by order (reversed, or the axis is not fully
    ordered), the axis filter is **widened** — dropped entirely — rather
    than compared by code text: ``get_table_data`` is always re-filtered
    by the order-aware ``filter_all_data`` pass, which stays the
    authoritative narrower and the source of the ``1-2`` endpoint error,
    so it must never under-fetch.

    Args:
        data: Cell frame to narrow.
        code_col: Header code column of the axis being filtered.
        values: List of filter values (may have ranges).
        order_map: ``{code: order}`` for this axis, or ``None`` when the axis
            has no usable order.

    Returns:
        The narrowed frame, or ``data`` itself when the filter widens.
    """
    codes, unresolved = _resolve_dimension_values(values, order_map)
    if unresolved or not codes:
        return data
    return data[data[code_col].isin(codes)]


def _dimension_mask(
    code_column: "pd.Series[Any]",
    values: Sequence[str],
    order_map: dict[str, int] | None,
) -> "pd.Series[bool] | None":
    """Build a dimension filter mask for ``get_filtered_datapoints``.

    Like :func:`_narrow_to_dimension` but never widens: a range that
    cannot be resolved by order falls back to comparing the code text
    (this method's result is used directly, without a
    ``filter_all_data`` re-filter, so it must still narrow). Returns
    ``None`` when there is nothing to filter (e.g. an all-wildcard
    selection).

    A cell with no header on the axis is excluded either way, as the
    ``NULL`` it carries was by the SQL comparison this replaces.

    Args:
        code_column: Header code column of the axis being filtered.
        values: List of filter values (may have ranges).
        order_map: ``{code: order}`` for this axis, or ``None``.

    Returns:
        The row mask, or ``None`` when the selection filters nothing.
    """
    codes, unresolved = _resolve_dimension_values(values, order_map)
    masks: list["pd.Series[bool]"] = []
    if codes:
        masks.append(code_column.isin(codes))
    if unresolved:
        # An axis no cell carries comes back as NaN, which compares with
        # neither endpoint; ``present`` reproduces the ``NULL BETWEEN``
        # that excluded it, over text the comparison accepts.
        present = code_column.notna()
        text = code_column.fillna("").astype(str)
        masks.extend(
            present & (text >= lo) & (text <= hi) for lo, hi in unresolved
        )
    if not masks:
        return None
    selected = masks[0]
    for mask in masks[1:]:
        selected = selected | mask
    return selected


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
        query = filter_by_release(
            query,
            start_col=ItemCategory.start_release_id,
            end_col=ItemCategory.end_release_id,
            release_id=release_id,
            active_only_fallback=True,
        )
        query = filter_by_release(
            query,
            start_col=ModuleVersion.start_release_id,
            end_col=ModuleVersion.end_release_id,
            release_id=release_id,
            active_only_fallback=True,
        )
        query = query.distinct()
        return read_sql_with_connection(query.statement, session)


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
        query = filter_by_release(
            query,
            start_col=ItemCategory.start_release_id,
            end_col=ItemCategory.end_release_id,
            release_id=release_id,
            active_only_fallback=True,
        )
        query = query.distinct()
        return read_sql_with_connection(query.statement, session)


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
        return read_sql_with_connection(query.statement, session)
