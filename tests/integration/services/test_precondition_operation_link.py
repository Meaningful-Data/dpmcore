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
            OperationVersion(
                operation_vid=500,
                expression="{v_C_02.00}",
                start_release_id=1,
                end_release_id=None,
            ),
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

    svc._check_precondition_link(500, release_id=1)  # no raise


def test_filing_indicator_not_in_any_module_raises_7_3(memory_session):
    _seed_filing_indicator(memory_session, indicator_in_open_module=False)
    svc = _svc(memory_session)

    with pytest.raises(SemanticError) as exc_info:
        svc._check_precondition_link(500, release_id=1)
    assert exc_info.value.code == "7-3"


def test_non_filing_indicator_variable_is_ignored(memory_session):
    # "fact" variable, not scope-relevant: ignored despite no module.
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
            OperationVersion(
                operation_vid=501,
                expression="{v_V_FACT}",
                start_release_id=1,
                end_release_id=None,
            ),
            OperationNode(node_id=2, operation_vid=501),
            OperandReference(operand_reference_id=2, node_id=2, variable_id=2),
        ]
    )
    memory_session.flush()
    svc = _svc(memory_session)

    svc._check_precondition_link(501, release_id=1)  # no raise


def test_operation_with_no_operand_references_is_a_noop(memory_session):
    memory_session.add_all(
        [
            Release(release_id=1, code="3.4", date=datetime.date(2022, 12, 1)),
            OperationVersion(
                operation_vid=502,
                expression="1 + 1",
                start_release_id=1,
                end_release_id=None,
            ),
        ]
    )
    memory_session.flush()
    svc = _svc(memory_session)

    svc._check_precondition_link(502, release_id=1)  # no raise


def _seed_two_filing_indicators(session, *, first_live, second_live):
    session.add_all(
        [
            Release(release_id=1, code="3.4", date=datetime.date(2022, 12, 1)),
            Variable(variable_id=10, type="filingindicator"),
            VariableVersion(
                variable_vid=10,
                variable_id=10,
                code="OR_A",
                start_release_id=1,
                end_release_id=None,
            ),
            Variable(variable_id=11, type="filingindicator"),
            VariableVersion(
                variable_vid=11,
                variable_id=11,
                code="OR_B",
                start_release_id=1,
                end_release_id=None,
            ),
            OperationVersion(
                operation_vid=700,
                expression="{v_OR_A} or {v_OR_B}",
                start_release_id=1,
                end_release_id=None,
            ),
            OperationNode(node_id=10, operation_vid=700),
            OperandReference(
                operand_reference_id=10, node_id=10, variable_id=10
            ),
            OperationNode(node_id=11, operation_vid=700),
            OperandReference(
                operand_reference_id=11, node_id=11, variable_id=11
            ),
        ]
    )
    if first_live:
        session.add_all(
            [
                ModuleVersion(
                    module_vid=400,
                    module_id=10,
                    code="M_OR_A",
                    version_number="1.0",
                    start_release_id=1,
                    end_release_id=None,
                    from_reference_date=datetime.date(2023, 6, 30),
                    to_reference_date=None,
                ),
                ModuleParameters(module_vid=400, variable_vid=10),
            ]
        )
    if second_live:
        session.add_all(
            [
                ModuleVersion(
                    module_vid=401,
                    module_id=11,
                    code="M_OR_B",
                    version_number="1.0",
                    start_release_id=1,
                    end_release_id=None,
                    from_reference_date=datetime.date(2023, 6, 30),
                    to_reference_date=None,
                ),
                ModuleParameters(module_vid=401, variable_vid=11),
            ]
        )
    session.flush()


def test_or_gate_passes_when_only_one_side_is_live(memory_session):
    _seed_two_filing_indicators(
        memory_session, first_live=False, second_live=True
    )
    svc = _svc(memory_session)

    svc._check_precondition_link(700, release_id=1)  # no raise


def test_or_gate_raises_7_3_when_both_sides_are_stale(memory_session):
    _seed_two_filing_indicators(
        memory_session, first_live=False, second_live=False
    )
    svc = _svc(memory_session)

    with pytest.raises(SemanticError) as exc_info:
        svc._check_precondition_link(700, release_id=1)
    assert exc_info.value.code == "7-3"
    assert "10" in str(exc_info.value)
    assert "11" in str(exc_info.value)


