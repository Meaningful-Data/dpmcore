from dpmcore.dpm_xl.types.scalar import (
    Boolean,
    Date,
    Duration,
    Integer,
    Item,
    Mixed,
    Null,
    Number,
    ScalarType,
    String,
    Subcategory,
    TimeInterval,
    TimePeriod,
)
from dpmcore.dpm_xl.warning_collector import add_semantic_warning
from dpmcore.errors import SemanticError

implicit_type_promotion_dict = {
    String: {String},
    Number: {String, Number},
    Integer: {String, Number, Integer},
    TimeInterval: {String, TimeInterval},
    Date: {String, TimeInterval, Date},
    TimePeriod: {String, TimeInterval, TimePeriod},
    Duration: {String, Duration},
    Boolean: {String, Boolean},
    Item: {String, Item},
    Subcategory: {String, Subcategory},
    Null: {
        String,
        Number,
        Integer,
        TimeInterval,
        Date,
        TimePeriod,
        Duration,
        Boolean,
        Item,
        Subcategory,
        Null,
    },
}


def binary_implicit_type_promotion(
    left: ScalarType,
    right: ScalarType,
    op_type_to_check: ScalarType = None,
    return_type: ScalarType = None,
    interval_allowed: bool = True,
    error_info: dict = None,
):
    """ """
    left_implicities = implicit_type_promotion_dict[left.__class__]
    right_implicities = implicit_type_promotion_dict[right.__class__]

    if left and right:
        warning_raising = not (
            isinstance(left, type(right)) or isinstance(right, type(left))
        )
    else:
        warning_raising = False

    if op_type_to_check:
        if op_type_to_check.is_included(
            left_implicities.intersection(right_implicities)
        ):  # general case and date->str and boolean-> str in the str operator
            if warning_raising:
                if error_info:
                    add_semantic_warning(
                        f"Implicit promotion between {left} and {right} in: "
                        f"{error_info['left_name']} {error_info['op']} {error_info['right_name']}"
                    )
                else:
                    add_semantic_warning(
                        f"Implicit promotion between {left} and {right}."
                    )
            if return_type:
                binary_check_interval(
                    result_operand=return_type,
                    left_operand=left,
                    right_operand=right,
                    op_type_to_check=op_type_to_check,
                    return_type=return_type,
                    interval_allowed=interval_allowed,
                    error_info=error_info,
                )
                return return_type

            if not left.is_null_type() and left.is_included(right_implicities):
                binary_check_interval(
                    result_operand=left,
                    left_operand=left,
                    right_operand=right,
                    op_type_to_check=op_type_to_check,
                    return_type=return_type,
                    interval_allowed=interval_allowed,
                    error_info=error_info,
                )
                return left
            elif not right.is_null_type() and right.is_included(
                left_implicities
            ):
                binary_check_interval(
                    result_operand=right,
                    left_operand=left,
                    right_operand=right,
                    op_type_to_check=op_type_to_check,
                    return_type=return_type,
                    interval_allowed=interval_allowed,
                    error_info=error_info,
                )
                return right
            else:
                if isinstance(op_type_to_check, Number):
                    binary_check_interval(
                        result_operand=op_type_to_check,
                        left_operand=left,
                        right_operand=right,
                        op_type_to_check=op_type_to_check,
                        return_type=return_type,
                        interval_allowed=interval_allowed,
                        error_info=error_info,
                    )
                return op_type_to_check

        else:
            origin = (
                None
                if error_info is None
                else "operator={operator} {left} {right}".format(
                    left=error_info["left_name"],
                    operator=error_info["op"],
                    right=error_info["right_name"],
                )
            )
            raise SemanticError(
                "3-2",
                type_1=left,
                type_2=right,
                type_op=op_type_to_check,
                origin=origin,
            )
    else:
        if warning_raising:
            if error_info:
                add_semantic_warning(
                    f"Implicit promotion between {left} and {right} in: "
                    f"{error_info['left_name']} {error_info['op']} {error_info['right_name']}"
                )
            else:
                add_semantic_warning(
                    f"Implicit promotion between {left} and {right}."
                )
        if return_type and (
            left.is_included(right_implicities)
            or right.is_included(left_implicities)
        ):
            return return_type
        elif left.is_included(right_implicities):
            return left
        elif right.is_included(left_implicities):
            return right
        else:
            origin = (
                None
                if error_info is None
                else "operator={operator} {left} {right}".format(
                    left=error_info["left_name"],
                    operator=error_info["op"],
                    right=error_info["right_name"],
                )
            )
            raise SemanticError(
                "3-1", type_1=left, type_2=right, origin=origin
            )


