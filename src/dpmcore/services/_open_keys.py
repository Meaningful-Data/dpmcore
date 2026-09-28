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
from dpmcore.orm.rendering import (
    Header,
    HeaderVersion,
    TableVersion,
    TableVersionHeader,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def get_open_keys_for_tables(
    session: "Session",
    table_codes: List[str],
    release_id: Optional[int] = None,
    table_vids: Optional[List[int]] = None,
) -> Dict[str, Dict[str, str]]:
    """Return ``{table_code: {property_code: data_type_code}}``.

    Identifies the open-key (compound-key) headers of each table by
    walking ``TableVersion`` → ``TableVersionHeader`` → ``Header``
    (filtered to ``Header.IsKey``) → ``HeaderVersion`` → ``Property``
    → ``ItemCategory`` (for the property code) → ``DataType`` (for the
    type code). ``Header.IsKey`` is the DPM concept for "this axis is a
    key" — a table's open axis headers, not a ``KeyComposition``/
    ``VariableVersion`` pairing, which models something else entirely
    (dpmcore#381). ``TableVersionHeader.header_vid`` is a direct FK to
    one ``HeaderVersion`` row, so unlike ``ItemCategory`` below it needs
    no separate release-window filter. When ``release_id`` is given the
    query restricts to ``TableVersion`` rows whose release window
    contains it.

    ``table_vids``, when given, pins the lookup to those exact
    ``TableVersion`` rows (as resolved by the caller from a module
    version's own ``ModuleVersionComposition``) instead of resolving
    ``TableVersion`` rows by code + release-window overlap. This
    matters because two ``TableVersion`` rows can share the same code
    with both windows "still open" (``EndReleaseID IS NULL``) when an
    older row was superseded without ever being release-terminated in
    the source data — resolving by code alone would then merge both
    rows' open keys under the same table_code.
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
            HeaderVersion,
            ItemCategory.item_id == HeaderVersion.property_id,
        )
        .join(
            TableVersionHeader,
            TableVersionHeader.header_vid == HeaderVersion.header_vid,
        )
        .join(Header, Header.header_id == TableVersionHeader.header_id)
        .join(
            TableVersion,
            TableVersionHeader.table_vid == TableVersion.table_vid,
        )
        .filter(Header.is_key == True)  # noqa: E712
    )

    if table_vids is not None:
        query = query.filter(TableVersion.table_vid.in_(table_vids))

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
        if table_vids is None:
            query = query.filter(
                TableVersion.start_release_id.in_(start_ids),
                or_(
                    TableVersion.end_release_id.is_(None),
                    TableVersion.end_release_id.in_(end_ids),
                ),
            )
        query = query.filter(
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
    if table_vids is not None:
        rows = chunked_in(query, TableVersion.table_vid, table_vids)
    else:
        rows = chunked_in(query, TableVersion.code, table_codes)
    for row in rows:
        tcode = row.table_code
        pcode = row.property_code
        dcode = row.data_type_code or ""
        if tcode and pcode:
            result.setdefault(tcode, {})[pcode] = dcode
    return result
