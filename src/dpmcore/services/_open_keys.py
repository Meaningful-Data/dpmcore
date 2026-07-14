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
        query = query.filter(
            or_(
                TableVersion.end_release_id.is_(None),
                TableVersion.end_release_id > release_id,
            ),
            TableVersion.start_release_id <= release_id,
        )

    query = query.distinct().order_by(TableVersion.code, ItemCategory.code)
    rows = chunked_in(query, TableVersion.code, table_codes)
    for row in rows:
        tcode = row.table_code
        pcode = row.property_code
        dcode = row.data_type_code or ""
        if tcode and pcode:
            result.setdefault(tcode, {})[pcode] = dcode
    return result
