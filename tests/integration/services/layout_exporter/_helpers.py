"""Helpers to populate the in-memory DB with realistic DPM table data.

Each builder seeds enough rows to drive the layout_exporter through
its various branches. Builders are explicit (no fixture magic) so
individual tests can pick exactly the shape they need.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from dpmcore.orm.glossary import (
    Category,
    ContextComposition,
    Item,
    ItemCategory,
    Property,
    PropertyCategory,
    SubCategory,
    SubCategoryVersion,
)
from dpmcore.orm.infrastructure import DataType, Release
from dpmcore.orm.packaging import (
    Framework,
    Module,
    ModuleVersion,
    ModuleVersionComposition,
)
from dpmcore.orm.rendering import (
    Cell,
    Header,
    HeaderVersion,
    Table,
    TableVersion,
    TableVersionCell,
    TableVersionHeader,
)
from dpmcore.orm.variables import Variable, VariableVersion

# ------------------------------------------------------------------ #
# Common reference data
# ------------------------------------------------------------------ #


def seed_releases(session: Session) -> None:
    session.add(Release(release_id=1, code="REL1"))
    session.add(Release(release_id=2, code="REL2"))


def seed_data_types(session: Session) -> None:
    session.add(DataType(data_type_id=1, code="m", name="Monetary"))
    session.add(DataType(data_type_id=2, code="e", name="Enumeration"))
    session.add(DataType(data_type_id=3, code="p", name="Percent"))
    session.add(DataType(data_type_id=4, code="s", name="String"))


def seed_property_category(session: Session) -> None:
    """Add the '_PR' category used by _load_dimension_codes."""
    session.add(Category(category_id=1, code="_PR", name="Property Category"))


def seed_domain_category(
    session: Session,
    category_id: int,
    code: str,
) -> None:
    session.add(Category(category_id=category_id, code=code, name=code))


def make_property(
    session: Session,
    *,
    property_id: int,
    name: str,
    data_type_id: int = 1,
    dim_code: str = "",
    domain_category_id: int | None = None,
) -> None:
    """Add a property/item with an ItemCategory in '_PR' for the dim code."""
    session.add(
        Item(item_id=property_id, name=name, is_property=True),
    )
    session.add(
        Property(property_id=property_id, data_type_id=data_type_id),
    )
    if dim_code:
        session.add(
            ItemCategory(
                item_id=property_id,
                start_release_id=1,
                category_id=1,  # the _PR category
                code=dim_code,
            ),
        )
    if domain_category_id is not None:
        session.add(
            PropertyCategory(
                property_id=property_id,
                start_release_id=1,
                category_id=domain_category_id,
            ),
        )


def make_member(
    session: Session,
    *,
    item_id: int,
    name: str,
    domain_category_id: int,
    code: str,
) -> None:
    """Add an Item-as-member belonging to a domain category."""
    session.add(Item(item_id=item_id, name=name))
    session.add(
        ItemCategory(
            item_id=item_id,
            start_release_id=1,
            category_id=domain_category_id,
            code=code,
        ),
    )


def make_module(
    session: Session,
    *,
    module_id: int = 1,
    module_vid: int = 10,
    code: str = "MOD1",
    framework_id: int = 1,
    start_release_id: int = 1,
    end_release_id: int | None = None,
) -> None:
    session.add(Framework(framework_id=framework_id, code="FW1"))
    session.add(Module(module_id=module_id, framework_id=framework_id))
    session.add(
        ModuleVersion(
            module_vid=module_vid,
            module_id=module_id,
            code=code,
            start_release_id=start_release_id,
            end_release_id=end_release_id,
        ),
    )


def add_table(
    session: Session,
    *,
    table_id: int,
    table_vid: int,
    code: str,
    name: str,
    module_vid: int | None = None,
    start_release_id: int | None = 1,
    end_release_id: int | None = None,
    order: int = 1,
) -> None:
    session.add(Table(table_id=table_id))
    session.add(
        TableVersion(
            table_vid=table_vid,
            table_id=table_id,
            code=code,
            name=name,
            start_release_id=start_release_id,
            end_release_id=end_release_id,
        ),
    )
    if module_vid is not None:
        session.add(
            ModuleVersionComposition(
                module_vid=module_vid,
                table_vid=table_vid,
                table_id=table_id,
                order=order,
            ),
        )


def add_header(
    session: Session,
    *,
    table_vid: int,
    table_id: int,
    header_id: int,
    header_vid: int,
    direction: str,
    code: str,
    label: str,
    order: int = 1,
    is_abstract: bool = False,
    is_key: bool = False,
    parent_header_id: int | None = None,
    parent_first: bool = True,
    context_id: int | None = None,
    property_id: int | None = None,
    subcategory_vid: int | None = None,
    key_variable_vid: int | None = None,
) -> None:
    session.add(
        Header(
            header_id=header_id,
            table_id=table_id,
            direction=direction,
            is_key=is_key,
        ),
    )
    session.add(
        HeaderVersion(
            header_vid=header_vid,
            header_id=header_id,
            code=code,
            label=label,
            context_id=context_id,
            property_id=property_id,
            subcategory_vid=subcategory_vid,
            key_variable_vid=key_variable_vid,
        ),
    )
    session.add(
        TableVersionHeader(
            table_vid=table_vid,
            header_id=header_id,
            header_vid=header_vid,
            order=order,
            is_abstract=is_abstract,
            parent_header_id=parent_header_id,
            parent_first=parent_first,
        ),
    )


def add_context_composition(
    session: Session,
    *,
    context_id: int,
    property_id: int,
    item_id: int | None = None,
) -> None:
    session.add(
        ContextComposition(
            context_id=context_id,
            property_id=property_id,
            item_id=item_id,
        ),
    )


def add_variable_version(
    session: Session,
    *,
    variable_id: int,
    variable_vid: int,
    code: str = "V",
    property_id: int | None = None,
    context_id: int | None = None,
) -> None:
    session.add(Variable(variable_id=variable_id))
    session.add(
        VariableVersion(
            variable_vid=variable_vid,
            variable_id=variable_id,
            code=code,
            property_id=property_id,
            context_id=context_id,
        ),
    )


def add_cell(
    session: Session,
    *,
    cell_id: int,
    table_id: int,
    table_vid: int,
    column_id: int,
    row_id: int | None = None,
    sheet_id: int | None = None,
    variable_vid: int | None = None,
    is_excluded: bool = False,
    is_void: bool = False,
    sign: str = "",
) -> None:
    session.add(
        Cell(
            cell_id=cell_id,
            table_id=table_id,
            column_id=column_id,
            row_id=row_id,
            sheet_id=sheet_id,
        ),
    )
    session.add(
        TableVersionCell(
            table_vid=table_vid,
            cell_id=cell_id,
            variable_vid=variable_vid,
            is_excluded=is_excluded,
            is_void=is_void,
            sign=sign,
        ),
    )


def add_subcategory(
    session: Session,
    *,
    subcategory_id: int,
    subcategory_vid: int,
    category_id: int,
    code: str,
    description: str | None = None,
    name: str | None = None,
) -> None:
    session.add(
        SubCategory(
            subcategory_id=subcategory_id,
            category_id=category_id,
            code=code,
            description=description,
            name=name,
        ),
    )
    session.add(
        SubCategoryVersion(
            subcategory_vid=subcategory_vid,
            subcategory_id=subcategory_id,
            start_release_id=1,
        ),
    )


# ------------------------------------------------------------------ #
# Composite scenario builders
# ------------------------------------------------------------------ #


def build_basic_module_with_table(session: Session) -> None:
    """A minimal module with one table containing one row + one column.

    Provides a clean baseline for service-level export tests.
    """
    seed_releases(session)
    seed_data_types(session)
    seed_property_category(session)
    seed_domain_category(session, 10, "DOM")

    make_module(session, module_id=1, module_vid=10, code="MOD1")
    add_table(
        session,
        table_id=100,
        table_vid=1000,
        code="T1",
        name="Table One",
        module_vid=10,
        order=1,
    )

    # A monetary metric property used as ATY column header
    make_property(
        session,
        property_id=200,
        name="Carrying amount",
        data_type_id=1,
        dim_code="qCCB",
        domain_category_id=10,
    )

    # Single column referencing the property directly
    add_header(
        session,
        table_vid=1000,
        table_id=100,
        header_id=1,
        header_vid=11,
        direction="x",
        code="010",
        label="Col 1",
        order=1,
        property_id=200,
    )

    # Single row
    add_header(
        session,
        table_vid=1000,
        table_id=100,
        header_id=2,
        header_vid=12,
        direction="y",
        code="010",
        label="Row 1",
        order=1,
    )

    # One cell with a variable
    add_variable_version(
        session,
        variable_id=300,
        variable_vid=3000,
        code="V1",
        property_id=200,
    )
    add_cell(
        session,
        cell_id=900,
        table_id=100,
        table_vid=1000,
        column_id=1,
        row_id=2,
        variable_vid=3000,
        sign="positive",
    )

    session.commit()
