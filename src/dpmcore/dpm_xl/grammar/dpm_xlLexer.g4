lexer grammar dpm_xlLexer;

// ------------ Individual tokens -----------

// Boolean
BOOLEAN_LITERAL:
    'true'
    | 'false'
    ;

AND:                    'and';
OR:                     'or';
XOR:                    'xor';

NOT:                    'not';

// Assign
ASSIGN:                 ':=';
PERSISTENT_ASSIGN:      '<-';

// Comparison
EQ:                     '=';
NE:                     '!=';
LT:                     '<';
LE:                     '<=';
GT:                     '>';
GE:                     '>=';

// Matches
MATCH:                'match';

// With
WITH:                   'with';

// Arithmetic
PLUS:                   '+';
MINUS:                  '-';
MULT:                   '*';
DIV:                    '/';

// Aggregate
MAX_AGGR:                       'max_aggr';
MIN_AGGR:                       'min_aggr';
SUM:                            'sum';
COUNT:                          'count';
AVG:                            'avg';
MEDIAN:                         'median';

// Grouping
GROUP_BY:               'group by' -> pushMode(GROUPING_CLAUSE_MODE);

// Unary
ABS:                    'abs';
ISNULL:                 'isnull';
EXP:                    'exp';
LN:                     'ln';
SQRT:                   'sqrt';

// Binary
POWER:                          'power';
LOG:                            'log';

MAX:                            'max';
MIN:                            'min';

// Belonging
// ``in`` does not push a dedicated mode: the following ``{`` pushes
// SELECTION_MODE (see CURLY_BRACKET_LEFT), which knows item signatures,
// literals and parameter references — so set parameters work as the RHS of
// ``in`` without a separate SET_OPERAND_MODE.
IN:                     'in';

// Punctuation elements
COMMA:                  ',';
COLON:                  ':';

// Parenthesis
LPAREN:                 '(';
RPAREN:                 ')';


// Brackets
CURLY_BRACKET_LEFT:     '{' -> pushMode(SELECTION_MODE);
CURLY_BRACKET_RIGHT:    '}';
SQUARE_BRACKET_LEFT:    '[' -> pushMode(CLAUSE_MODE);
SQUARE_BRACKET_RIGHT:   ']';


// Conditional
IF:                     'if';
ENDIF:                  'endif';
THEN:                   'then';
ELSE:                   'else';
NVL:                    'nvl';

// Filter
FILTER:                 'filter';

// Clause
WHERE:                  'where';
GET:                    'get';
RENAME:                 'rename';
TO:                     'to';
SUB:                    'sub';

// Reference date
TIME_SHIFT:             'time_shift';
ANNUALISE:              'annualise';

// Date-component extraction
YEAR:                   'year';
SEMESTER:               'semester';
QUARTER:                'quarter';
MONTH:                  'month';
WEEK:                   'week';
DAY:                    'day';

// Date constructor
DATE:                   'date';

// String
LEN:                    'len';
CONCAT:                 '&';

// Time periods

TIME_PERIOD:            'A'
                        | 'S'
                        | 'Q'
                        | 'M'
                        | 'W'
                        | 'D'
                        ;

// End of line
EOL:                    ';';


// ------------ Literals ---------------
fragment
DIGITS0_9:              '0'..'9';
fragment
DIGITS1_9:              '1'..'9';

INTEGER_LITERAL:        DIGITS0_9+
                        | LPAREN MINUS DIGITS0_9+ RPAREN;
DECIMAL_LITERAL:        INTEGER_LITERAL '.' INTEGER_LITERAL;
PERCENT_LITERAL:        INTEGER_LITERAL '%'
                        | DECIMAL_LITERAL '%'
                        ;
NULL_LITERAL:           'null';
STRING_LITERAL:         '"' (~'"')+ '"' | '\'' (~'\'')+ '\'';
EMPTY_LITERAL:          '\'\'' | '""';

fragment
YYYY:                   DIGITS0_9 DIGITS0_9 DIGITS0_9 DIGITS0_9;

fragment
MM:                     '0' DIGITS1_9
                        | '1' [0-2]
                        ;

fragment
WW:                     '0' DIGITS1_9
                        | [1-4] DIGITS0_9
                        | '5' [0-2]
                        ;

fragment
DD:                     [0-2] DIGITS0_9
                        | '3' [0-1];

fragment
HOURS:                  [0-1] DIGITS0_9
                        | '2' [0-3]
                        ;

fragment
MINUTES:                [0-5] DIGITS0_9;

fragment
SECONDS:                [0-5] DIGITS0_9;

fragment
DATE_FORMAT:            YYYY '-' MM '-' DD ('T' HOURS COLON MINUTES COLON SECONDS)?;

