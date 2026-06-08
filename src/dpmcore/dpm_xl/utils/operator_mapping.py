from dpmcore.dpm_xl.operators.aggregate import (
    Avg,
    Count,
    MaxAggr,
    Median,
    MinAggr,
    Sum,
)
from dpmcore.dpm_xl.operators.arithmetic import (
    AbsoluteValue,
    BinMinus,
    BinPlus,
    Div,
    Exponential,
    Logarithm,
    Max,
    Min,
    Mult,
    NaturalLogarithm,
    Power,
    SquareRoot,
    UnMinus,
    UnPlus,
)
from dpmcore.dpm_xl.operators.boolean import And, Not, Or, Xor
from dpmcore.dpm_xl.operators.clause import Get, Rename, Sub, Where
from dpmcore.dpm_xl.operators.comparison import (
    Equal,
    Greater,
    GreaterEqual,
    In,
    IsNull,
    Less,
    LessEqual,
    Match,
    NotEqual,
)
from dpmcore.dpm_xl.operators.conditional import Filter, IfOperator, Nvl
from dpmcore.dpm_xl.operators.string import Concatenate, Len
from dpmcore.dpm_xl.operators.time import (
    Annualise,
    DateConstructor,
    Day,
    Month,
    Quarter,
    Semester,
    TimeShift,
    Week,
    Year,
)

from .tokens import *

BIN_OP_MAPPING = {
    # Boolean operators
    AND: And,
    OR: Or,
    XOR: Xor,
    # Comparison operators
    EQ: Equal,
    NEQ: NotEqual,
    GT: Greater,
    GTE: GreaterEqual,
    LT: Less,
    LTE: LessEqual,
    IN: In,
    MATCH: Match,
    # Numeric operators
    PLUS: BinPlus,
    MINUS: BinMinus,
    MULT: Mult,
    DIV: Div,
    POW: Power,
    LOG: Logarithm,
    # Conditional operator
    NVL: Nvl,
    # String operators
    CONCATENATE: Concatenate,
}

UNARY_OP_MAPPING = {
    # Boolean Operators
    NOT: Not,
    # Numeric Operators
    PLUS: UnPlus,
    MINUS: UnMinus,
    ABS: AbsoluteValue,
    EXP: Exponential,
    LN: NaturalLogarithm,
    SQRT: SquareRoot,
    # Comparison Operators
    ISNULL: IsNull,
    # String operators
    LENGTH: Len,
}

AGGR_OP_MAPPING = {
    MAX_AGGR: MaxAggr,
    MIN_AGGR: MinAggr,
    SUM: Sum,
    COUNT: Count,
    AVG: Avg,
    MEDIAN: Median,
}

CLAUSE_OP_MAPPING = {WHERE: Where, RENAME: Rename, GET: Get, SUB: Sub}

TIME_OPERATORS = {
    TIME_SHIFT: TimeShift,
    ANNUALISE: Annualise,
    YEAR: Year,
    SEMESTER: Semester,
    QUARTER: Quarter,
    MONTH: Month,
    WEEK: Week,
    DAY: Day,
    DATE: DateConstructor,
}

CONDITIONAL_OP_MAPPING = {IF: IfOperator, FILTER: Filter}

COMPLEX_OP_MAPPING = {MAX: Max, MIN: Min}