def binary_implicit_type_promotion_with_mixed_types(
    result_dataframe,
    left_type,
    right_type,
    op_type_to_check=None,
    return_type=None,
    interval_allowed: bool = False,
    error_info=None,
):
    """ """

    if result_dataframe.empty:
        return Mixed(), result_dataframe

    # If there is not a data_type column, result_dataframe is the result of merging two recordsets
    if "data_type" not in result_dataframe.columns:
        result_dataframe["data_type"] = result_dataframe.apply(
            lambda x: binary_implicit_type_promotion(
                x["data_type_left"],
                x["data_type_right"],
                op_type_to_check,
                return_type,
                interval_allowed,
                error_info,
            ),
            axis=1,
        )

        result_dataframe = result_dataframe.drop(
            columns=["data_type_left", "data_type_right"]
        )

    elif isinstance(left_type, Mixed):
        result_dataframe["data_type"] = result_dataframe["data_type"].apply(
            lambda x: binary_implicit_type_promotion(
                x,
                right_type,
                op_type_to_check,
                return_type,
                interval_allowed,
                error_info,
            )
        )

    elif isinstance(right_type, Mixed):
        result_dataframe["data_type"] = result_dataframe["data_type"].apply(
            lambda x: binary_implicit_type_promotion(
                left_type,
                x,
                op_type_to_check,
                return_type,
                interval_allowed,
                error_info,
            )
        )

    if return_type:
        return return_type, result_dataframe
    return Mixed(), result_dataframe


def unary_implicit_type_promotion(
    operand: ScalarType,
    op_type_to_check: ScalarType = None,
    return_type: ScalarType = None,
    interval_allowed: bool = True,
    error_info: dict = None,
):
    """ """

    operand_implicities = implicit_type_promotion_dict[operand.__class__]

    unary_check_interval(
        operand=operand,
        op_type_to_check=op_type_to_check,
        return_type=return_type,
        interval_allowed=interval_allowed,
        error_info=error_info,
    )

    if op_type_to_check:
        if not op_type_to_check.is_included(operand_implicities):
            origin = (
                None
                if error_info is None
                else "{}({})".format(
                    error_info["op"], error_info["operand_name"]
                )
            )
            raise SemanticError(
                "3-3", type_1=operand, type_op=op_type_to_check, origin=origin
            )

    if return_type:
        return return_type
    if op_type_to_check and not operand.is_subtype(op_type_to_check):
        return op_type_to_check
    return operand


def unary_implicit_type_promotion_with_mixed_types(
    operand_dataframe,
    op_type_to_check=None,
    return_type=None,
    interval_allowed=None,
    error_info=None,
):
    """ """

    if operand_dataframe.empty:
        return Mixed(), operand_dataframe

    operand_dataframe["data_type"] = operand_dataframe["data_type"].apply(
        lambda x: unary_implicit_type_promotion(
            x,
            op_type_to_check,
            return_type,
            interval_allowed=interval_allowed,
            error_info=error_info,
        )
    )

    if return_type:
        return return_type, operand_dataframe
    return Mixed(), operand_dataframe


def check_operator(
    return_type: ScalarType = None, op_check_type: ScalarType = None
):
    """ """
    if return_type is None or op_check_type is None:
        return True

    op_check_type_implicities = implicit_type_promotion_dict[
        op_check_type.__class__
    ]

    return bool(return_type.is_included(op_check_type_implicities))


def unary_check_interval(
    operand: ScalarType,
    op_type_to_check: ScalarType = None,
    return_type: ScalarType = None,
    interval_allowed: bool = False,
    error_info: dict = None,
):
    if interval_allowed and getattr(operand, "interval", None):
        if return_type and isinstance(return_type, Integer):
            return None
        if return_type and isinstance(return_type, Number):
            return_type.set_interval(operand.interval)
        if op_type_to_check and isinstance(op_type_to_check, Number):
            op_type_to_check.set_interval(operand.interval)
    elif not interval_allowed and getattr(operand, "interval", None):
        origin = (
            None
            if error_info is None
            else "{}({})".format(error_info["op"], error_info["operand_name"])
        )
        raise SemanticError("3-5", origin=origin)
    else:
        return None


def binary_check_interval(
    result_operand: ScalarType = None,
    left_operand: ScalarType = None,
    right_operand: ScalarType = None,
    op_type_to_check: ScalarType = None,
    return_type: ScalarType = None,
    interval_allowed: bool = False,
    error_info: dict = None,
):
    """ """
    if op_type_to_check is None:
        return None
    if return_type and isinstance(return_type, Integer):
        return None
    if isinstance(result_operand, Number):
        interval = getattr(left_operand, "interval", None) or getattr(
            right_operand, "interval", None
        )
        if interval and not interval_allowed:
            origin = (
                None
                if error_info is None
                else "{}({})".format(
                    error_info["op"], error_info["operand_name"]
                )
            )
            raise SemanticError("3-5", origin=origin)
        result_operand.set_interval(interval)