DATE_LITERAL:           '#' DATE_FORMAT '#';

CODE:                   [A-Za-z]([A-Za-z0-9_.]*[A-Za-z0-9])*;
ESCAPED_IDENTIFIER:     '`' [A-Za-z0-9_.+]+ '`';

WS:                     [ \t\r\n\u000C]+ -> channel(2);


mode SELECTION_MODE;

SELECTION_MODE_COMMA:        COMMA -> type(COMMA);
SELECTION_MODE_COLON:        COLON -> type(COLON);

SELECTION_MODE_LPAREN:                 LPAREN -> type(LPAREN);
SELECTION_MODE_RPAREN:                 RPAREN -> type(RPAREN);

// A ``{`` inside a selection opens a nested selection (set-typed parameter
// defaults, e.g. ``default: {[ns:code]}``). It re-pushes SELECTION_MODE so the
// matching ``}`` (SELECTION_MODE_CURLY_BRACKET_RIGHT) pops back one level.
SELECTION_MODE_CURLY_BRACKET_LEFT:     CURLY_BRACKET_LEFT -> type(CURLY_BRACKET_LEFT), pushMode(SELECTION_MODE);
SELECTION_MODE_CURLY_BRACKET_RIGHT:    CURLY_BRACKET_RIGHT -> popMode, type(CURLY_BRACKET_RIGHT);

INTERVAL: 'interval';
DEFAULT: 'default';

// Parameter Selection types ({p_code, <type>}). These keywords MUST precede
// the SHEET/SHEET_RANGE rules below so ``string`` is not lexed as the SHEET
// ``s`` + ``tring`` and ``set-number`` is not lexed as a sheet range. The set
// variants come first so they win over their scalar prefixes on equal length.
SET_NUMBER:  'set-number';
SET_INTEGER: 'set-integer';
SET_STRING:  'set-string';
SET_DATE:    'set-date';
SET_BOOLEAN: 'set-boolean';
SET_ITEM:    'set-item';

NUMBER:    'number';
INTEGER:   'integer';
STRING:    'string';
// Named PARAM_DATE (not DATE) to avoid colliding with a future ``date(...)``
// constructor token; the parser maps it to the ``date`` parameter type.
PARAM_DATE: 'date';
BOOLEAN:   'boolean';
ITEM:      'item';

SELECTION_MODE_NULL_LITERAL: NULL_LITERAL -> type(NULL_LITERAL);
SELECTION_MODE_BOOLEAN_LITERAL: BOOLEAN_LITERAL -> type(BOOLEAN_LITERAL);

// Prefix

fragment
ROW_PREFIX:            'r';
fragment
COL_PREFIX:            'c';
fragment
SHEET_PREFIX:          's';
fragment
TABLE_PREFIX:           't';
fragment
TABLE_GROUP_PREFIX:     'g';

fragment
VAR_REF_PREFIX:         'v';
fragment
OPERATION_REF_PREFIX:   'o';
fragment
PARAMETER_REF_PREFIX:   'p';

// Codes

fragment
TABLE_CODE:                 [A-Za-z]([A-Za-z0-9_.-]*[A-Za-z0-9])*
                            ;
fragment
CELL_COMPONENT_CODE:        [0-9A-Za-z]+;
fragment
CELL_COMPONENT_RANGE:       CELL_COMPONENT_CODE [-] CELL_COMPONENT_CODE;

fragment
VAR_CODE:               [A-Za-z]([A-Za-z0-9_.]*[A-Za-z0-9])*;
fragment
OPERATION_CODE:         [A-Za-z]([A-Za-z0-9_.]*[A-Za-z0-9])*;

ROW:                    ROW_PREFIX CELL_COMPONENT_CODE;
ROW_RANGE:              ROW_PREFIX CELL_COMPONENT_RANGE;
ROW_ALL:                ROW_PREFIX [*];

COL:                    COL_PREFIX CELL_COMPONENT_CODE;
COL_RANGE:              COL_PREFIX CELL_COMPONENT_RANGE;
COL_ALL:                COL_PREFIX [*];

SHEET:                  SHEET_PREFIX CELL_COMPONENT_CODE;
SHEET_RANGE:            SHEET_PREFIX CELL_COMPONENT_RANGE;
SHEET_ALL:              SHEET_PREFIX [*];

TABLE_REFERENCE:        TABLE_PREFIX ('_'? TABLE_CODE | ESCAPED_IDENTIFIER);
TABLE_GROUP_REFERENCE:  TABLE_GROUP_PREFIX ('_'? TABLE_CODE | ESCAPED_IDENTIFIER);

VAR_REFERENCE:                VAR_REF_PREFIX ('_'? VAR_CODE | ESCAPED_IDENTIFIER);
OPERATION_REFERENCE:          OPERATION_REF_PREFIX ('_'? OPERATION_CODE | ESCAPED_IDENTIFIER);

