parser grammar dpm_xlParser;

options { tokenVocab=dpm_xlLexer ;}

// Added rule for expr management and EOF
start:
    statement ((EOL statements) | EOL?) EOF
    ;

statements:
    (statement EOL)+
    ;

statement:
    expressionWithoutAssignment                                                                      #exprWithoutAssignment
    | temporaryAssignmentExpression                                                                  #assignmentExpr
    | persistentAssignmentExpression                                                                 #persistentAssignExpr
    ;

persistentExpression:
    persistentAssignmentExpression
    | expressionWithoutAssignment
    ;

expressionWithoutAssignment:
    expression                                                                  #exprWithoutPartialSelection
    | WITH partialSelection
    (SQUARE_BRACKET_LEFT WHERE expression SQUARE_BRACKET_RIGHT)?
    COLON expression                                                            #exprWithSelection
    ;

partialSelection:
    CURLY_BRACKET_LEFT cellRef CURLY_BRACKET_RIGHT                              #partialSelect
    ;

temporaryAssignmentExpression:
    temporaryIdentifier ASSIGN persistentExpression
    ;

persistentAssignmentExpression:
    assignmentTarget PERSISTENT_ASSIGN expressionWithoutAssignment
    ;

assignmentTarget:
    CURLY_BRACKET_LEFT (cellRef | varRef) CURLY_BRACKET_RIGHT
    ;

expression:
    LPAREN expression RPAREN                                                                            #parExpr
    | functions                                                                                         #funcExpr
    | expression SQUARE_BRACKET_LEFT clauseOperators SQUARE_BRACKET_RIGHT                               #clauseExpr
    | op=(PLUS|MINUS) expression                                                                        #unaryExpr
    | op=NOT expression                                                                                 #notExpr
    | left=expression op=(MULT|DIV) right=expression                                                    #numericExpr
    | left=expression op=(PLUS|MINUS) right=expression                                                  #numericExpr
    | left=expression op=CONCAT right=expression                                                        #concatExpr
    | left=expression op=comparisonOperators right=expression                                           #compExpr
    | left=expression op=IN right=expression                                                            #inExpr
    | left=expression op=AND right=expression                                                           #boolExpr
    | left=expression op=(OR|XOR) right=expression                                                      #boolExpr
    | IF conditionalExpr=expression THEN thenExpr=expression (ELSE elseExpr=expression)? ENDIF          #ifExpr
    | itemReference                                                                                     #itemReferenceExpr
    | propertyReference                                                                                 #propertyReferenceExpr
    | keyNames                                                                                          #keyNamesExpr
    | literal                                                                                           #literalExpr
    | select                                                                                            #selectExpr
    | setExpression                                                                                     #setExpr
    ;

// A set literal: an explicit enumeration of elements, or `{}` for the empty
// set. The leading token of an element (`[` for an item signature, or a
// literal) cannot begin a `select`, so a set literal is never confused with a
// Subcategory selection such as `{c020}`.
setOperand:
    CURLY_BRACKET_LEFT setElements? CURLY_BRACKET_RIGHT
    ;

setElements:
    itemReference (COMMA itemReference)*
    | literal (COMMA literal)*
    ;

// Set-valued Operators. Operands are ordinary expressions: a set literal, a
// Subcategory selection, a `set-*` Parameter, another set Operator, or a
// Recordset/Subcategory selection coerced to its Scalar Set (see §13). Whether
// an Operand is a valid set is decided by semantic analysis, not by the grammar.
setExpression:
    setOperand                                                              #setLiteralExpr
    | SET_OF LPAREN op=expression RPAREN                                     #setOfExpr
    | UNION LPAREN expression (COMMA expression)+ RPAREN                     #unionSetExpr
    | INTERSECT LPAREN expression (COMMA expression)+ RPAREN                 #intersectSetExpr
    | SETDIFF LPAREN left=expression COMMA right=expression RPAREN           #setdiffSetExpr
    | SYMDIFF LPAREN left=expression COMMA right=expression RPAREN           #symdiffSetExpr
    ;

functions:
    aggregateOperators                                              #aggregateFunctions
    | numericOperators                                              #numericFunctions
    | comparisonFunctionOperators                                   #comparisonFunctions
    | filterOperators                                               #filterFunctions
    | conditionalOperators                                          #conditionalFunctions
    | timeOperators                                                 #timeFunctions
    | stringOperators                                               #stringFunctions
;

numericOperators:
    op=(ABS|EXP|LN|SQRT) LPAREN expression RPAREN                                 #unaryNumericFunctions
    | op=(POWER|LOG) LPAREN left=expression COMMA right=expression RPAREN         #binaryNumericFunctions
    | op=(MAX|MIN) LPAREN expression (COMMA expression)+ RPAREN                   #complexNumericFunctions
    ;

comparisonFunctionOperators:
    MATCH LPAREN expression COMMA literal RPAREN                    #matchExpr
    | ISNULL LPAREN expression RPAREN                               #isnullExpr
;

filterOperators:
    FILTER LPAREN expression COMMA expression RPAREN
    ;

timeOperators:
    TIME_SHIFT LPAREN expression COMMA TIME_PERIOD COMMA expression (COMMA propertyCode)? RPAREN #timeShiftFunction
    | ANNUALISE LPAREN expression COMMA expression COMMA propertyCode RPAREN                     #annualiseFunction
    | op=(YEAR|SEMESTER|QUARTER|MONTH|WEEK|DAY) LPAREN expression RPAREN                        #dateExtractFunction
    | DATE LPAREN year=expression COMMA month=expression COMMA day=expression RPAREN            #dateConstructorFunction
    ;

