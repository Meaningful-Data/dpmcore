"""Integration tests for the URI-resolution chain in ScopeCalculatorService.

These pin the load-bearing behaviour that ``script()`` relies on when it
populates ``dependency_modules``: the CSV-hit branch must strip the
``.json`` suffix; the dynamic-template branch must assemble the EBA-style
URL from real ORM rows.

The full ``script()`` end-to-end requires a parseable DPM-XL expression
plus a heavy fixture; these focused tests exercise the same primitive
methods (``_get_module_uri`` / ``_get_module_tables``) against real
SQLAlchemy queries via ``memory_session``.
"""

from __future__ import annotations

from datetime import date

import pytest

from dpmcore.orm.glossary import DataType, Property
from dpmcore.orm.infrastructure import Release
from dpmcore.orm.packaging import (
    Framework,
    Module,
    ModuleVersion,
    ModuleVersionComposition,
)
from dpmcore.orm.rendering import TableVersion, TableVersionCell
from dpmcore.orm.variables import Variable, VariableVersion
from dpmcore.services.scope_calculator import ScopeCalculatorService


@pytest.fixture
def populated_session(memory_session):
    """Build a minimal DPM graph: 1 release, 1 framework, 1 module, 1 mv."""
    session = memory_session
    session.add_all(
        [
            Release(release_id=5, code="3.4", date=date(2024, 2, 6)),
            Framework(framework_id=1, code="COREP", name="Common Reporting"),
            Module(module_id=10, framework_id=1),
        ]
    )
    session.commit()
    return session


class TestGetModuleUriIntegration:
    """Exercise ``_get_module_uri`` against real SQLAlchemy queries."""

    def test_csv_hit_strips_json_suffix(self, populated_session):
        """An mv whose ``code + version_number`` matches the CSV uses it."""
        # COREP_Con v2.0.1 is row 2 of the bundled CSV.
        populated_session.add(
            ModuleVersion(
                module_vid=100,
                module_id=10,
                code="COREP_Con",
                version_number="2.0.1",
                start_release_id=5,
            )
        )
        populated_session.commit()

        svc = ScopeCalculatorService(populated_session)
        mv = (
            populated_session.query(ModuleVersion)
            .filter(ModuleVersion.module_vid == 100)
            .first()
        )
        uri = svc._get_module_uri(module_vid=100, mv=mv)

        # The CSV row ends with .json and the resolver strips it.
        assert uri == (
            "http://www.eba.europa.eu/eu/fr/xbrl/crr/fws/corep/"
            "its-2013-02/2013-12-01/mod/corep_con"
        )

    def test_dynamic_template_built_from_db(self, populated_session):
        """An mv with no CSV entry falls through to the dynamic builder."""
        populated_session.add(
            ModuleVersion(
                module_vid=200,
                module_id=10,
                code="MADE_UP_MOD",
                version_number="9.9.9",
                start_release_id=5,
            )
        )
        populated_session.commit()

        svc = ScopeCalculatorService(populated_session)
        uri = svc._get_module_uri(module_vid=200, release_id=5)

        # Dynamic template uses framework.code + Release.code + module.code.
        assert uri == (
            "http://www.eba.europa.eu/eu/fr/xbrl/crr/fws/corep/3.4/mod/"
            "made_up_mod"
        )

    def test_missing_module_returns_none(self, populated_session):
        svc = ScopeCalculatorService(populated_session)
        assert svc._get_module_uri(module_vid=99999) is None


class TestGetModuleTablesIntegration:
    """Exercise ``_get_module_tables`` against real SQLAlchemy queries."""

    def test_returns_tables_with_variables(self, memory_session):
        session = memory_session
        # Minimal graph: module 10 → table 100 → 1 cell → 1 variable.
        session.add_all(
            [
                Module(module_id=10),
                ModuleVersion(
                    module_vid=200,
                    module_id=10,
                    code="MOD",
                    version_number="1.0.0",
                ),
                TableVersion(table_vid=100, code="T_01"),
                ModuleVersionComposition(
                    module_vid=200, table_id=1, table_vid=100
                ),
                Variable(variable_id=42),
                DataType(data_type_id=1, code="X"),
                Property(property_id=1, data_type_id=1),
                VariableVersion(
                    variable_vid=42, variable_id=42, property_id=1
                ),
                TableVersionCell(cell_id=1, table_vid=100, variable_vid=42),
            ]
        )
        session.commit()

        svc = ScopeCalculatorService(session)
        tables = svc._get_module_tables(module_vid=200)

        assert "T_01" in tables
        assert tables["T_01"]["variables"] == {"42": "X"}
        assert tables["T_01"]["open_keys"] == {}

    def test_unknown_module_returns_empty_dict(self, memory_session):
        svc = ScopeCalculatorService(memory_session)
        assert svc._get_module_tables(module_vid=999) == {}