// Parameter reference: ``{p_code, ...}``. The ``'_'?`` makes the underscore a
// cosmetic separator (``pthreshold`` == ``p_threshold``); a code that itself
// starts with ``_`` is reached via the backtick-escaped form (``p`_legacy```).
PARAMETER_REFERENCE:          PARAMETER_REF_PREFIX ('_'? VAR_CODE | ESCAPED_IDENTIFIER);

// Item-typed parameter defaults (``default: [ns:code]``) need item signatures.
// ``[`` pushes CLAUSE_MODE (as the default-mode ``[`` does) so the signature is
// lexed there and the matching ``]`` pops back. A bare ITEM_SIGNATURE token in
// SELECTION_MODE must NOT be added: it would greedily swallow ``default:0`` (no
// space) as a single ``default:0`` item signature.
SELECTION_MODE_SQUARE_BRACKET_LEFT:    SQUARE_BRACKET_LEFT -> type(SQUARE_BRACKET_LEFT), pushMode(CLAUSE_MODE);

SELECTION_MODE_INTEGER_LITERAL: INTEGER_LITERAL -> type(INTEGER_LITERAL);
SELECTION_MODE_DECIMAL_LITERAL: DECIMAL_LITERAL -> type(DECIMAL_LITERAL);
SELECTION_MODE_PERCENT_LITERAL: PERCENT_LITERAL -> type(PERCENT_LITERAL);

SELECTION_MODE_STRING_LITERAL: STRING_LITERAL -> type(STRING_LITERAL);
SELECTION_MODE_EMPTY_LITERAL: EMPTY_LITERAL -> type(EMPTY_LITERAL);

SELECTION_MODE_DATE_LITERAL: DATE_LITERAL -> type(DATE_LITERAL);

SELECTION_MODE_WS:        WS -> channel(2);


mode CLAUSE_MODE;

CLAUSE_BOOLEAN_LITERAL: BOOLEAN_LITERAL -> type(BOOLEAN_LITERAL);

CLAUSE_AND:                    'and' -> type(AND);
CLAUSE_OR:                     'or' -> type(OR);
CLAUSE_XOR:                    'xor' -> type(XOR);

CLAUSE_NOT:                    'not' -> type(NOT);

// Comparison
CLAUSE_EQ:                     '=' -> type(EQ);
CLAUSE_NE:                     '!=' -> type(NE);
CLAUSE_LT:                     '<' -> type(LT);
CLAUSE_LE:                     '<=' -> type(LE);
CLAUSE_GT:                     '>' -> type(GT);
CLAUSE_GE:                     '>=' -> type(GE);

// Matches
CLAUSE_MATCH:                'match' -> type(MATCH);

// Arithmetic
CLAUSE_PLUS:                   '+' -> type(PLUS);
CLAUSE_MINUS:                  '-' -> type(MINUS);
CLAUSE_MULT:                   '*' -> type(MULT);
CLAUSE_DIV:                    '/' -> type(DIV);

// Aggregate
CLAUSE_MAX_AGGR:                       'max_aggr' -> type(MAX_AGGR);
CLAUSE_MIN_AGGR:                       'min_aggr' -> type(MIN_AGGR);
CLAUSE_SUM:                            'sum' -> type(SUM);
CLAUSE_COUNT:                          'count' -> type(COUNT);
CLAUSE_AVG:                            'avg' -> type(AVG);
CLAUSE_MEDIAN:                         'median' -> type(MEDIAN);

// Grouping
CLAUSE_GROUP_BY:               'group by' -> type(GROUP_BY), pushMode(GROUPING_CLAUSE_MODE);

// Unary
CLAUSE_ABS:                    'abs' -> type(ABS);
CLAUSE_ISNULL:                 'isnull' -> type(ISNULL);
CLAUSE_EXP:                    'exp' -> type(EXP);
CLAUSE_LN:                     'ln' -> type(LN);
CLAUSE_SQRT:                   'sqrt' -> type(SQRT);

// Binary
CLAUSE_POWER:                          'power' -> type(POWER);
CLAUSE_LOG:                            'log' -> type(LOG);

CLAUSE_MAX:                            'max' -> type(MAX);
CLAUSE_MIN:                            'min' -> type(MIN);

// Belonging
CLAUSE_IN:                     'in' -> type(IN);

// Punctuation elements
CLAUSE_COMMA:                  ',' -> type(COMMA);
CLAUSE_COLON:                  ':' -> type(COLON);

// Parenthesis
CLAUSE_LPAREN:                 '(' -> type(LPAREN);
CLAUSE_RPAREN:                 ')' -> type(RPAREN);