conditionalOperators:
    NVL LPAREN expression COMMA expression RPAREN           #nvlFunction
    ;

stringOperators:
    LEN LPAREN expression RPAREN                                              #unaryStringFunction
    | SUBSTR LPAREN expression (COMMA INTEGER_LITERAL (COMMA INTEGER_LITERAL)?)? RPAREN #substrFunction
    ;

aggregateOperators:
    op=(MAX_AGGR
        |MIN_AGGR
        |SUM
        |COUNT
        |AVG
        |MEDIAN) LPAREN expression (groupingClause | analyticClause)? RPAREN   #commonAggrOp
    | RANK LPAREN expression analyticClause RPAREN                              #rankOp
    ;

groupingClause:
    GROUP_BY keyNames (COMMA keyNames)*
;

// Analytical (windowing) invocation — mutually exclusive with groupingClause.
analyticClause:
    OVER LPAREN partitionClause? orderClause? windowClause? RPAREN
;

partitionClause:
    PARTITION_BY keyNames (COMMA keyNames)*
;

orderClause:
    ORDER_BY orderItem (COMMA orderItem)*
;

orderItem:
    keyNames (ASC | DESC)?
;

windowClause:
    (DATA_POINTS | RANGE) BETWEEN windowBoundary AND windowBoundary
;

windowBoundary:
    UNBOUNDED PRECEDING
    | UNBOUNDED FOLLOWING
    | CURRENT_DATA_POINT
    | INTEGER_LITERAL PRECEDING
    | INTEGER_LITERAL FOLLOWING
;

// Dimension management and members
itemSignature: ITEM_SIGNATURE;
itemReference: SQUARE_BRACKET_LEFT itemSignature SQUARE_BRACKET_RIGHT;

// Cell Address and table management
rowElem:
    ROW
    | ROW_RANGE
    | ROW_ALL
;
colElem:
    COL
    | COL_RANGE
    | COL_ALL
;
sheetElem:
    SHEET
    | SHEET_RANGE
    | SHEET_ALL
;
rowHandler:
    rowElem
    | LPAREN ROW (COMMA ROW)* RPAREN;

colHandler:
    colElem
    | LPAREN COL (COMMA COL)* RPAREN;

sheetHandler:
    sheetElem
    | LPAREN SHEET (COMMA SHEET)* RPAREN
;

interval:
    INTERVAL COLON BOOLEAN_LITERAL
;

default:
    DEFAULT COLON literal
    | DEFAULT COLON NULL_LITERAL
    | DEFAULT COLON itemReference
    | DEFAULT COLON setOperand
;

argument:
    rowHandler                          #rowArg
    | colHandler                        #colArg
    | sheetHandler                      #sheetArg
    | interval                          #intervalArg
    | default                           #defaultArg
;

select:
    CURLY_BRACKET_LEFT selectOperand CURLY_BRACKET_RIGHT
    ;

selectOperand:
    cellRef
    | varRef
    | operationRef
    | parameterRef
    ;

parameterRef:
    PARAMETER_REFERENCE COMMA parameterType (COMMA default)?
    ;

parameterType:
    NUMBER | INTEGER | STRING | PARAM_DATE | BOOLEAN | ITEM
    | SET_NUMBER | SET_INTEGER | SET_STRING | SET_DATE | SET_BOOLEAN | SET_ITEM
    ;

varID:
    CURLY_BRACKET_LEFT varRef CURLY_BRACKET_RIGHT
    ;

cellRef:
    address=cellAddress
    ;

varRef:
    VAR_REFERENCE
    ;

operationRef:
    OPERATION_REFERENCE
    ;

cellAddress:
    tableReference (COMMA argument)*                        #tableRef
    | operationRef COMMA argument (COMMA argument)*         #opRef
    | argument (COMMA argument)*                            #compRef;

tableReference:
    TABLE_REFERENCE
    | TABLE_GROUP_REFERENCE
    ;

clauseOperators:
    WHERE expression                                             #whereExpr
    | GET keyNames                                               #getExpr
    | RENAME renameClause (COMMA renameClause)*                  #renameExpr
    | SUB subAssignment (COMMA subAssignment)*                   #subExpr
    ;

// Always on grammar, not on tokens. Order is important (top ones should be the enclosing ones)

subAssignment:
    propertyCode EQ (literal | select | itemReference)
    ;

renameClause:
    propertyCode TO propertyCode
    ;

comparisonOperators:
    EQ
    |NE
    |GT
    |LT
    |GE
    |LE;

literal:
    INTEGER_LITERAL
    | DECIMAL_LITERAL
    | PERCENT_LITERAL
    | STRING_LITERAL
    | BOOLEAN_LITERAL
    | DATE_LITERAL
    | EMPTY_LITERAL
;

keyNames:
    ROW_COMPONENT
    | COL_COMPONENT
    | SHEET_COMPONENT
    | PROPERTY_CODE
    | ESCAPED_IDENTIFIER
;

propertyReference:
    SQUARE_BRACKET_LEFT propertyCode SQUARE_BRACKET_RIGHT;

propertyCode:
    PROPERTY_CODE
    | CODE
    | ESCAPED_IDENTIFIER
    ;

temporaryIdentifier:
    CODE
    | ESCAPED_IDENTIFIER
    ;