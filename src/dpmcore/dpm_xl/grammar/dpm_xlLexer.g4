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
IN:                     'in' -> pushMode(SET_OPERAND_MODE);

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
YEAR:                   DIGITS0_9 DIGITS0_9 DIGITS0_9 DIGITS0_9;

fragment
MONTH:                  '0' DIGITS1_9
                        | '1' [0-2]
                        ;

fragment
WEEK:                   '0' DIGITS1_9
                        | [1-4] DIGITS0_9
                        | '5' [0-2]
                        ;

fragment
DAY:                    [0-2] DIGITS0_9
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
DATE_FORMAT:            YEAR '-' MONTH '-' DAY ('T' HOURS COLON MINUTES COLON SECONDS)?;

fragment
TIME_PERIOD_FORMAT:     YEAR 'A'?
                        | YEAR 'D' [0-3] DIGITS0_9 DIGITS0_9
                        | YEAR 'W' WEEK
                        | YEAR 'M' MONTH
                        | YEAR 'Q' [1-4]
                        | YEAR 'S' [1-2]
                        ;

DATE_LITERAL:           '#' DATE_FORMAT '#';

TIME_INTERVAL_LITERAL:  '#' DATE_FORMAT '/' DATE_FORMAT '#';

TIME_PERIOD_LITERAL:    '#' TIME_PERIOD_FORMAT '#';

CODE:                   [A-Za-z]([A-Za-z0-9_.]*[A-Za-z0-9])*;

WS:                     [ \t\r\n\u000C]+ -> channel(2);


mode SELECTION_MODE;

SELECTION_MODE_COMMA:        COMMA -> type(COMMA);
SELECTION_MODE_COLON:        COLON -> type(COLON);

SELECTION_MODE_LPAREN:                 LPAREN -> type(LPAREN);
SELECTION_MODE_RPAREN:                 RPAREN -> type(RPAREN);

SELECTION_MODE_CURLY_BRACKET_RIGHT:    CURLY_BRACKET_RIGHT -> popMode, type(CURLY_BRACKET_RIGHT);

INTERVAL: 'interval';
DEFAULT: 'default';

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
PRECONDITION_PREFIX:      'v_';


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

TABLE_REFERENCE:        TABLE_PREFIX TABLE_CODE;
TABLE_GROUP_REFERENCE:  TABLE_GROUP_PREFIX TABLE_CODE;

VAR_REFERENCE:                VAR_REF_PREFIX VAR_CODE;
OPERATION_REFERENCE:          OPERATION_REF_PREFIX OPERATION_CODE;
PRECONDITION_ELEMENT:         PRECONDITION_PREFIX TABLE_CODE;

SELECTION_MODE_INTEGER_LITERAL: INTEGER_LITERAL -> type(INTEGER_LITERAL);
SELECTION_MODE_DECIMAL_LITERAL: DECIMAL_LITERAL -> type(DECIMAL_LITERAL);
SELECTION_MODE_PERCENT_LITERAL: PERCENT_LITERAL -> type(PERCENT_LITERAL);

SELECTION_MODE_STRING_LITERAL: STRING_LITERAL -> type(STRING_LITERAL);
SELECTION_MODE_EMPTY_LITERAL: EMPTY_LITERAL -> type(EMPTY_LITERAL);

SELECTION_MODE_DATE_LITERAL: DATE_LITERAL -> type(DATE_LITERAL);
SELECTION_MODE_TIME_INTERVAL_LITERAL: TIME_INTERVAL_LITERAL -> type(TIME_INTERVAL_LITERAL);
SELECTION_MODE_TIME_PERIOD_LITERAL: TIME_PERIOD_LITERAL -> type(TIME_PERIOD_LITERAL);

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
CLAUSE_IN:                     'in' -> pushMode(SET_OPERAND_MODE), type(IN);

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

CLAUSE_TIME_INTERVAL_LITERAL:  '#' DATE_FORMAT '/' DATE_FORMAT '#' -> type(TIME_INTERVAL_LITERAL);

CLAUSE_TIME_PERIOD_LITERAL:    '#' TIME_PERIOD_FORMAT '#' -> type(TIME_PERIOD_LITERAL);

ITEM_SIGNATURE:             [A-Za-z]([A-Za-z0-9_-]*[:][A-Za-z0-9._-]*[A-Za-z0-9])+;
PROPERTY_CODE:              CODE;

CLAUSE_WS:                     [ \t\r\n\u000C]+ -> channel(2);


mode GROUPING_CLAUSE_MODE;

GROUPING_RPAREN:                    ')' -> type(RPAREN), popMode;
GROUPING_COMMA:                     ',' -> type(COMMA);

GROUPING_ROW_COMPONENT:            'r'  -> type(ROW_COMPONENT);
GROUPING_COL_COMPONENT:            'c'  -> type(COL_COMPONENT);
GROUPING_SHEET_COMPONENT:          's' -> type(SHEET_COMPONENT);
GROUPING_PROPERTY_CODE:            CODE -> type(PROPERTY_CODE);

GROUPING_WS:                     [ \t\r\n\u000C]+ -> channel(2);


mode SET_OPERAND_MODE;

SET_OPERAND_MODE_COMMA:        COMMA -> type(COMMA);

SET_OPERAND_MODE_CURLY_BRACKET_LEFT:     CURLY_BRACKET_LEFT -> type(CURLY_BRACKET_LEFT);
SET_OPERAND_MODE_CURLY_BRACKET_RIGHT:    CURLY_BRACKET_RIGHT -> popMode, type(CURLY_BRACKET_RIGHT);

SET_OPERAND_MODE_SQUARE_BRACKET_LEFT:    SQUARE_BRACKET_LEFT -> type(SQUARE_BRACKET_LEFT);
SET_OPERAND_MODE_SQUARE_BRACKET_RIGHT:   SQUARE_BRACKET_RIGHT -> type(SQUARE_BRACKET_RIGHT);

SET_OPERAND_MODE_ITEM_SIGNATURE:             ITEM_SIGNATURE -> type(ITEM_SIGNATURE);

SET_OPERAND_MODE_INTEGER_LITERAL: INTEGER_LITERAL -> type(INTEGER_LITERAL);
SET_OPERAND_MODE_DECIMAL_LITERAL: DECIMAL_LITERAL -> type(DECIMAL_LITERAL);
SET_OPERAND_MODE_PERCENT_LITERAL: PERCENT_LITERAL -> type(PERCENT_LITERAL);

SET_OPERAND_MODE_STRING_LITERAL: STRING_LITERAL -> type(STRING_LITERAL);
SET_OPERAND_MODE_EMPTY_LITERAL: EMPTY_LITERAL -> type(EMPTY_LITERAL);

SET_OPERAND_MODE_DATE_LITERAL: DATE_LITERAL -> type(DATE_LITERAL);
SET_OPERAND_MODE_TIME_INTERVAL_LITERAL: TIME_INTERVAL_LITERAL -> type(TIME_INTERVAL_LITERAL);
SET_OPERAND_MODE_TIME_PERIOD_LITERAL: TIME_PERIOD_LITERAL -> type(TIME_PERIOD_LITERAL);

SET_OPERAND_MODE_WS:        WS -> channel(2);