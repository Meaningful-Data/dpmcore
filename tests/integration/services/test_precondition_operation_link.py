import datetime

import pytest

from dpmcore.errors import SemanticError
from dpmcore.orm.infrastructure import Release
from dpmcore.orm.operations import (
    OperandReference,
    OperationNode,
    OperationVersion,
)
from dpmcore.orm.packaging import (
    ModuleParameters,
    ModuleVersion,
    ModuleVersionComposition,
)
from dpmcore.orm.rendering import Table, TableVersion
from dpmcore.orm.variables import Variable, VariableVersion
from dpmcore.services.semantic import SemanticService

pytestmark = pytest.mark.integration


def _svc(session):
    return SemanticService(session=session)


# --------------------------------------------------------------------- #
# _check_precondition_filing_indicators (error 7-3)
# --------------------------------------------------------------------- #


def _seed_filing_indicator(session, *, indicator_in_open_module: bool):
    session.add_all(
        [
            Release(release_id=1, code="3.4", date=datetime.date(2022, 12, 1)),
            Variable(variable_id=1, type="filingindicator"),
            VariableVersion(
                variable_vid=1,
                variable_id=1,
                code="C_02.00",
                start_release_id=1,
                end_release_id=None,
            ),
            OperationVersion(operation_vid=500, expression="{v_C_02.00}"),
            OperationNode(node_id=1, operation_vid=500),
            OperandReference(operand_reference_id=1, node_id=1, variable_id=1),
        ]
    )
    if indicator_in_open_module:
        session.add_all(
            [
                ModuleVersion(
                    module_vid=100,
                    module_id=1,
                    code="COREP_OF",
                    version_number="1.0",
                    start_release_id=1,
                    end_release_id=None,
                    from_reference_date=datetime.date(2023, 6, 30),
                    to_reference_date=None,
                ),
                ModuleParameters(module_vid=100, variable_vid=1),
            ]
        )
    session.flush()


def test_filing_indicator_in_open_module_passes(memory_session):
    _seed_filing_indicator(memory_session, indicator_in_open_module=True)
    svc = _svc(memory_session)

    svc._check_precondition_filing_indicators(500, release_id=1)  # no raise


def test_filing_indicator_not_in_any_module_raises_7_3(memory_session):
    _seed_filing_indicator(memory_session, indicator_in_open_module=False)
    svc = _svc(memory_session)

    with pytest.raises(SemanticError) as exc_info:
        svc._check_precondition_filing_indicators(500, release_id=1)
    assert exc_info.value.code == "7-3"


def test_non_filing_indicator_variable_is_ignored(memory_session):
    # "fact"-typed variable: not scope-relevant, ignored despite no module.
    memory_session.add_all(
        [
            Release(release_id=1, code="3.4", date=datetime.date(2022, 12, 1)),
            Variable(variable_id=2, type="fact"),
            VariableVersion(
                variable_vid=2,
                variable_id=2,
                code="V_FACT",
                start_release_id=1,
                end_release_id=None,
            ),
            OperationVersion(operation_vid=501, expression="{v_V_FACT}"),
            OperationNode(node_id=2, operation_vid=501),
            OperandReference(operand_reference_id=2, node_id=2, variable_id=2),
        ]
    )
    memory_session.flush()
    svc = _svc(memory_session)

    svc._check_precondition_filing_indicators(501, release_id=1)  # no raise


def test_operation_with_no_operand_references_is_a_noop(memory_session):
    memory_session.add_all(
        [
            Release(release_id=1, code="3.4", date=datetime.date(2022, 12, 1)),
            OperationVersion(operation_vid=502, expression="1 + 1"),
        ]
    )
    memory_session.flush()
    svc = _svc(memory_session)

    svc._check_precondition_filing_indicators(502, release_id=1)  # no raise


def test_unknown_precondition_operation_vid_is_a_noop(memory_session):
    memory_session.add(
        Release(release_id=1, code="3.4", date=datetime.date(2022, 12, 1))
    )
    memory_session.flush()
    svc = _svc(memory_session)

    svc._check_precondition_link(999999, release_id=1)  # no raise


# --------------------------------------------------------------------- #
# _check_precondition_tables (errors 7-4 / 7-5)
# --------------------------------------------------------------------- #


def _seed_tables(session, *, fi_shares_operand_module: bool):
    """Table T1 (module M1), abstract table FI_X.

    ``fi_shares_operand_module=True`` puts FI_X in M1 too (both checks
    pass); otherwise FI_X is only in module M2 (7-5 must fail).
    """
    session.add_all(
        [
            Release(release_id=1, code="3.4", date=datetime.date(2022, 12, 1)),
            Table(table_id=1),
            Table(table_id=2),
            TableVersion(
                table_vid=10,
                code="T1",
                table_id=1,
                abstract_table_id=2,
                start_release_id=1,
                end_release_id=None,
            ),
            TableVersion(
                table_vid=20,
                code="FI_X",
                table_id=2,
                abstract_table_id=None,
                start_release_id=1,
                end_release_id=None,
            ),
            ModuleVersion(
                module_vid=200,
                module_id=1,
                code="M1",
                version_number="1.0",
                start_release_id=1,
                end_release_id=None,
            ),
            ModuleVersionComposition(module_vid=200, table_id=1, table_vid=10),
        ]
    )
    if fi_shares_operand_module:
        session.add(
            ModuleVersionComposition(module_vid=200, table_id=2, table_vid=20)
        )
    else:
        session.add_all(
            [
                ModuleVersion(
                    module_vid=300,
                    module_id=2,
                    code="M2",
                    version_number="1.0",
                    start_release_id=1,
                    end_release_id=None,
                ),
                ModuleVersionComposition(
                    module_vid=300, table_id=2, table_vid=20
                ),
            ]
        )
    session.flush()


def test_matching_table_and_module_passes(memory_session):
    _seed_tables(memory_session, fi_shares_operand_module=True)
    svc = _svc(memory_session)
    svc.oc_tables = {"T1": {}}

    svc._check_precondition_tables("{v_FI_X}", release_id=1)  # no raise


def test_precondition_code_not_among_operand_abstract_tables_raises_7_4(
    memory_session,
):
    _seed_tables(memory_session, fi_shares_operand_module=True)
    svc = _svc(memory_session)
    svc.oc_tables = {"T1": {}}

    with pytest.raises(SemanticError) as exc_info:
        svc._check_precondition_tables("{v_UNRELATED}", release_id=1)
    assert exc_info.value.code == "7-4"


def test_matching_table_but_different_module_raises_7_5(memory_session):
    _seed_tables(memory_session, fi_shares_operand_module=False)
    svc = _svc(memory_session)
    svc.oc_tables = {"T1": {}}

    with pytest.raises(SemanticError) as exc_info:
        svc._check_precondition_tables("{v_FI_X}", release_id=1)
    assert exc_info.value.code == "7-5"


def test_expression_with_no_precondition_codes_is_a_noop(memory_session):
    _seed_tables(memory_session, fi_shares_operand_module=True)
    svc = _svc(memory_session)
    svc.oc_tables = {"T1": {}}

    svc._check_precondition_tables("1 + 1", release_id=1)  # no raise


def test_malformed_precondition_expression_is_a_noop(memory_session):
    svc = _svc(memory_session)
    svc.oc_tables = {"T1": {}}

    svc._check_precondition_tables("{{{not valid dpm-xl", release_id=1)
