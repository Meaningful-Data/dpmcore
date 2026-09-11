"""Shared helper: open-key (compound-key) lookups per table.

Kept as a module-level function rather than a service method so both
:class:`~dpmcore.services.data_dictionary.DataDictionaryService` and
:class:`~dpmcore.services.scope_calculator.ScopeCalculatorService` can
use it without one service reaching into the private surface of the
other.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional

from sqlalchemy import or_

from dpmcore.orm.glossary import ItemCategory, Property
from dpmcore.orm.infrastructure import DataType
from dpmcore.orm.query_utils import chunked_in
from dpmcore.orm.rendering import TableVersion
from dpmcore.orm.variables import KeyComposition, VariableVersion

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def get_open_keys_for_tables(
    session: "Session",
    table_codes: List[str],
    release_id: Optional[int] = None,
) -> Dict[str, Dict[str, str]]:
    """Return ``{table_code: {property_code: data_type_code}}``.

    Identifies the open-key (compound-key) variables of each table by
    walking ``TableVersion`` → ``KeyComposition`` → ``VariableVersion``
    → ``Property`` → ``ItemCategory`` (for the property code) →
    ``DataType`` (for the type code). When ``release_id`` is given the
    query restricts to ``TableVersion`` rows whose release window
    contains it.
    """
    result: Dict[str, Dict[str, str]] = {code: {} for code in table_codes}
    if not table_codes:
        return result

    query = (
        session.query(
            TableVersion.code.label("table_code"),
            ItemCategory.code.label("property_code"),
            DataType.code.label("data_type_code"),
        )
        .select_from(DataType)
        .join(Property, DataType.data_type_id == Property.data_type_id)
        .join(ItemCategory, Property.property_id == ItemCategory.item_id)
        .join(
            VariableVersion,
            ItemCategory.item_id == VariableVersion.property_id,
        )
        .join(
            KeyComposition,
            VariableVersion.variable_vid == KeyComposition.variable_vid,
        )
        .join(
            TableVersion,
            KeyComposition.key_id == TableVersion.key_id,
        )
    )

    if release_id is not None:
        # ``ReleaseID`` values are opaque from DPM 4.2.1 onwards — 4.2.1
        # is ``1010000003`` while older releases stay in 1..5, and the
        # transitional ``Playground`` release has an ID larger than
        # 4.2.1's despite predating it. Release-range comparisons must
        # therefore go through the date-based sort order in
        # :mod:`dpmcore.orm.release_sort_order` rather than compare the
        # numeric IDs directly — a numeric filter happens to give the
        # right answer for a monotonic ID sequence but silently returns
        # the wrong window when a release lands out of numeric order.
        from dpmcore.orm.release_sort_order import (
            load_release_sort_orders,
            release_ids_for_sort_order,
        )

        sort_orders = load_release_sort_orders(session)
        target_sort = sort_orders.get(release_id)
        if target_sort is None:
            raise ValueError(
                f"release {release_id} has no sort_order — "
                "no Release row matches that ID."
            )
        start_ids = release_ids_for_sort_order(sort_orders, le=target_sort)
        end_ids = release_ids_for_sort_order(sort_orders, gt=target_sort)
        query = query.filter(
            TableVersion.start_release_id.in_(start_ids),
            or_(
                TableVersion.end_release_id.is_(None),
                TableVersion.end_release_id.in_(end_ids),
            ),
            # ItemCategory has its own release window: a property can
            # be renamed across releases (e.g. ``LES`` up to release 3,
            # ``qLES`` from release 3 onwards) and both rows share the
            # same ``ItemID``. Without this filter both codes end up in
            # the open_keys map for any release, duplicating each
            # property with its historical alias.
            ItemCategory.start_release_id.in_(start_ids),
            or_(
                ItemCategory.end_release_id.is_(None),
                ItemCategory.end_release_id.in_(end_ids),
            ),
        )
    else:
        # No target release: keep only the currently open ItemCategory
        # row per ItemID. Without this a property renamed across
        # releases (e.g. ``LES`` up to release 3, ``qLES`` from release
        # 3+ sharing the same ``ItemID``) returns both codes for the
        # same table, duplicating each open key with its historical
        # alias.
        query = query.filter(ItemCategory.end_release_id.is_(None))

    query = query.distinct().order_by(TableVersion.code, ItemCategory.code)
    rows = chunked_in(query, TableVersion.code, table_codes)
    for row in rows:
        tcode = row.table_code
        pcode = row.property_code
        dcode = row.data_type_code or ""
        if tcode and pcode:
            result.setdefault(tcode, {})[pcode] = dcode
    return result