def test_and_gate_7_3_message_lists_only_the_stale_side(memory_session):
    # AND needs both sides. The message must name only the stale one.
    memory_session.add_all(
        [
            Release(release_id=1, code="3.4", date=datetime.date(2022, 12, 1)),
            Variable(variable_id=20, type="filingindicator"),
            VariableVersion(
                variable_vid=20,
                variable_id=20,
                code="AND_A",
                start_release_id=1,
                end_release_id=None,
            ),
            Variable(variable_id=21, type="filingindicator"),
            VariableVersion(
                variable_vid=21,
                variable_id=21,
                code="AND_B",
                start_release_id=1,
                end_release_id=None,
            ),
            OperationVersion(
                operation_vid=701,
                expression="{v_AND_A} and {v_AND_B}",
                start_release_id=1,
                end_release_id=None,
            ),
            OperationNode(node_id=20, operation_vid=701),
            OperandReference(
                operand_reference_id=20, node_id=20, variable_id=20
            ),
            OperationNode(node_id=21, operation_vid=701),
            OperandReference(
                operand_reference_id=21, node_id=21, variable_id=21
            ),
            # Only AND_B is live in an open module. AND_A stays stale.
            ModuleVersion(
                module_vid=402,
                module_id=20,
                code="M_AND_B",
                version_number="1.0",
                start_release_id=1,
                end_release_id=None,
                from_reference_date=datetime.date(2023, 6, 30),
                to_reference_date=None,
            ),
            ModuleParameters(module_vid=402, variable_vid=21),
        ]
    )
    memory_session.flush()
    svc = _svc(memory_session)

    with pytest.raises(SemanticError) as exc_info:
        svc._check_precondition_link(701, release_id=1)
    assert exc_info.value.code == "7-3"
    assert "20" in str(exc_info.value)
    assert "21" not in str(exc_info.value)


def _seed_two_filing_indicators_xor(session, *, first_live, second_live):
    session.add_all(
        [
            Release(release_id=1, code="3.4", date=datetime.date(2022, 12, 1)),
            Variable(variable_id=12, type="filingindicator"),
            VariableVersion(
                variable_vid=12,
                variable_id=12,
                code="XOR_A",
                start_release_id=1,
                end_release_id=None,
            ),
            Variable(variable_id=13, type="filingindicator"),
            VariableVersion(
                variable_vid=13,
                variable_id=13,
                code="XOR_B",
                start_release_id=1,
                end_release_id=None,
            ),
            OperationVersion(
                operation_vid=703,
                expression="{v_XOR_A} xor {v_XOR_B}",
                start_release_id=1,
                end_release_id=None,
            ),
            OperationNode(node_id=12, operation_vid=703),
            OperandReference(
                operand_reference_id=12, node_id=12, variable_id=12
            ),
            OperationNode(node_id=13, operation_vid=703),
            OperandReference(
                operand_reference_id=13, node_id=13, variable_id=13
            ),
        ]
    )
    if first_live:
        session.add_all(
            [
                ModuleVersion(
                    module_vid=403,
                    module_id=12,
                    code="M_XOR_A",
                    version_number="1.0",
                    start_release_id=1,
                    end_release_id=None,
                    from_reference_date=datetime.date(2023, 6, 30),
                    to_reference_date=None,
                ),
                ModuleParameters(module_vid=403, variable_vid=12),
            ]
        )
    if second_live:
        session.add_all(
            [
                ModuleVersion(
                    module_vid=404,
                    module_id=13,
                    code="M_XOR_B",
                    version_number="1.0",
                    start_release_id=1,
                    end_release_id=None,
                    from_reference_date=datetime.date(2023, 6, 30),
                    to_reference_date=None,
                ),
                ModuleParameters(module_vid=404, variable_vid=13),
            ]
        )
    session.flush()


def test_xor_gate_passes_when_only_one_side_is_live(memory_session):
    # xor takes the same branch as or in gate_satisfiable.
    _seed_two_filing_indicators_xor(
        memory_session, first_live=False, second_live=True
    )
    svc = _svc(memory_session)

    svc._check_precondition_link(703, release_id=1)  # no raise


def test_xor_gate_raises_7_3_when_both_sides_are_stale(memory_session):
    _seed_two_filing_indicators_xor(
        memory_session, first_live=False, second_live=False
    )
    svc = _svc(memory_session)

    with pytest.raises(SemanticError) as exc_info:
        svc._check_precondition_link(703, release_id=1)
    assert exc_info.value.code == "7-3"


