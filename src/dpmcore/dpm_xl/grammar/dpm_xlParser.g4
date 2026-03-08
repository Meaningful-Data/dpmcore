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
    varID PERSISTENT_ASSIGN expressionWithoutAssignment
    ;

expression:
    LPAREN expression RPAREN                                                                            #parExpr
    | functions                                                                                         #funcExpr
    | expression SQUARE_BRACKET_LEFT clauseOperators SQUARE_BRACKET_RIGHT                               #clauseExpr
    | op=(PLUS|MINUS) expression                                                                        #unaryExpr
    | op=NOT LPAREN expression RPAREN                                                                   #notExpr
    | left=expression op=(MULT|DIV) right=expression                                                    #numericExpr
    | left=expression op=(PLUS|MINUS) right=expression                                                  #numericExpr
    | left=expression op=CONCAT right=expression                                                        #concatExpr
    | left=expression op=comparisonOperators right=expression                                           #compExpr
    | left=expression op=IN setOperand                                                                  #inExpr
    | left=expression op=AND right=expression                                                           #boolExpr
    | left=expression op=(OR|XOR) right=expression                                                      #boolExpr
    | IF conditionalExpr=expression THEN thenExpr=expression (ELSE elseExpr=expression)? ENDIF          #ifExpr
    | itemReference                                                                                     #itemReferenceExpr
    | propertyReference                                                                                 #propertyReferenceExpr
    | keyNames                                                                                          #keyNamesExpr
    | literal                                                                                           #literalExpr
    | select                                                                                            #selectExpr
    ;

setOperand:
    CURLY_BRACKET_LEFT setElements CURLY_BRACKET_RIGHT
    ;

setElements:
    itemReference (COMMA itemReference)*
    | literal (COMMA literal)*
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
    TIME_SHIFT LPAREN expression COMMA TIME_PERIOD COMMA INTEGER_LITERAL (COMMA propertyCode)? RPAREN #timeShiftFunction
    ;

conditionalOperators:
    NVL LPAREN expression COMMA expression RPAREN           #nvlFunction
    ;

stringOperators:
    LEN LPAREN expression RPAREN          #unaryStringFunction
    ;

aggregateOperators:
    op=(MAX_AGGR
        |MIN_AGGR
        |SUM
        |COUNT
        |AVG
        |MEDIAN) LPAREN expression (groupingClause)? RPAREN        #commonAggrOp
    ;

groupingClause:
    GROUP_BY keyNames (COMMA keyNames)*
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
    | preconditionElem
    ;

varID:
    CURLY_BRACKET_LEFT varRef CURLY_BRACKET_RIGHT
    ;

cellRef:
    address=cellAddress
    ;

preconditionElem:
    PRECONDITION_ELEMENT
    ;

varRef:
    VAR_REFERENCE
    ;

operationRef:
    OPERATION_REFERENCE
    ;

cellAddress:
    tableReference (COMMA argument)*               #tableRef
    | argument (COMMA argument)*                   #compRef;

tableReference:
    TABLE_REFERENCE
    | TABLE_GROUP_REFERENCE
    ;

clauseOperators:
    WHERE expression                                             #whereExpr
    | GET keyNames                                               #getExpr
    | RENAME renameClause (COMMA renameClause)*                  #renameExpr
    | SUB propertyCode EQ (literal | select | itemReference)     #subExpr
    ;

// Always on grammar, not on tokens. Order is important (top ones should be the enclosing ones)

renameClause:
    keyNames TO keyNames
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
    | TIME_INTERVAL_LITERAL
    | TIME_PERIOD_LITERAL
    | EMPTY_LITERAL
;

keyNames:
    ROW_COMPONENT
    | COL_COMPONENT
    | SHEET_COMPONENT
    | PROPERTY_CODE
;

propertyReference:
    SQUARE_BRACKET_LEFT propertyCode SQUARE_BRACKET_RIGHT;

propertyCode:
    PROPERTY_CODE
    | CODE
    ;

temporaryIdentifier:
    CODE
    ;