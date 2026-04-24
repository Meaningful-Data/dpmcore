"""Syntax validation service — no database required."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from antlr4 import CommonTokenStream, InputStream

from dpmcore.dpm_xl.ast.constructor import ASTVisitor
from dpmcore.dpm_xl.grammar.generated.dpm_xlLexer import dpm_xlLexer
from dpmcore.dpm_xl.grammar.generated.dpm_xlParser import dpm_xlParser
from dpmcore.dpm_xl.grammar.generated.listeners import DPMErrorListener
from dpmcore.errors import SyntaxError_


@dataclass(frozen=True)
class SyntaxResult:
    """Outcome of a syntax validation."""

    is_valid: bool
    error_message: Optional[str]
    expression: str


class SyntaxService:
    """Validate and parse DPM-XL expression syntax.

    This service is stateless and does **not** require a database
    connection.
    """

    def __init__(self) -> None:
        """Build a stateless syntax validator."""
        # DPMErrorListener lives in grammar/ (untyped generated code).
        self._error_listener = DPMErrorListener()  # type: ignore[no-untyped-call]
        self._visitor = ASTVisitor()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def validate(self, expression: str) -> SyntaxResult:
        """Validate the syntax of *expression*.

        Returns a :class:`SyntaxResult` — never raises on invalid
        syntax.
        """
        try:
            self._parse(expression)
            return SyntaxResult(
                is_valid=True,
                error_message=None,
                expression=expression,
            )
        except (SyntaxError_, SyntaxError) as exc:
            return SyntaxResult(
                is_valid=False,
                error_message=str(exc),
                expression=expression,
            )
        except Exception as exc:
            return SyntaxResult(
                is_valid=False,
                error_message=f"Unexpected error: {exc}",
                expression=expression,
            )

    def parse(self, expression: str) -> Any:
        """Parse *expression* and return the AST root node.

        Raises on syntax errors.
        """
        parse_tree = self._parse(expression)
        return self._visitor.visit(parse_tree)

    def is_valid(self, expression: str) -> bool:
        """Quick boolean check."""
        return self.validate(expression).is_valid

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _parse(self, expression: str) -> Any:
        """Run ANTLR lexer + parser, return the parse tree."""
        input_stream = InputStream(expression)
        lexer = dpm_xlLexer(input_stream)
        lexer._listeners = [self._error_listener]
        token_stream = CommonTokenStream(lexer)

        parser = dpm_xlParser(token_stream)
        parser._listeners = [self._error_listener]
        # parser.start lives in grammar/ (untyped generated code).
        tree = parser.start()  # type: ignore[no-untyped-call]

        if parser._syntaxErrors > 0:
            raise SyntaxError_("Syntax errors detected")
        return tree
