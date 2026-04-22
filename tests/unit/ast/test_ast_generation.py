from dpmcore.services.ast_generator import ASTGeneratorService


def test_parse_expression_does_not_use_undefined_astobjects():
    """Regression test for NameError: ASTObjects not defined in serialization.

    Ensures that ASTGeneratorService.parse runs successfully and returns
    a structured result.
    """
    expression = "{tC_01.00, r0100, c0010}"

    result = ASTGeneratorService().parse(expression)

    assert isinstance(result, dict)
    assert result["success"] is True
    assert result["ast"] is not None
    assert result["error"] is None
