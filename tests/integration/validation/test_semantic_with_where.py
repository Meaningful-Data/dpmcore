"""Issue #281 -- the ``where`` block of a ``with`` clause, against the real
dictionary.

The clause used to be parsed and thrown away, so it filtered nothing and
raised nothing. Now it is grafted onto every body selection (§3.2.5), which
means each selection is validated against it individually: a selection whose
table does not carry the referenced component is an error, not a silent
no-op.
"""

import json

from dpmcore.dpm_xl.utils.serialization import serialize_ast
from dpmcore.services.semantic import SemanticService

RELEASE = "4.2.1"

# C_08.01.a carries the open key ``qEEA``; C_01.00 has no open keys at all.
KEYED = "tC_08.01.a, r0010"
UNKEYED = "tC_01.00"


def _validate(session, expression):
    return SemanticService(session).validate(expression, release_code=RELEASE)


def test_with_level_where_is_valid(fixture_session):
    """A clause naming an open key of the body's table validates."""
    expression = (
        f"with {{{KEYED}}}[where qEEA = [eba_qAE:qx2023]]:"
        " {c0250} + {c0260} >= 0"
    )
    result = _validate(fixture_session, expression)
    assert result.is_valid, result.error_message


def test_payload_matches_the_explicit_per_operand_form(fixture_session):
    """The engine receives exactly the filter dpmcore validated.

    Comparing against the hand-written form pins the whole enriched
    payload -- cell ``data`` arrays included -- not just the presence of a
    ``WhereClauseOp``.
    """
    implicit = SemanticService(fixture_session)
    assert implicit.validate(
        f"with {{{KEYED}}}[where qEEA = [eba_qAE:qx2023]]:"
        " {c0250} + {c0260} >= 0",
        release_code=RELEASE,
    ).is_valid

    explicit = SemanticService(fixture_session)
    assert explicit.validate(
        "{tC_08.01.a, r0010, c0250}[where qEEA = [eba_qAE:qx2023]] + "
        "{tC_08.01.a, r0010, c0260}[where qEEA = [eba_qAE:qx2023]] >= 0",
        release_code=RELEASE,
    ).is_valid

    assert json.dumps(
        serialize_ast(implicit.ast), sort_keys=True, default=str
    ) == json.dumps(serialize_ast(explicit.ast), sort_keys=True, default=str)


def test_selection_on_a_table_without_the_component_yields_2_8(
    fixture_session,
):
    """§3.2.5: a selection the clause cannot apply to is an error.

    C_01.00 has no ``qEEA``. The same body without the block is valid, so
    the rejection comes from the clause now being applied rather than
    dropped.
    """
    body = "{c0250} = {tC_01.00, r0010, c0010}"

    unfiltered = _validate(fixture_session, f"with {{{KEYED}}}: {body}")
    assert unfiltered.is_valid, unfiltered.error_message

    filtered = _validate(
        fixture_session,
        f"with {{{KEYED}}}[where qEEA = [eba_qAE:qx2023]]: {body}",
    )
    assert not filtered.is_valid
    assert filtered.error_code == "2-8"


def test_unknown_property_yields_1_5(fixture_session):
    """A property with no dictionary row is caught by the operands pass."""
    result = _validate(
        fixture_session,
        f"with {{{KEYED}}}[where qZZZZ = 1]: {{c0250}} >= 0",
    )
    assert not result.is_valid
    assert result.error_code == "1-5"


def test_fact_only_clause_applies_without_open_keys(fixture_session):
    """Issue #266 amendment: ``f`` needs no open key on the table.

    C_01.00 declares none, and the body selection still spans rows, so the
    filter has records to choose between.
    """
    result = _validate(
        fixture_session,
        f"with {{{UNKEYED}}}[where f > 0]: sum({{c0010}}) >= 0",
    )
    assert result.is_valid, result.error_message


def test_fact_only_clause_on_a_single_datapoint_yields_4_5_2_3(
    fixture_session,
):
    """The selection must still be a recordset, not a Scalar.

    ``{tC_01.00, r0010, c0010}`` is one datapoint -- its only key components
    are the implicit globals -- so there is nothing for the filter to do.
    """
    result = _validate(
        fixture_session,
        f"with {{{UNKEYED}, r0010}}[where f > 0]: {{c0010}} >= 0",
    )
    assert not result.is_valid
    assert result.error_code == "4-5-2-3"


def test_operand_level_fact_clause_on_a_single_datapoint_also_rejected(
    fixture_session,
):
    """The guard is on the clause, so both spellings behave alike."""
    result = _validate(
        fixture_session, "{tC_01.00, r0010, c0010}[where f > 0] >= 0"
    )
    assert not result.is_valid
    assert result.error_code == "4-5-2-3"
