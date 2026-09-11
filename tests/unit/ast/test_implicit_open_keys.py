"""Unit tests for the implicit open-keys catalogue.

``IMPLICIT_OPEN_KEYS`` (in ``dpm_xl/ast/operands.py``) and the mirror
``global_variables`` map in ``dpm_xl/semantic_analyzer.py`` declare the
dimensions that arise from the reporting context itself and therefore do
not need to be looked up per-table via ``KeyComposition``.

Every entry here is consumed by ``check_dimensions``/
``check_getop_components`` in ``ast/operands.py`` to synthesize an
``open_keys`` DataFrame row with ``property_id = -1`` and the declared
scalar type. Regressions on these entries silently reject perfectly
valid DPM-XL expressions used by the published ECB EGDQ checks (see
``EGDQ_0510a`` etc. for ``baseCurrency``).
"""

from dpmcore.dpm_xl.ast.operands import IMPLICIT_OPEN_KEYS
from dpmcore.dpm_xl.semantic_analyzer import InputAnalyzer


def test_ref_period_is_implicit_open_key():
    """``refPeriod`` — the reference period of the report — stays declared
    as an implicit open key of date type ``"d"``.
    """
    assert IMPLICIT_OPEN_KEYS.get("refPeriod") == "d"


def test_entity_id_is_implicit_open_key():
    """``entityID`` — the reporting entity's identifier — stays declared
    as an implicit open key of string type ``"s"``.
    """
    assert IMPLICIT_OPEN_KEYS.get("entityID") == "s"


def test_base_currency_is_implicit_open_key():
    """``baseCurrency`` — the reporting currency of the entity — is
    declared as an implicit open key of string type ``"s"``.

    Regression against #232: the ECB EGDQ checks (rows highlighted yellow
    in the "DPM-XL publication" sheet Gregorio Guidi shared on
    2026-07-16) filter operational-risk rows by ``baseCurrency = 'EUR'``;
    that syntax must be accepted by the semantic analyser without
    requiring a per-module ``KeyComposition`` declaration.
    """
    assert IMPLICIT_OPEN_KEYS.get("baseCurrency") == "s"


def test_semantic_global_variables_mirror_implicit_open_keys():
    """The semantic analyser exposes the same set of implicit open keys
    via its ``global_variables`` map, so the two catalogues stay in sync.
    Any entry added to :data:`IMPLICIT_OPEN_KEYS` must also appear here,
    otherwise implicit keys would parse fine in ``check_dimensions``
    (via ``operands.py``) but be treated as undeclared in
    ``visit_Dimension`` (via ``semantic_analyzer.py``).
    """
    analyser = InputAnalyzer(expression="")
    assert set(IMPLICIT_OPEN_KEYS.keys()).issubset(
        set(analyser.global_variables.keys())
    ), (
        "IMPLICIT_OPEN_KEYS keys not covered by "
        "InputAnalyzer.global_variables: "
        f"{set(IMPLICIT_OPEN_KEYS) - set(analyser.global_variables)}"
    )
