"""Issue #121 — contradictory ``where`` clauses must yield a semantic error.

When a binary operator combines two operands that each pin the same key
component to a *different* literal value (``[where qEEA = A]`` and
``[where qEEA = B]``), the inner join over that key can never match a row,
so the validation is dead. The semantic analyzer must reject it (``2-2``)
rather than silently accepting it.
"""

from dpmcore.services.semantic import SemanticService

RELEASE = "4.2.1"

# The reported dead validation, ``v6200_m`` (current version).
V6200_M = (
    "with {c0110, default: 0, interval: true}: sum ({tC_101.00}) <= "
    "({tC_08.01.a, r0010}[where qEEA = [eba_qAE:qx2023]] + "
    "{tC_08.01.a, r0010}[where qEEA = [eba_qAE:qx2022]]) * 2"
)


def test_contradictory_where_yields_2_2(fixture_session):
    """``v6200_m`` pins qEEA to qx2023 vs qx2022 -> empty inner join."""
    result = SemanticService(fixture_session).validate(
        V6200_M, release_code=RELEASE
    )
    assert not result.is_valid
    assert result.error_code == "2-2"


def test_same_where_value_is_valid(fixture_session):
    """Both operands pinned to the same value still align -> valid."""
    expression = (
        "{tC_08.01.a, r0010}[where qEEA = [eba_qAE:qx2023]] + "
        "{tC_08.01.a, r0010}[where qEEA = [eba_qAE:qx2023]]"
    )
    result = SemanticService(fixture_session).validate(
        expression, release_code=RELEASE
    )
    assert result.is_valid, result.error_message


def test_single_where_operand_is_valid(fixture_session):
    """Only one operand pinned -> the other spans all values -> valid."""
    expression = (
        "{tC_08.01.a, r0010}[where qEEA = [eba_qAE:qx2023]] + "
        "{tC_08.01.a, r0010}"
    )
    result = SemanticService(fixture_session).validate(
        expression, release_code=RELEASE
    )
    assert result.is_valid, result.error_message