// Brackets
CLAUSE_CURLY_BRACKET_LEFT:     '{' -> type(CURLY_BRACKET_LEFT), pushMode(SELECTION_MODE);
CLAUSE_CURLY_BRACKET_RIGHT:    '}'  -> type(CURLY_BRACKET_RIGHT);
CLAUSE_SQUARE_BRACKET_LEFT:    '[' -> type(SQUARE_BRACKET_LEFT), pushMode(CLAUSE_MODE);
CLAUSE_SQUARE_BRACKET_RIGHT:   ']' -> type(SQUARE_BRACKET_RIGHT), popMode;


// Conditional
CLAUSE_IF:                     'if' -> type(IF);
CLAUSE_ENDIF:                  'endif' -> type(ENDIF);
CLAUSE_THEN:                   'then' -> type(THEN);
CLAUSE_ELSE:                   'else' -> type(ELSE);
CLAUSE_NVL:                    'nvl' -> type(NVL);

// Filter
CLAUSE_FILTER:                 'filter' -> type(FILTER);

// Clause
CLAUSE_WHERE:                  'where' -> type(WHERE);
CLAUSE_GET:                    'get' -> type(GET);
CLAUSE_RENAME:                 'rename' -> type(RENAME);
CLAUSE_TO:                     'to' -> type(TO);
CLAUSE_SUB:                    'sub' -> type(SUB);

// Reference date
CLAUSE_TIME_SHIFT:             'time_shift' -> type(TIME_SHIFT);
CLAUSE_ANNUALISE:              'annualise' -> type(ANNUALISE);

// Date-component extraction
CLAUSE_YEAR:                   'year' -> type(YEAR);
CLAUSE_SEMESTER:               'semester' -> type(SEMESTER);
CLAUSE_QUARTER:                'quarter' -> type(QUARTER);
CLAUSE_MONTH:                  'month' -> type(MONTH);
CLAUSE_WEEK:                   'week' -> type(WEEK);
CLAUSE_DAY:                    'day' -> type(DAY);

// Date constructor
CLAUSE_DATE:                   'date' -> type(DATE);

// String
CLAUSE_LEN:                    'len' -> type(LEN);
CLAUSE_CONCAT:                 '&' -> type(CONCAT);

// Regex

// Prefix
ROW_COMPONENT:            'r';
COL_COMPONENT:            'c';
SHEET_COMPONENT:          's';

// Time periods

CLAUSE_TIME_PERIOD: TIME_PERIOD -> type(TIME_PERIOD);

CLAUSE_INTEGER_LITERAL: INTEGER_LITERAL -> type(INTEGER_LITERAL);
CLAUSE_DECIMAL_LITERAL:        DECIMAL_LITERAL -> type(DECIMAL_LITERAL);
CLAUSE_PERCENT_LITERAL: PERCENT_LITERAL -> type(PERCENT_LITERAL);

CLAUSE_STRING_LITERAL:         STRING_LITERAL -> type(STRING_LITERAL);
CLAUSE_EMPTY_LITERAL:          EMPTY_LITERAL -> type(EMPTY_LITERAL);

CLAUSE_DATE_LITERAL:           '#' DATE_FORMAT '#' -> type(DATE_LITERAL);

ITEM_SIGNATURE:             [A-Za-z]([A-Za-z0-9_-]*[:][A-Za-z0-9._-]*[A-Za-z0-9])+;
PROPERTY_CODE:              CODE;
CLAUSE_ESCAPED_IDENTIFIER: '`' [A-Za-z0-9_.+]+ '`' -> type(ESCAPED_IDENTIFIER);

CLAUSE_WS:                     [ \t\r\n\u000C]+ -> channel(2);


mode GROUPING_CLAUSE_MODE;

GROUPING_RPAREN:                    ')' -> type(RPAREN), popMode;
GROUPING_COMMA:                     ',' -> type(COMMA);

GROUPING_ROW_COMPONENT:            'r'  -> type(ROW_COMPONENT);
GROUPING_COL_COMPONENT:            'c'  -> type(COL_COMPONENT);
GROUPING_SHEET_COMPONENT:          's' -> type(SHEET_COMPONENT);
GROUPING_PROPERTY_CODE:            CODE -> type(PROPERTY_CODE);
GROUPING_ESCAPED_IDENTIFIER: '`' [A-Za-z0-9_.+]+ '`' -> type(ESCAPED_IDENTIFIER);

GROUPING_WS:                     [ \t\r\n\u000C]+ -> channel(2);


// SET_OPERAND_MODE removed: ``in`` no longer pushes a dedicated mode — the
// ``{`` following it pushes SELECTION_MODE, which already lexes item
// signatures, literals and parameter references for set operands.