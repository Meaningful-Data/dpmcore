"""Smoke tests for release_code threading through service entry points.

The ``resolve_release_id`` helper turns a textual ``release_code``
into the numeric ``release_id`` used by ``filter_by_release``.
Exercises one positive path and one mutex check per service so the
contract stays consistent.
"""

from datetime import date

import pytest

from dpmcore.orm.glossary import (
    Category,
    Item,
    ItemCategory,
)
from dpmcore.orm.infrastructure import Release
from dpmcore.orm.operations import OperationVersion
from dpmcore.orm.rendering import Table, TableVersion
from dpmcore.orm.variables import Variable, VariableVersion
from dpmcore.services.data_dictionary import DataDictionaryService
from dpmcore.services.explorer import ExplorerService


@pytest.fixture
def release_session(memory_session):
    """A session with two releases: '1.0' and '2.0' (opaque IDs)."""
    session = memory_session
    session.add_all(
        [
            Release(release_id=1, code="1.0", date=date(2023, 1, 1)),
            # Mimic the post-4.2.1 opaque-ID era.
            Release(release_id=1010000003, code="2.0", date=date(2024, 1, 1)),
        ]
    )
    session.commit()
    return session


# --------------------------------------------------------------------- #
# DataDictionaryService
# --------------------------------------------------------------------- #


def test_get_table_version_resolves_release_code(release_session):
    """release_code='1.0' resolves to release_id=1 and filters."""
    session = release_session
    session.add(Table(table_id=1))
    session.add(
        TableVersion(table_vid=10, table_id=1, code="T1", start_release_id=1)
    )
    session.commit()

    svc = DataDictionaryService(session)
    res = svc.get_table_version("T1", release_code="1.0")
    assert res is not None
    assert res["table_vid"] == 10


def test_get_table_version_mutex(release_session):
    svc = DataDictionaryService(release_session)
    with pytest.raises(ValueError, match="maximum of one"):
        svc.get_table_version("T1", release_id=1, release_code="1.0")


def test_get_all_item_signatures_resolves_release_code(release_session):
    session = release_session
    session.add(Category(category_id=1, code="C1"))
    session.add(Item(item_id=100, name="Item 100"))
    session.add(
        ItemCategory(
            item_id=100,
            start_release_id=1,
            end_release_id=None,
            category_id=1,
            signature="sig:item",
        )
    )
    session.commit()

    svc = DataDictionaryService(session)
    sigs = svc.get_all_item_signatures(release_code="1.0")
    assert "sig:item" in sigs


def test_get_item_categories_resolves_opaque_release_code(release_session):
    """Opaque post-4.2.1-style ID (1010000003) resolves correctly."""
    session = release_session
    session.add(Category(category_id=1, code="C1"))
    session.add(Item(item_id=200))
    session.add(
        ItemCategory(
            item_id=200,
            start_release_id=1010000003,
            end_release_id=None,
            category_id=1,
            code="ICODE",
            signature="sig:opaque",
        )
    )
    session.commit()

    svc = DataDictionaryService(session)
    rows = svc.get_item_categories(release_code="2.0")
    assert ("ICODE", "sig:opaque") in rows


# --------------------------------------------------------------------- #
# ExplorerService
# --------------------------------------------------------------------- #


def test_explorer_get_variable_by_code_resolves_release_code(release_session):
    session = release_session
    session.add(Variable(variable_id=1))
    session.add(
        VariableVersion(
            variable_vid=100,
            variable_id=1,
            code="V1",
            start_release_id=1,
            end_release_id=None,
        )
    )
    session.commit()

    svc = ExplorerService(session)
    res = svc.get_variable_by_code("V1", release_code="1.0")
    assert res is not None
    assert res["variable_vid"] == 100


def test_explorer_search_table_resolves_release_code(release_session):
    session = release_session
    session.add(Table(table_id=2))
    session.add(
        TableVersion(
            table_vid=20, table_id=2, code="C_01.00", start_release_id=1
        )
    )
    session.commit()

    svc = ExplorerService(session)
    rows = svc.search_table("C_01", release_code="1.0")
    codes = [r["code"] for r in rows]
    assert "C_01.00" in codes


def test_explorer_get_variable_usage_mutex(release_session):
    svc = ExplorerService(release_session)
    with pytest.raises(ValueError, match="maximum of one"):
        svc.get_variable_usage(
            variable_vid=1, release_id=1, release_code="1.0"
        )


def test_explorer_unknown_release_code_raises(release_session):
    svc = ExplorerService(release_session)
    with pytest.raises(ValueError, match="not found"):
        svc.get_variable_by_code("V1", release_code="99.0")


# --------------------------------------------------------------------- #
# DpmXlService facade — semantic mutex
# --------------------------------------------------------------------- #


def test_dpm_xl_facade_semantic_mutex(release_session):
    """Facade.validate_semantic forwards release_code to SemanticService."""
    from dpmcore.services.dpm_xl import DpmXlService

    svc = DpmXlService(release_session)
    res = svc.validate_semantic(
        "{tC_01.00, r0010, c0010}",
        release_id=1,
        release_code="1.0",
    )
    # SemanticService catches the ValueError and surfaces it on the
    # result rather than raising — verify it propagated.
    assert res["is_valid"] is False
    assert res["error_message"] is not None
    assert "maximum of one" in res["error_message"]


# --------------------------------------------------------------------- #
# ScopeCalculatorService
# --------------------------------------------------------------------- #


def test_scope_calculator_calculate_from_tables_unknown_release_code(
    release_session,
):
    """Unknown release_code surfaces as ScopeResult error."""
    from dpmcore.services.scope_calculator import ScopeCalculatorService

    svc = ScopeCalculatorService(release_session)
    res = svc.calculate_from_tables(table_vids=[1], release_code="99.0")
    # ScopeCalculator catches exceptions and surfaces them as has_error.
    assert res.has_error is True
    assert "not found" in (res.error_message or "")


def test_scope_calculator_detect_alternative_dependencies_resolves_code(
    release_session,
):
    """Public alt-deps entry point accepts release_code."""
    from dpmcore.services.scope_calculator import (
        ScopeCalculatorService,
        ScopeResult,
    )

    svc = ScopeCalculatorService(release_session)
    # Empty input — just verify the call doesn't raise and returns [].
    out = svc.detect_alternative_dependencies(
        scope_results=[ScopeResult()],
        primary_module_vid=1,
        release_code="1.0",
    )
    assert out == []


# --------------------------------------------------------------------- #
# OperandReference test data — get_variable_usage smoke
# --------------------------------------------------------------------- #


def test_get_variable_usage_resolves_release_code(release_session):
    """End-to-end: release_code passes through join + filter pipeline."""
    session = release_session
    session.add(Variable(variable_id=1))
    session.add(
        VariableVersion(
            variable_vid=100,
            variable_id=1,
            code="V1",
            start_release_id=1,
        )
    )
    session.add(
        OperationVersion(
            operation_vid=10,
            operation_id=1,
            start_release_id=1,
            end_release_id=None,
        )
    )
    session.commit()

    svc = ExplorerService(session)
    # No OperandReference row → empty result, but the query must
    # compile and execute against the resolved release_id.
    out = svc.get_variable_usage(variable_vid=100, release_code="1.0")
    assert out == []
