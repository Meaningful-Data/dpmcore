from py_dpm.api.dpm_xl.ast_generator import parse_expression


def test_parse_expression_does_not_use_undefined_astobjects():
    """Regression test for NameError: ASTObjects not defined in serialization.

    Ensures that parse_expression runs successfully and returns a structured result.
    """
    expression = "{tC_01.00, r0100, c0010}"

    result = parse_expression(expression)

    assert isinstance(result, dict)
    assert result["success"] is True
    assert result["ast"] is not None
    assert result["error"] is None
