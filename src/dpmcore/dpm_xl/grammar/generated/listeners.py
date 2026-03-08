from antlr4.error.ErrorListener import ErrorListener

from dpmcore.errors import SyntaxError_


class DPMErrorListener(ErrorListener):
    def __init__(self):
        super().__init__()

    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
        # UTILS_UTILS.1
        raise SyntaxError_('offendingSymbol: {} msg: {}'.format(offendingSymbol, msg))
