"""Semantic validation must reject ranges with a non-existent endpoint.

Regression test for issue #196: a range selection such as the typo
``c0010-c0030`` (a repeated selector letter) is read as the range from code
``0010`` to code ``c0030``. Column ``c0030`` does not exist in F_11.03, so the
range cannot resolve and the expression must fail semantic validation.
"""

from dpmcore.services.semantic import SemanticService

_EXPRESSION = (
    "with {{tF_11.03, c{cols}, default:0}}: "
    "{{r0010}} >= {{r0020}} + {{r0030}} + {{r0040}}"
)


def test_range_with_valid_endpoints_is_valid(fixture_session):
    """The writer's intended column range ``c0010-0030`` resolves cleanly."""
    svc = SemanticService(fixture_session)
    result = svc.validate(
        _EXPRESSION.format(cols="0010-0030"), release_code="4.2.1"
    )
    assert result.is_valid, result.error_message


def test_range_with_bogus_endpoint_is_invalid(fixture_session):
    """The typo ``c0010-c0030`` names a missing column and must be rejected."""
    svc = SemanticService(fixture_session)
    result = svc.validate(
        _EXPRESSION.format(cols="0010-c0030"), release_code="4.2.1"
    )
    assert not result.is_valid
    assert result.error_code == "1-2"
    assert "c0030" in (result.error_message or "")
