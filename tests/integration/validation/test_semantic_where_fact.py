"""Issue #266 — ``[where f …]`` against the real dictionary.

Before the extension, a ``where`` condition naming the Fact Component died in
the operands pre-check with ``1-5 "open keys not found: ['f']"``, because
``f`` has no dictionary row and every condition identifier was resolved as an
open key. It must now resolve structurally, against the Fact Component of the
clause operand, while ``get``/``rename``/``sub`` keep rejecting it — with
``4-5-0-1`` rather than the misleading ``1-5``.
"""

from dpmcore.services.semantic import SemanticService

RELEASE = "4.2.1"

# C_08.01.a r0020 c0260 is the operand of published check v6200_m: a
# monetary cell whose selection carries an open key (``qEEA``).
OPERAND = "{tC_08.01.a, r0020, c0260}"


def test_where_on_fact_is_valid(fixture_session):
    """A Fact-only where condition passes semantic validation."""
    result = SemanticService(fixture_session).validate(
        f"{OPERAND}[where f > 0] >= 0", release_code=RELEASE
    )
    assert result.is_valid, result.error_message


def test_where_mixing_fact_and_open_key_is_valid(fixture_session):
    """The Fact composes with the DPM key components it used to exclude."""
    expression = (
        f"sum({OPERAND}[where f > 0 and qEEA in {{[eba_qAE:qx2018]}}]) >= 0"
    )
    result = SemanticService(fixture_session).validate(
        expression, release_code=RELEASE
    )
    assert result.is_valid, result.error_message


def test_where_on_fact_then_get_on_a_key_is_valid(fixture_session):
    """Chained clauses: the outer ``get`` still sees the filtered operand."""
    result = SemanticService(fixture_session).validate(
        f"{OPERAND}[where f > 0][get qEEA] >= 0", release_code=RELEASE
    )
    assert result.is_valid, result.error_message


def test_disjoint_fact_filters_do_not_yield_2_2(fixture_session):
    """Unlike a key, the Fact cannot make an inner join empty.

    Guards against a false ``2-2`` from the contradictory-where check of
    issue #121, which is keyed on *Key Components* only.
    """
    result = SemanticService(fixture_session).validate(
        f"{OPERAND}[where f = 1] = {OPERAND}[where f = 2]",
        release_code=RELEASE,
    )
    assert result.is_valid, result.error_message


def test_non_boolean_fact_condition_yields_3_3(fixture_session):
    """``f`` is typed from the operand, so a bare numeric fact is not a filter.

    This is what makes ``[where f and …]`` meaningful only on Boolean-typed
    selections: the condition must promote to Boolean.
    """
    result = SemanticService(fixture_session).validate(
        f"{OPERAND}[where f] >= 0", release_code=RELEASE
    )
    assert not result.is_valid
    assert result.error_code == "3-3"


def test_get_on_fact_yields_4_5_0_1(fixture_session):
    """Projecting onto the Fact stays invalid, with the structural error."""
    result = SemanticService(fixture_session).validate(
        f"{OPERAND}[get f] >= 0", release_code=RELEASE
    )
    assert not result.is_valid
    assert result.error_code == "4-5-0-1"


def test_rename_on_fact_yields_4_5_0_1(fixture_session):
    result = SemanticService(fixture_session).validate(
        f"{OPERAND}[rename f to qZZ] >= 0", release_code=RELEASE
    )
    assert not result.is_valid
    assert result.error_code == "4-5-0-1"


def test_sub_on_fact_yields_4_5_0_1(fixture_session):
    result = SemanticService(fixture_session).validate(
        f"{OPERAND}[sub f = 1] >= 0", release_code=RELEASE
    )
    assert not result.is_valid
    assert result.error_code == "4-5-0-1"