def test_7_3_falls_back_to_the_stale_code_without_node_rows(memory_session):
    # No OperationNode rows, so the message falls back to the stale code.
    memory_session.add_all(
        [
            Release(release_id=1, code="3.4", date=datetime.date(2022, 12, 1)),
            Variable(variable_id=30, type="filingindicator"),
            VariableVersion(
                variable_vid=30,
                variable_id=30,
                code="NO_NODES",
                start_release_id=1,
                end_release_id=None,
            ),
            OperationVersion(
                operation_vid=702,
                expression="{v_NO_NODES}",
                start_release_id=1,
                end_release_id=None,
            ),
        ]
    )
    memory_session.flush()
    svc = _svc(memory_session)

    with pytest.raises(SemanticError) as exc_info:
        svc._check_precondition_link(702, release_id=1)
    assert exc_info.value.code == "7-3"
    assert "NO_NODES" in str(exc_info.value)


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


def _seed_precondition_operation(session, operation_vid, expression):
    session.add_all(
        [
            OperationVersion(
                operation_vid=operation_vid,
                expression=expression,
                start_release_id=1,
                end_release_id=None,
            ),
        ]
    )


def _seed_tables(session, *, fi_shares_operand_module: bool):
    """T1 (module M1) and FI_X are siblings under abstract ROOT, not
    parent and child, so T1 can't leak into FI_X's children and
    trivially pass the module check against itself.

    UNRELATED matches neither. ``fi_shares_operand_module=True`` puts
    FI_X in M1 too, so 7-5 passes; otherwise FI_X sits only in M2, so
    7-5 fails.
    """
    session.add_all(
        [
            Release(release_id=1, code="3.4", date=datetime.date(2022, 12, 1)),
            Table(table_id=1),
            Table(table_id=2),
            Table(table_id=3),
            Table(table_id=5),
            TableVersion(
                table_vid=50,
                code="ROOT",
                table_id=5,
                abstract_table_id=None,
                start_release_id=1,
                end_release_id=None,
            ),
            TableVersion(
                table_vid=10,
                code="T1",
                table_id=1,
                abstract_table_id=5,
                start_release_id=1,
                end_release_id=None,
            ),
            TableVersion(
                table_vid=20,
                code="FI_X",
                table_id=2,
                abstract_table_id=5,
                start_release_id=1,
                end_release_id=None,
            ),
            TableVersion(
                table_vid=30,
                code="UNRELATED",
                table_id=3,
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
    _seed_precondition_operation(memory_session, 600, "{v_FI_X}")
    memory_session.flush()
    svc = _svc(memory_session)
    svc.oc_tables = {"T1": {}}

    svc._check_precondition_link(600, release_id=1)  # no raise


def test_precondition_code_not_among_operand_abstract_tables_raises_7_4(
    memory_session,
):
    _seed_tables(memory_session, fi_shares_operand_module=True)
    _seed_precondition_operation(memory_session, 601, "{v_UNRELATED}")
    memory_session.flush()
    svc = _svc(memory_session)
    svc.oc_tables = {"T1": {}}

    with pytest.raises(SemanticError) as exc_info:
        svc._check_precondition_link(601, release_id=1)
    assert exc_info.value.code == "7-4"


def test_matching_table_but_different_module_raises_7_5(memory_session):
    _seed_tables(memory_session, fi_shares_operand_module=False)
    _seed_precondition_operation(memory_session, 602, "{v_FI_X}")
    memory_session.flush()
    svc = _svc(memory_session)
    svc.oc_tables = {"T1": {}}

    with pytest.raises(SemanticError) as exc_info:
        svc._check_precondition_link(602, release_id=1)
    assert exc_info.value.code == "7-5"


def test_or_gate_passes_7_4_when_one_table_matches(memory_session):
    _seed_tables(memory_session, fi_shares_operand_module=True)
    _seed_precondition_operation(
        memory_session, 605, "{v_UNRELATED} or {v_FI_X}"
    )
    memory_session.flush()
    svc = _svc(memory_session)
    svc.oc_tables = {"T1": {}}

    svc._check_precondition_link(605, release_id=1)  # no raise


def test_or_gate_raises_7_4_when_both_tables_mismatch(memory_session):
    _seed_tables(memory_session, fi_shares_operand_module=True)
    memory_session.add_all(
        [
            Table(table_id=4),
            TableVersion(
                table_vid=40,
                code="UNRELATED2",
                table_id=4,
                abstract_table_id=None,
                start_release_id=1,
                end_release_id=None,
            ),
        ]
    )
    memory_session.flush()
    _seed_precondition_operation(
        memory_session, 606, "{v_UNRELATED} or {v_UNRELATED2}"
    )
    memory_session.flush()
    svc = _svc(memory_session)
    svc.oc_tables = {"T1": {}}

    with pytest.raises(SemanticError) as exc_info:
        svc._check_precondition_link(606, release_id=1)
    assert exc_info.value.code == "7-4"


def test_or_gate_raises_7_5_when_the_matching_tables_module_differs(
    memory_session,
):
    # FI_X passes 7-4 but sits only in M2, and UNRELATED never matches on
    # table, so no branch fits both table and module and 7-5 must fire.
    _seed_tables(memory_session, fi_shares_operand_module=False)
    _seed_precondition_operation(
        memory_session, 607, "{v_UNRELATED} or {v_FI_X}"
    )
    memory_session.flush()
    svc = _svc(memory_session)
    svc.oc_tables = {"T1": {}}

    with pytest.raises(SemanticError) as exc_info:
        svc._check_precondition_link(607, release_id=1)
    assert exc_info.value.code == "7-5"


def _seed_abstract_precondition_table(session, *, child_shares_operand_module):
    """T1 and FI_ABS are siblings under ROOT; only FI_ABS's concrete
    child FI_V1 carries a module. ``child_shares_operand_module=True``
    puts FI_V1 in M1 too, so 7-5 passes; otherwise FI_V1 sits only in
    M2, so 7-5 fails.
    """
    session.add_all(
        [
            Release(release_id=1, code="3.4", date=datetime.date(2022, 12, 1)),
            Table(table_id=100),
            Table(table_id=101),
            Table(table_id=102),
            Table(table_id=110),
            TableVersion(
                table_vid=1100,
                code="ROOT",
                table_id=110,
                abstract_table_id=None,
                start_release_id=1,
                end_release_id=None,
            ),
            TableVersion(
                table_vid=1000,
                code="T1",
                table_id=100,
                abstract_table_id=110,
                start_release_id=1,
                end_release_id=None,
            ),
            TableVersion(
                table_vid=1010,
                code="FI_ABS",
                table_id=101,
                abstract_table_id=110,
                start_release_id=1,
                end_release_id=None,
            ),
            TableVersion(
                table_vid=1020,
                code="FI_V1",
                table_id=102,
                abstract_table_id=101,
                start_release_id=1,
                end_release_id=None,
            ),
            ModuleVersion(
                module_vid=1000,
                module_id=100,
                code="M1",
                version_number="1.0",
                start_release_id=1,
                end_release_id=None,
            ),
            ModuleVersionComposition(
                module_vid=1000, table_id=100, table_vid=1000
            ),
        ]
    )
    if child_shares_operand_module:
        session.add(
            ModuleVersionComposition(
                module_vid=1000, table_id=102, table_vid=1020
            )
        )
    else:
        session.add_all(
            [
                ModuleVersion(
                    module_vid=1001,
                    module_id=101,
                    code="M2",
                    version_number="1.0",
                    start_release_id=1,
                    end_release_id=None,
                ),
                ModuleVersionComposition(
                    module_vid=1001, table_id=102, table_vid=1020
                ),
            ]
        )
    session.flush()


def test_abstract_precondition_code_resolves_modules_via_concrete_child(
    memory_session,
):
    # FI_ABS carries no module itself, but FI_V1 shares the operand's.
    _seed_abstract_precondition_table(
        memory_session, child_shares_operand_module=True
    )
    _seed_precondition_operation(memory_session, 800, "{v_FI_ABS}")
    memory_session.flush()
    svc = _svc(memory_session)
    svc.oc_tables = {"T1": {}}

    svc._check_precondition_link(800, release_id=1)  # no raise


def test_abstract_precondition_code_still_raises_7_5_on_real_mismatch(
    memory_session,
):
    # FI_ABS's only concrete child, FI_V1, sits only in M2.
    _seed_abstract_precondition_table(
        memory_session, child_shares_operand_module=False
    )
    _seed_precondition_operation(memory_session, 801, "{v_FI_ABS}")
    memory_session.flush()
    svc = _svc(memory_session)
    svc.oc_tables = {"T1": {}}

    with pytest.raises(SemanticError) as exc_info:
        svc._check_precondition_link(801, release_id=1)
    assert exc_info.value.code == "7-5"


def test_expression_with_no_precondition_codes_is_a_noop(memory_session):
    _seed_tables(memory_session, fi_shares_operand_module=True)
    _seed_precondition_operation(memory_session, 603, "1 + 1")
    memory_session.flush()
    svc = _svc(memory_session)
    svc.oc_tables = {"T1": {}}

    svc._check_precondition_link(603, release_id=1)  # no raise


def test_malformed_precondition_expression_is_a_noop(memory_session):
    memory_session.add(
        Release(release_id=1, code="3.4", date=datetime.date(2022, 12, 1))
    )
    _seed_precondition_operation(memory_session, 604, "{{{not valid dpm-xl")
    memory_session.flush()
    svc = _svc(memory_session)
    svc.oc_tables = {"T1": {}}

    svc._check_precondition_link(604, release_id=1)  # no raise
