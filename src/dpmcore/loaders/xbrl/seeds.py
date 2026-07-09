"""Static reference data required by freshly created DPM databases.

``Base.metadata.create_all`` produces empty tables; a database built
from an XBRL taxonomy therefore needs the DPM metamodel reference
rows (``DPMClass``, ``DPMAttribute``, ``DataType``, ``Operator``,
``Language``) seeded before the mapped content can reference them.
Values are transcribed from the canonical ``data/DPM/*.csv`` exports
of the EBA 4.2.1 database so that identifiers stay aligned with real
DPM databases.

Every ``ensure_*`` function is get-or-create by natural key, so
seeding an already-populated database (``into_existing`` mode) is a
no-op that simply returns the existing identifiers.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from dpmcore.orm.infrastructure import (
    DataType,
    DpmAttribute,
    DpmClass,
    Language,
)
from dpmcore.orm.operations import Operator

#: ``(name, type, owner_class_id, has_references, class_id)`` rows
#: from ``data/DPM/DPMClass.csv``.
DPM_CLASS_ROWS: Tuple[Tuple[str, Optional[int], bool, int], ...] = (
    ("Organisation", None, True, 1),
    ("Category", None, True, 2),
    ("SubCategory", None, True, 3),
    ("Property", None, True, 4),
    ("Item", None, True, 5),
    ("Framework", None, True, 6),
    ("Module", 6, True, 7),
    ("ModuleVersion", 7, True, 8),
    ("TableGroup", None, True, 9),
    ("Table", None, True, 10),
    ("TableVersion", 10, True, 11),
    ("TableAssociation", None, True, 12),
    ("Header", 10, True, 13),
    ("HeaderVersion", 13, True, 14),
    ("Cell", 10, True, 15),
    ("Variable", None, True, 16),
    ("VariableVersion", 16, True, 17),
    ("CompoundKey", None, False, 18),
    ("Context", None, True, 19),
    ("Operation", None, True, 20),
    ("OperationVersion", 20, True, 21),
    ("LegalDocument", None, False, 22),
    ("LegalDocumentVersion", 22, False, 23),
    ("Subdivision", 23, False, 24),
    ("Release", None, True, 28),
    ("OperAttrValue", None, True, 29),
    ("SubCategoryItem", 3, True, 30),
)

#: ``(class_name, attribute_name, attribute_id)`` rows from
#: ``data/DPM/DPMAttribute.csv`` for the attributes the importer
#: writes translations for.
DPM_ATTRIBUTE_ROWS: Tuple[Tuple[str, str, int], ...] = (
    ("Organisation", "Name", 2),
    ("Category", "Name", 8),
    ("SubCategory", "Name", 19),
    ("Item", "Name", 30),
    ("Framework", "Name", 37),
    ("ModuleVersion", "Name", 49),
    ("TableVersion", "Name", 76),
    ("HeaderVersion", "Label", 105),
    ("VariableVersion", "Name", 130),
    ("SubCategoryItem", "Label", 176),
)

#: ``(code, name, parent_data_type_id, data_type_id)`` rows from
#: ``data/DPM/DataType.csv``.
DATA_TYPE_ROWS: Tuple[Tuple[str, str, Optional[int], int], ...] = (
    ("i", "integer", None, 1),
    ("r", "decimal", None, 2),
    ("s", "string (non empty)", None, 3),
    ("b", "boolean", None, 4),
    ("t", "true", 4, 5),
    ("dt", "date time", None, 6),
    ("d", "date", 6, 7),
    ("e", "enumeration", 3, 8),
    ("m", "monetary", None, 9),
    ("p", "percentage", None, 10),
    ("u", "URI", None, 11),
    ("o", "ordinals", None, 12),
    ("es", "string (including empty string)", None, 13),
)

#: ``(name, symbol, type, operator_id)`` rows from
#: ``data/DPM/Operator.csv``.
OPERATOR_ROWS: Tuple[Tuple[str, str, str, int], ...] = (
    ("Unary plus", "+", "Numeric", 1),
    ("Addition", "+", "Numeric", 2),
    ("Division", "/", "Numeric", 3),
    ("Unary minus", "-", "Numeric", 4),
    ("Subtraction", "-", "Numeric", 5),
    ("Absolute value", "abs", "Numeric", 6),
    ("Numeric minimum", "min", "Numeric", 7),
    ("Multiplication", "*", "Numeric", 8),
    ("Numeric maximum", "max", "Numeric", 9),
    ("Square root", "sqrt", "Numeric", 10),
    ("Aggregate maximum", "max_aggr", "Aggregate", 11),
    ("Aggregate minimum", "min_aggr", "Aggregate", 12),
    ("Equal to", "=", "Comparison", 13),
    ("Less than equal to", "<=", "Comparison", 14),
    ("Greater than equal to", ">=", "Comparison", 15),
    ("Element of", "in", "Comparison", 16),
    ("Is null", "isnull", "Comparison", 17),
    ("Greater than", ">", "Comparison", 18),
    ("Less than", "<", "Comparison", 19),
    ("Not equal to", "!=", "Comparison", 20),
    ("Match characters", "match", "Comparison", 21),
    ("And", "and", "Logical", 22),
    ("Or", "or", "Logical", 23),
    ("Not", "not", "Logical", 24),
    ("Exclusive or", "xor", "Logical", 25),
    ("Sum", "sum", "Aggregate", 26),
    ("Count", "count", "Aggregate", 27),
    ("Where", "where", "Clause", 28),
    ("Get", "get", "Clause", 29),
    ("If then else", "if-then-else", "Conditional", 30),
    ("Filter", "filter", "Conditional", 31),
    ("Time shift", "time_shift", "Time", 32),
    ("Rename", "rename", "Clause", 33),
    ("RenameNode", "node", "Clause", 34),
    ("Grouping clause", "group by", "Clause", 35),
    ("Persistent assignment", "<-", "Assignment", 36),
    ("Parenthesis Expression", "()", "Logical", 37),
    ("Sub", "sub", "Clause", 38),
)

#: ``(iso_code, display_name, language_code)`` seed. The DPM
#: ``Language`` table has no ISO-code column, so the importer keys
#: languages by display name and uses these codes when creating.
LANGUAGE_ROWS: Tuple[Tuple[str, str, int], ...] = (
    ("en", "English", 1),
    ("fr", "French", 2),
    ("nl", "Dutch", 3),
)


def ensure_dpm_classes(session: Session) -> Dict[str, int]:
    """Get-or-create the DPM metamodel classes.

    Args:
        session: Target database session.

    Returns:
        Mapping of class name to ``ClassID``.
    """
    existing = {
        row.name: row.class_id
        for row in session.query(DpmClass).all()
        if row.name is not None
    }
    for name, owner_class_id, has_references, class_id in DPM_CLASS_ROWS:
        if name in existing:
            continue
        session.add(
            DpmClass(
                class_id=class_id,
                name=name,
                owner_class_id=owner_class_id,
                has_references=has_references,
            )
        )
        existing[name] = class_id
    session.flush()
    return existing


def ensure_dpm_attributes(session: Session) -> Dict[Tuple[str, str], int]:
    """Get-or-create the DPM attributes used for translations.

    Args:
        session: Target database session.

    Returns:
        Mapping of ``(class_name, attribute_name)`` to
        ``AttributeID``.
    """
    class_ids = ensure_dpm_classes(session)
    class_names = {cid: name for name, cid in class_ids.items()}

    existing: Dict[Tuple[str, str], int] = {}
    for row in session.query(DpmAttribute).all():
        class_name = class_names.get(row.class_id or -1)
        if class_name is not None and row.name is not None:
            existing[(class_name, row.name)] = row.attribute_id

    for class_name, attr_name, attribute_id in DPM_ATTRIBUTE_ROWS:
        key = (class_name, attr_name)
        if key in existing:
            continue
        session.add(
            DpmAttribute(
                attribute_id=attribute_id,
                class_id=class_ids[class_name],
                name=attr_name,
                has_translations=False,
            )
        )
        existing[key] = attribute_id
    session.flush()
    return existing


def ensure_data_types(session: Session) -> Dict[str, int]:
    """Get-or-create the DPM data types.

    Args:
        session: Target database session.

    Returns:
        Mapping of data-type code (``m``, ``e``, ...) to
        ``DataTypeID``.
    """
    existing = {
        row.code: row.data_type_id
        for row in session.query(DataType).all()
        if row.code is not None
    }
    for code, name, parent_id, data_type_id in DATA_TYPE_ROWS:
        if code in existing:
            continue
        session.add(
            DataType(
                data_type_id=data_type_id,
                code=code,
                name=name,
                parent_data_type_id=parent_id,
                is_active=True,
            )
        )
        existing[code] = data_type_id
    session.flush()
    return existing


def ensure_operators(session: Session) -> int:
    """Get-or-create the DPM-XL operator list.

    Args:
        session: Target database session.

    Returns:
        Number of operator rows created.
    """
    existing = {
        row.name
        for row in session.query(Operator).all()
        if row.name is not None
    }
    created = 0
    for name, symbol, op_type, operator_id in OPERATOR_ROWS:
        if name in existing:
            continue
        session.add(
            Operator(
                operator_id=operator_id,
                name=name,
                symbol=symbol,
                type=op_type,
            )
        )
        created += 1
    session.flush()
    return created


def ensure_languages(session: Session) -> Dict[str, int]:
    """Get-or-create the languages used by NBB taxonomies.

    Args:
        session: Target database session.

    Returns:
        Mapping of ISO code (``en``, ``fr``, ``nl``) to the DPM
        ``LanguageCode`` integer.
    """
    by_name = {
        row.name: row.language_code
        for row in session.query(Language).all()
        if row.name is not None
    }
    max_code = session.query(func.max(Language.language_code)).scalar() or 0

    codes: Dict[str, int] = {}
    for iso_code, display_name, language_code in LANGUAGE_ROWS:
        if display_name in by_name:
            codes[iso_code] = by_name[display_name]
            continue
        new_code = max(language_code, max_code + 1)
        session.add(Language(language_code=new_code, name=display_name))
        max_code = new_code
        codes[iso_code] = new_code
    session.flush()
    return codes
