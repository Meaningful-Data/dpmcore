# Comparison operators.
EQ = '='
NEQ = '!='
GT = '>'
GTE = '>='
LT = '<'
LTE = '<='
IN = 'in'
ISNULL = 'isnull'
MATCH = 'match'

# Numeric operators
PLUS = '+'
MINUS = '-'
MULT = '*'
DIV = '/'
ABS = 'abs'
EXP = 'exp'
LN = 'ln'
SQRT = 'sqrt'
POW = 'power'
LOG = 'log'
MAX = 'max'
MIN = 'min'

# Boolean operators.
AND = 'and'
OR = 'or'
XOR = 'xor'
NOT = 'not'

# Conditional operators.
IF = "if"
NVL= "nvl"

# Clause operators
WHERE = 'where'
RENAME = 'rename'
GET = 'get'
SUB = 'sub'

# Aggregation operators
MAX_AGGR = 'max_aggr'
MIN_AGGR = 'min_aggr'
SUM = 'sum'
COUNT = 'count'
AVG = 'avg'
MEDIAN = 'median'

# String operators
LENGTH = "len"
CONCATENATE = "&"

# Time operators
TIME_SHIFT = 'time_shift'

# Conditional operators
FILTER = 'filter'

# key Components types
DPM = "DPM"
STANDARD = "Standard"

# Standard key names
ROW = 'r'
COLUMN = 'c'
SHEET = 's'
FACT = 'f'

# Indexes
INDEX_X = 'x'
INDEX_Y = 'y'
INDEX_Z = 'z'

# Cell components
ROW_CODE = 'row_code'
COLUMN_CODE = 'column_code'
SHEET_CODE = 'sheet_code'
TABLE_CODE = 'table_code'
CELL_COMPONENTS = [ROW_CODE, COLUMN_CODE, SHEET_CODE]

# Generated validations status
STATUS = 'status'
STATUS_CORRECT = 'Correct'
STATUS_INCORRECT = 'Incorrect'
STATUS_INCOMPLETE = 'Incomplete'
STATUS_UNKNOWN = 'Unknown'
TABLE_VERSION_ID = 'table_version_id'

# Generated validations constants
ITEM_ID = 'ItemID'
PARENT_ITEM_ID = 'ParentItemID'
VARIABLE_VID = 'variable_vid'
ARITHMETIC_OPERATOR_ID = 'ArithmeticOperatorID'
ORDER = 'Order'

TABLE_CODE_LEFT = TABLE_CODE + '_left'
ROW_CODE_LEFT = ROW_CODE + '_left'
COLUMN_CODE_LEFT = COLUMN_CODE + '_left'
SHEET_CODE_LEFT = SHEET_CODE + '_left'

TABLE_CODE_RIGHT = TABLE_CODE + '_right'
ROW_CODE_RIGHT = ROW_CODE + '_right'
COLUMN_CODE_RIGHT = COLUMN_CODE + '_right'
SHEET_CODE_RIGHT = SHEET_CODE + '_right'
VARIABLE_PROPERTY_ID = 'variable_property_id'

CONTEXT_PROPERTY = 'context_property'
OPERATOR_ID = 'OperatorID'
SYMBOL = 'Symbol'
ARITHMETIC_OPERATOR_SYMBOL = 'arithmetic_operator_symbol'
COMPARISON_OPERATOR_ID = 'ComparisonOperatorID'
COMPARISON_OPERATOR_SYMBOL = 'comparison_operator_symbol'

OPERATOR = 'operator'
IS_DEFAULT_ITEM = 'IsDefaultItem'
PROPERTY_ID = 'property_id'
CONTEXT_ITEM = 'context_item'
CONTEXT_ITEM_ID = 'context_item_id'
METRIC_PROPERTY_ID = 'metric_property_id'
CONTEXT_PROPERTY_ID = 'context_property_id'
SUBCATEGORY_PROPERTY = 'subcategory_property'

VALIDATION_CODE = 'validation_code'
TABLE_GROUP_CHILD_TYPE = 'tableGroup_child'
EXPRESSION = 'expression'
DUPLICATE_VARIABLES = 'duplicate_variables'
CELL_ID = 'cell_id'
SUBCATEGORY_ID = 'subcategory_id'
SUBCATEGORY_CODE = 'subcategory_code'
PARENT_ID = 'parent_id'
LEFT_CELL_IDS = 'left_cell_ids'
KEY_ID = 'KeyID'

# Data types
PER = "p"

INPUTS = 'inputs'
OUTPUTS = 'outputs'

# Prefix
TABLE_GROUP_PREFIX = 'g'

# Modules
INTRA_MODULE = 'intra-module'
CROSS_MODULE = 'cross-module'
REPEATED_INTRA_MODULE = 'repeated-intra-module'
REPEATED_CROSS_MODULE = 'repeated-cross-module'

# Operation scope constants
WARNING_SEVERITY = 'warning'

# Severity levels
SEVERITY_ERROR = 'error'
SEVERITY_WARNING = 'warning'
SEVERITY_INFO = 'info'
VALID_SEVERITIES = frozenset({SEVERITY_ERROR, SEVERITY_WARNING, SEVERITY_INFO})
DEFAULT_SEVERITY = SEVERITY_ERROR

FILING_INDICATOR = 'filingIndicator'
OP_VERSION_ID = 'op_version_id'

# Report types
HIERARCHY_REPORT = 'hierarchy_report'
SIGN_REPORT = 'sign_report'
EXISTENCE_REPORT = 'existence_report'
HIERARCHY = 'hierarchy'
SIGN = 'sign'
EXISTENCE = 'existence'
#sign
POSITIVE = 'positive'
NEGATIVE = 'negative'

# Web service constants
CODE = 'code'
ERROR = 'error'
ERROR_CODE = 'error_code'
VALIDATIONS = 'validations'
VARIABLES = 'variables'
VALIDATION_TYPE = 'validation_type'
