"""Exception classes for dpmcore."""

from typing import Any, Dict, Optional, cast


class DpmCoreError(Exception):
    """Base exception for all dpmcore errors.

    Attributes:
        title: Short error summary.
        description: Detailed explanation.
        csi: Contextual supplementary information.
    """

    def __init__(
        self,
        title: str,
        description: Optional[str] = None,
        csi: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialise a DpmCoreError.

        Args:
            title: Short error summary.
            description: Detailed explanation.
            csi: Contextual supplementary information.
        """
        self.title = title
        self.description = description
        self.csi = csi
        msg = f"{title}: {description}" if description else title
        super().__init__(msg)


class Invalid(DpmCoreError):
    """Bad request or invalid input."""


class NotFound(DpmCoreError):
    """Requested resource does not exist."""


class InternalError(DpmCoreError):
    """Internal processing error."""


class ConfigurationError(DpmCoreError):
    """Invalid or missing configuration."""


class SyntaxValidationError(DpmCoreError):
    """DPM-XL syntax validation failure."""


class SemanticValidationError(DpmCoreError):
    """DPM-XL semantic validation failure."""


class MigrationError(DpmCoreError):
    """Database migration failure."""


# -----------------------------------------------------------
# DPM-XL Engine Exceptions (code-based message formatting)
# -----------------------------------------------------------

centralised_messages: Dict[str, str] = {
    # Syntax errors
    "0-1": ("For match operator, provided regex has syntax errors: {message}"),
    "0-2": (
        "Cannot specify {argument} more than one"
        " time in the same cell reference."
    ),
    "0-3": ("Cannot use null literal, you must use the isnull function"),
    # Variable not found
    "1-1": "The following items were not found: {items}.",
    "1-2": ("Cell expression {cell_expression} was not found."),
    "1-3": "Variable {variable} was not found.",
    "1-4": "Table {table} was not found.",
    "1-5": ("The following open keys were not found: {open_keys}."),
    "1-6": "Table group {table_group} not found.",
    "1-7": (
        "Property signature {property_code} associated"
        " with the property constraint cannot be found."
    ),
    "1-8": ("The following operations {operations} were not found."),
    "1-9": ("Previous operation: {operation_code} was not found"),
    "1-10": (
        "Can't be analyzed an expression with table"
        " groups. Table reference {table} is defined"
        " as table group."
    ),
    "1-11": ("Category with code: {category_code} was not found"),
    "1-12": ("Subcategory with code: {subcategory_code} was not found"),
    "1-13": (
        "No module versions found for table versions: {table_version_ids}."
    ),
    "1-14": (
        "No module versions found for preconditions"
        " items: {precondition_items}."
    ),
    "1-15": ("Subcategory with id: {subcategory_id} was not found"),
    "1-16": ("Category with id: {category_id} was not found"),
    "1-17": ("Grey cells {cell_expression} were found."),
    "1-18": (
        "Found explicit s* on the expression, but no"
        " sheets for the cells were found for the"
        " operand(s)."
    ),
    "1-19": (
        "Found explicit r* on the expression, but no"
        " rows for the cells were found for the"
        " operand(s)."
    ),
    "1-20": ("Missing explicit {header} on the expression for table {table}"),
    "1-21": "Release {release_id} was not found.",
    # Structures
    "2-1": (
        "If preconditions are involved the result has to be a boolean scalar."
    ),
    "2-2": (
        "This operation is not allowed, because there"
        " is no match between DPM components."
        " Operator={op} left={left}, right={right}."
    ),
    "2-3": (
        "Structures are different (or types on key"
        " components) for this operator {op} between"
        " {structure_1} and {structure_2}."
        " Please check {origin}."
    ),
    "2-4": (
        "For this operator {op} this component {name}"
        " is not present in both structures."
        " Please check {origin}."
    ),
    "2-5": (
        "For this component {name} types are different"
        " for this operator {op} found {type_1} and"
        " {type_2}.Please check {origin}."
    ),
    "2-6": (
        "In RecordSet: {name}, standard keys: {keys}"
        " with values {values} are duplicated."
    ),
    "2-7": ("Component creation for {component_name} was not possible."),
    "2-8": (
        "At op {op}: Key components {dpm_keys}"
        " not found on recordset {recordset}."
    ),
    "2-9": (
        "At op {op}: Found different number of"
        " headers on left and right hand side."
    ),
    # Data types
    "3-1": (
        "Implicit cast is not available between"
        " {type_1} and {type_2}."
        "Please check {origin}."
    ),
    "3-2": (
        "Types are wrong, type_op_1={type_1},"
        "type_op_2={type_2}, operator works for"
        " {type_op}.Please check {origin}."
    ),
    "3-3": (
        "Types are wrong, type_op_1={type_1},"
        " operator works for {type_op}."
        "Please check {origin}."
    ),
    "3-4": ("Interval can't be used for this operand_type={operand_type}"),
    "3-5": ("Interval can't be used for this operator.Please check {origin}."),
    "3-6": (
        "Invalid default type, default is a"
        " {default_type} but it has to be a"
        " {expected_type}."
    ),
    # Operators
    # - Aggregate Operators
    "4-4-0-1": (
        "Only a Recordset is allowed in the Aggregation operator {op}."
    ),
    "4-4-0-2": (
        "Grouping components {not_present} are not present in key components"
    ),
    "4-4-0-3": (
        "Mixed type can't be used in aggregation. Please check {origin}."
    ),
    # - Clause Operators
    "4-5-0-1": (
        "On recordset {recordset}: clause operators"
        " can't be used with standard key components"
        " or fact component."
    ),
    "4-5-0-2": (
        "In {operator} operator only operands of recordset type are supported."
    ),
    # -- Rename
    "4-5-1-1": (
        "For rename operator component names: {names}"
        " already exists on recordset {recordset}."
    ),
    "4-5-1-2": ("Duplicated new names after rename operator: {duplicated}."),
    "4-5-1-3": (
        "For rename operator, new names can't be"
        " standard key names or indexes names(x,y,z)"
        " on recordset: {recordset}"
    ),
    "4-5-1-4": (
        "For rename operator, key component"
        " {component} not found on recordset:"
        " {recordset} because it has already"
        " been renamed."
    ),
    # -- Where
    "4-5-2-1": (
        "Invalid clause for where operator, at least"
        " one dpm key component of recordset"
        " {recordset} must be used."
    ),
    "4-5-2-2": (
        "For where operator, operand {operand} and"
        " condition {condition} must have the same"
        " structure or condition must be a subset"
        " of selection."
    ),
    # - Conditional Operators
    "4-6-0-1": (
        "For Conditional operators DPM components"
        " have to have the same records."
    ),
    "4-6-0-2": (
        "For conditional operators, condition"
        " {condition} and operand/selection {operand}"
        " must have the same structure or one must"
        " be a subset of the other"
    ),
    # -- if then else
    "4-6-1-1": ("Error for the condition in if then else operator"),
    "4-6-1-3": (
        "For if then else operator, then and else"
        " have to be both recordset or both scalars,"
        " if the condition is a scalar."
    ),
    # -- nvl
    "4-6-2-1": (
        "Invalid input structures for Nvl operator,"
        " right op has to be scalar too."
    ),
    # -- filter
    "4-6-3-1": (
        "Filter operator only supports recordset as selection and condition"
    ),
    # - Time Operators
    "4-7-1": ("Only a Recordset or a scalar is allowed for {op} operator."),
    "4-7-2": (
        "For time_shift operator, only var component"
        " is allowed when operand is a recordset"
    ),
    "4-7-3": (
        "For time_shift operator, var component must"
        " be specified when operand is a recordset"
    ),
    # Generation of validations
    "5-0-1": ("This expression doesn't generate any correct validation."),
    "5-0-2": ("This expression can't be used for the generation of children."),
    # - Properties constraints
    "5-1-1": "No properties constraints were found.",
    "5-1-2": (
        "In an expression defined on properties"
        " constraints only there can be one"
        " property constraint."
    ),
    "5-1-3": (
        "Operator '{operator}' not allowed in an"
        " expression defined on properties"
        " constraints."
    ),
    "5-1-4": ("Property with signature {ref} was not found."),
    # - Variants
    "5-2-1": ("The supplied expression does not contain any table group."),
    # - Sign validations
    "5-3-1": (
        "Table version id {table_version_id} does"
        " not exist or does not have associated"
        " cells."
    ),
    # Scripting
    "6-1": (
        "Overwriting a variable is not allowed, trying it with {variable}."
    ),
    "6-2": (
        "References to operations are not allowed in"
        " single expressions, trying it with"
        " {operation_code}."
    ),
    "6-3": (
        "Preconditions are not allowed in scripting,"
        " trying it with {precondition}."
    ),
    "6-4": (
        "Circular reference between operations"
        " {op1} and {op2}. Try removing or changing"
        " these references."
    ),
    # Other errors
    "7-1": (
        "Found a Property Reference in a regular"
        " validation. Please check Operation Source"
        " to use Property Constraint."
    ),
    "7-2": ("Found a Variable Reference, please check expression"),
}


class DrrException(DpmCoreError):
    """Base DPM-XL engine exception with position info.

    Attributes:
        lino: Line number in source expression.
        colno: Column number in source expression.
        code: Error code from centralised_messages.
    """

    def __init__(
        self,
        message: str,
        lino: Optional[int] = None,
        colno: Optional[int] = None,
        code: Optional[str] = None,
    ) -> None:
        """Initialise a DrrException.

        Args:
            message: Human-readable error message.
            lino: Line number in source expression.
            colno: Column number in source expression.
            code: Error code from centralised_messages.
        """
        self.lino = lino
        self.colno = colno
        self.code = code
        super().__init__(title=message)

    @property
    def pos(self) -> list[Optional[int]]:
        """Return ``[line, column]`` position."""
        return [self.lino, self.colno]


def _gather_expression(operand: str) -> str:
    """Resolve operand labels in an expression string.

    Args:
        operand: Raw operand string.

    Returns:
        Resolved expression with labels substituted.
    """
    from dpmcore.dpm_xl.utils.operands_mapping import (
        LabelHandler,
    )

    operands_labels = LabelHandler().operands_labels
    expression = operand
    for key in operands_labels.__reversed__():
        if key in expression:
            expression = expression.replace(
                key, cast(str, operands_labels[key])
            )
    return expression


class SyntaxError_(DrrException):
    """DPM-XL syntax error with centralised message.

    Uses error codes from ``centralised_messages`` to
    produce human-readable messages.
    """

    def __init__(self, code: str, **kwargs: Any) -> None:
        """Initialise a SyntaxError.

        Args:
            code: Message code from centralised_messages.
            **kwargs: Formatting arguments for the message.
        """
        message = centralised_messages[code].format(**kwargs)
        super().__init__(message, None, None, code)


class SemanticError(DrrException):
    """DPM-XL semantic error with operand label resolution.

    Resolves operand labels in the formatted message so
    that generated sub-expressions are shown in context.
    """

    def __init__(self, code: str, **kwargs: Any) -> None:
        """Initialise a SemanticError.

        Args:
            code: Message code from centralised_messages.
            **kwargs: Formatting arguments for the message.
        """
        from dpmcore.dpm_xl.utils.operands_mapping import (
            LabelHandler,
            get_type_from_label,
        )

        operands_labels = LabelHandler().operands_labels
        message = centralised_messages[code].format(**kwargs)
        for operand in reversed(operands_labels):
            if operand in message:
                generated = _gather_expression(operand)
                not_single = get_type_from_label(operand) == "not_single"
                if not_single:
                    message = message.replace(
                        operand,
                        f"GENERATED:' {generated} '",
                    )
                else:
                    message = message.replace(operand, generated)
        super().__init__(message, None, None, code)


class DataTypeError(Exception):
    """Invalid scalar value for a DPM data type."""

    def __init__(self, value: Any, data_type: str) -> None:
        """Initialise a DataTypeError.

        Args:
            value: The invalid value.
            data_type: Expected data type name.
        """
        super().__init__(
            f"Invalid Scalar value '{value}' for data type {data_type}."
        )


class ScriptingError(DrrException):
    """DPM-XL scripting error with centralised message."""

    def __init__(self, code: str, **kwargs: Any) -> None:
        """Initialise a ScriptingError.

        Args:
            code: Message code from centralised_messages.
            **kwargs: Formatting arguments for the message.
        """
        message = centralised_messages[code].format(**kwargs)
        super().__init__(message, None, None, code)
