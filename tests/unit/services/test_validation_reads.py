"""Unit tests for what each validation of a script reads."""

from unittest.mock import MagicMock

import pandas as pd

from dpmcore.dpm_xl.ast.nodes import BinOp, Constant, Dimension, VarID
from dpmcore.dpm_xl.utils.db_ast import _DbSubClauseOp
from dpmcore.services.ast_generator import ASTGeneratorService
from dpmcore.services.script_document.modules import AT_T, Read, RefDateLag
from dpmcore.services.syntax import SyntaxService


def _svc():
    svc = ASTGeneratorService()
    svc.session = MagicMock()
    return svc


def _holding(node, *variable_ids):
    """Give an operand the Variables validation resolves it to."""
    node.data = pd.DataFrame({"variable_id": list(variable_ids)})
    return node


def _built(table, *variable_ids):
    """An operand rebuilt from the database."""
    node = VarID(table, None, None, None, False, None)
    node._db_ast_dict = {
        "class_name": "VarID",
        "table": table,
        "data": [{"datapoint": v} for v in variable_ids],
    }
    return node


def _sub(operand, property_code):
    """A ``sub`` rebuilt from the database."""
    return _DbSubClauseOp(
        operand=operand,
        condition=BinOp(
            Dimension(property_code), "=", Constant("Date", "2025-12-31")
        ),
    )


class TestExtractReads:
    def test_an_operand_reads_the_variables_it_holds(self):
        svc = _svc()
        ast = SyntaxService().parse(
            "{tA, r0010-0020, c0010} = "
            "time_shift({tB, r0030, c0010}, A, 1, refPeriod)"
        )
        expression = ast.children[0]
        _holding(expression.left, 10, 20)
        _holding(expression.right.operand, 30)

        assert svc._extract_reads(ast) == [
            Read(0, "A", frozenset({10, 20}), AT_T),
            Read(0, "B", frozenset({30}), RefDateLag(-12)),
        ]
        assert svc.session.method_calls == []

    def test_the_partial_selection_of_a_with_is_not_read(self):
        ast = SyntaxService().parse("with {tA, c0010}: {r0010} > 0")
        operand = ast.children[0].expression.left
        operand.table = "A"
        _holding(operand, 10)

        assert _svc()._extract_reads(ast) == [
            Read(0, "A", frozenset({10}), AT_T)
        ]

    def test_an_operand_from_the_database_reads_its_datapoints(self):
        assert _svc()._extract_reads(
            BinOp(_built("A", 10, 20), ">", Constant("Integer", 0))
        ) == [Read(0, "A", frozenset({10, 20}), AT_T)]

    def test_a_sub_from_the_database_on_ref_period_lands_anywhere(self):
        reads = _svc()._extract_reads(
            BinOp(
                _sub(_built("A", 10), "refPeriod"),
                "=",
                _sub(_built("B", 20), "qEGS"),
            )
        )

        assert reads == [
            Read(0, "A", frozenset({10}), None),
            Read(0, "B", frozenset({20}), AT_T),
        ]
