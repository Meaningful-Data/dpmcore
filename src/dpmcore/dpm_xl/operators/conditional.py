from typing import ClassVar, Union

import pandas as pd

from dpmcore import errors
from dpmcore.dpm_xl.operators.base import Binary, Operator
from dpmcore.dpm_xl.symbols import (
    ConstantOperand,
    Operand,
    RecordSet,
    Scalar,
    Structure,
)
from dpmcore.dpm_xl.types.promotion import (
    binary_implicit_type_promotion,
    binary_implicit_type_promotion_with_mixed_types,
    unary_implicit_type_promotion,
)
from dpmcore.dpm_xl.types.scalar import (
    Mixed,
    Null,
    ScalarFactory,
    ScalarType,
)
from dpmcore.dpm_xl.utils import tokens
from dpmcore.dpm_xl.warning_collector import add_semantic_warning
from dpmcore.errors import SemanticError

# Type aliases used throughout the conditional operators pipeline.
CondOperand = Union[RecordSet, Scalar]


class ConditionalOperator(Operator):
    propagate_attributes: ClassVar[bool] = False

    @classmethod
    def validate(cls, *args: object) -> None:
        # Abstract-ish placeholder; concrete subclasses override with their
        # own signatures. Kept for runtime parity.
        pass

    @classmethod
    def create_labeled_scalar(
        cls,
        rslt_structure: CondOperand | ConstantOperand,
        rslt_type: ScalarType,
        origin: str,
    ) -> Scalar:
        """ """
        if not isinstance(rslt_structure, ConstantOperand):
            scalar = cls._create_labeled_scalar(
                origin=origin, result_type=rslt_type
            )
            return scalar
        else:
            value = rslt_structure.value
            return ConstantOperand(
                type_=ScalarFactory().scalar_factory(str(rslt_type)),
                name=None,
                origin=origin,
                value=value,
            )

    @classmethod
    def _check_combinable_operand(cls, operand: Operand, code: str) -> None:
        """Reject an operand the conditional operators cannot combine.

        The grammar accepts any expression wherever these operators take
        an operand, so a set — the operand shape of ``in`` — reaches them
        as a ``ScalarSet``, and §8.1.5 and §8.2.2 both admit ``rset`` and
        ``scal`` only. A set used to be silently dropped (the other
        operand's structure became the result), to break the analysis with
        an ``AttributeError``, or to fall through the structure check to a
        bare ``Exception``.
        """
        if not isinstance(operand, (RecordSet, Scalar)):
            name = getattr(operand, "name", None) or operand.origin
            raise SemanticError(code, operand=name)

    @classmethod
    def _check_same_recordset_structures(
        cls, left: RecordSet, right: RecordSet, origin: str
    ) -> bool:
        """Used for recordset-recordset."""
        left_structure = left.structure
        right_structure = right.structure
        if len(left_structure.get_key_components()) == len(
            right_structure.get_key_components()
        ):
            # For better error management
            class_check = Binary()
            # Binary.op is a ClassVar; overriding on the instance preserves
            # existing runtime behavior of piping cls.op into downstream
            # errors.
            class_check.op = cls.op  # type: ignore[misc]
            class_check.check_same_components(
                left_structure, right_structure, origin
            )
            return True
        return False

    @classmethod
    def _check_structures(
        cls,
        left: RecordSet,
        right: RecordSet,
        origin: str,
        subset_allowed: bool = True,
    ) -> bool:
        """Used for recordset-recordset."""
        left_records = left.records
        right_records = right.records
        if cls._check_same_recordset_structures(left, right, origin):
            # validation for records
            if left_records is not None and right_records is not None:
                result_dataframe = pd.merge(
                    left_records,
                    right_records,
                    on=[
                        col
                        for col in left_records.columns
                        if col != "data_type"
                    ],
                )
                if len(result_dataframe) != len(left_records):
                    raise SemanticError("4-6-0-1")

            return True

        if subset_allowed:
            # operand_is_subset = cls.check_condition_is_subset(selection=left, condition=right)
            operand_is_subset = cls.check_condition_is_subset(
                selection=right, condition=left
            )
            if cls.op in (tokens.NVL, tokens.IF):
                operand_is_subset = cls.check_condition_is_subset(
                    selection=right, condition=left
                )
            else:
                operand_is_subset = cls.check_condition_is_subset(
                    selection=left, condition=right
                )
            if operand_is_subset:
                return True
            raise errors.SemanticError(
                "4-6-0-2", condition=left.name, operand=right.name
            )

        raise SemanticError(
            "2-3",
            op=cls.op,
            structure_1=left.get_key_components_names(),
            structure_2=right.get_key_components_names(),
            origin=origin,
        )

    @classmethod
    def check_condition_is_subset(
        cls, selection: RecordSet, condition: RecordSet
    ) -> bool:

        selection_dpm_components = selection.get_dpm_components()
        condition_dpm_components = condition.get_dpm_components()

        if set(condition.get_key_components_names()) <= set(
            selection.get_key_components_names()
        ):
            for comp_key, comp_value in condition_dpm_components.items():
                if comp_key not in selection_dpm_components:
                    return False
                if (
                    comp_value.type.__class__
                    != selection_dpm_components[comp_key].type.__class__
                ):
                    return False
            return True
        return False

    @staticmethod
    def generate_result_dataframe(
        left: RecordSet, right: RecordSet
    ) -> pd.DataFrame | None:
        if left.records is not None and right.records is not None:
            result_dataframe = pd.merge(
                left.records,
                right.records,
                on=[
                    col for col in right.records.columns if col != "data_type"
                ],
                suffixes=("_left", "_right"),
            )

            result_dataframe["data_type"] = result_dataframe["data_type_left"]
            result_dataframe = result_dataframe.drop(
                columns=["data_type_left", "data_type_right"]
            )

            return result_dataframe

        return None


class IfOperator(ConditionalOperator):
    """ """

    op: ClassVar[str | None] = tokens.IF

    @classmethod
    def create_origin_expression(
        cls,
        condition: Operand,
        then_op: Operand,
        else_op: Operand | None = None,
    ) -> str:
        condition_name = getattr(condition, "name", None) or condition.origin
        then_name = getattr(then_op, "name", None) or then_op.origin
        if else_op:
            else_name = getattr(else_op, "name", None) or else_op.origin
            origin = f"If {condition_name} then {then_name} else {else_name}"
        else:
            origin = f"If {condition_name} then {then_name}"
        return origin

    @classmethod
    def check_condition(cls, condition: CondOperand) -> bool:
        """Check if the condition has Boolean type."""
        cls._check_combinable_operand(condition, "4-6-1-2")
        if isinstance(condition, RecordSet):
            condition_type = condition.structure.components["f"].type
        else:
            condition_type = condition.type
        # unary implicit promotion
        error_info = {"operand_name": condition.name, "op": cls.op}
        boolean_type = ScalarFactory().scalar_factory("Boolean")
        type_promotion = unary_implicit_type_promotion(
            operand=condition_type,
            op_type_to_check=boolean_type,
            error_info=error_info,
        )
        if type_promotion.strictly_same_class(boolean_type):
            return True

        raise SemanticError("4-6-1-1")

    @classmethod
    def _is_scalar_like(cls, operand: CondOperand) -> bool:
        """Whether *operand* carries one value per global key combination.

        Scalars and single-cell selections — recordsets whose key
        components are all global — are interchangeable as branches of the
        same ``if``: neither contributes a key component the other lacks.
        The specification reads them the same way, calling the comparison
        of a fully specified cell a "Scalar Boolean" (§8.1.7, example 5).
        """
        if isinstance(operand, RecordSet):
            return operand.has_only_global_components
        return True

    @classmethod
    def _is_null_literal(cls, operand: CondOperand) -> bool:
        """Whether *operand* is the ``null`` literal.

        The Null literal exception of §8.1.5: a null branch contributes no
        Record, so the other branch may carry key components the condition
        lacks without any Record of the result holding a null key value.
        An explicit ``else null`` reads as an omitted ``else``.
        """
        return isinstance(operand, Scalar) and isinstance(operand.type, Null)

    @classmethod
    def check_structures(
        cls,
        condition: CondOperand,
        first: CondOperand,
        second: CondOperand | None,
        origin: str,
    ) -> tuple[Structure | CondOperand, pd.DataFrame | None]:
        """ """
        cls._check_combinable_operand(first, "4-6-1-2")
        if second is not None:
            cls._check_combinable_operand(second, "4-6-1-2")
        if isinstance(condition, Scalar):
            return cls._scalar_condition_structures(first, second, origin)
        return cls._recordset_condition_structures(
            condition, first, second, origin
        )

    @classmethod
    def _scalar_condition_structures(
        cls,
        first: CondOperand,
        second: CondOperand | None,
        origin: str,
    ) -> tuple[Structure | CondOperand, pd.DataFrame | None]:
        """Result of an ``if`` whose condition is a scalar.

        A scalar condition has no key component of its own, so joining it
        with a branch leaves the branch's own key components, and the
        Matched join structure constraint of §8.1.5 reduces to: both
        branches carry the same key components. A scalar branch therefore
        cannot be paired with a recordset one — the case ``4-6-1-3`` has
        always covered (§8.1.7, example 5).
        """
        if second is None or cls._is_null_literal(second):
            return cls._single_branch_structure(first)
        if cls._is_null_literal(first):
            return cls._single_branch_structure(second)

        if isinstance(first, RecordSet) and isinstance(second, RecordSet):
            if cls._is_scalar_like(first) != cls._is_scalar_like(second):
                raise SemanticError("4-6-1-3")
            if cls._is_scalar_like(first):
                return first, None
            # Both branches carry standard key components, so their
            # structures have to be the same.
            cls._check_structures(first, second, origin, subset_allowed=False)
            return first.structure, first.records
        # At most one branch is a recordset, and it agrees with a scalar
        # branch only if it is a single cell contributing no key component.
        for branch in (first, second):
            if not cls._is_scalar_like(branch):
                raise SemanticError("4-6-1-3")
        return first, None

    @classmethod
    def _single_branch_structure(
        cls, branch: CondOperand
    ) -> tuple[Structure | CondOperand, pd.DataFrame | None]:
        """Result of a scalar-condition ``if`` with a single live branch."""
        if isinstance(branch, RecordSet) and not cls._is_scalar_like(branch):
            return branch.structure, branch.records
        return branch, None

    @classmethod
    def _recordset_condition_structures(
        cls,
        condition: RecordSet,
        first: CondOperand,
        second: CondOperand | None,
        origin: str,
    ) -> tuple[Structure | CondOperand, pd.DataFrame | None]:
        """Result of an ``if`` whose condition is a recordset.

        The condition is evaluated per record, so its own key components
        are part of the result even when both branches are scalars: a
        scalar branch is applied to every record of the condition (§8.1.7,
        example 3). Mixing a scalar branch with a recordset one is
        therefore allowed here (§8.1.7, example 6) — what §8.1.5 requires
        is that both branches, once joined with the condition, end up with
        the same key components (§8.1.7, example 8).
        """
        if second is None or cls._is_null_literal(second):
            return cls._branch_join(condition, first, origin)
        if cls._is_null_literal(first):
            return cls._branch_join(condition, second, origin)

        then_struct, then_records = cls._branch_join(condition, first, origin)
        else_struct, else_records = cls._branch_join(condition, second, origin)
        if set(then_struct.get_key_components_names()) != set(
            else_struct.get_key_components_names()
        ):
            raise SemanticError("4-6-1-3")

        # Both joins have the same key components, so either structure
        # describes the result; ``check_is_subset`` also rules out two
        # same-named key components of different types.
        is_sub, largest = Binary.check_is_subset(then_struct, else_struct)
        if not is_sub:
            raise SemanticError(
                "2-3",
                op=cls.op,
                structure_1=then_struct.get_key_components_names(),
                structure_2=else_struct.get_key_components_names(),
                origin=origin,
            )
        if largest is then_struct:
            return then_struct, then_records
        return else_struct, else_records

    @classmethod
    def _branch_join(
        cls, condition: RecordSet, branch: CondOperand, origin: str
    ) -> tuple[Structure, pd.DataFrame | None]:
        """Structure of ``join(condition, branch)``.

        A scalar branch adds no key component, so the join is the condition
        itself; a recordset branch has to be structurally compatible with
        the condition and contributes the larger of the two key component
        sets.
        """
        if isinstance(branch, RecordSet):
            return cls._check_if_structures(condition, branch, origin)
        return condition.structure, condition.records

    @classmethod
    def _check_if_structures(
        cls, condition: RecordSet, operand: RecordSet, origin: str
    ) -> tuple[Structure, pd.DataFrame | None]:
        """Bidirectional structure check for IF operator.
        Returns (result_structure, result_records) where result is the superset.
        """
        # Same structure: return condition's
        if cls._check_same_recordset_structures(condition, operand, origin):
            if condition.records is not None and operand.records is not None:
                result_df = pd.merge(
                    condition.records,
                    operand.records,
                    on=[
                        c
                        for c in condition.records.columns
                        if c != "data_type"
                    ],
                )
                if len(result_df) != len(condition.records):
                    raise SemanticError("4-6-0-1")
            return condition.structure, condition.records

        # Bidirectional subset check
        is_subset, superset = Binary.check_is_subset(
            condition.structure, operand.structure
        )
        if is_subset and superset is not None:
            if superset is condition.structure:
                return condition.structure, condition.records
            else:
                return operand.structure, operand.records

        raise SemanticError(
            "4-6-0-2", condition=condition.name, operand=operand.name
        )

    @classmethod
    def check_types(
        cls,
        first: CondOperand,
        result_dataframe: pd.DataFrame | None,
        second: CondOperand | None = None,
    ) -> tuple[ScalarType, pd.DataFrame | None]:
        first_type: ScalarType
        if second is not None:
            if isinstance(first, RecordSet):
                first_type = first.structure.components["f"].type
            else:
                first_type = first.type
            second_type: ScalarType
            if isinstance(second, RecordSet):
                second_type = second.structure.components["f"].type
            else:
                second_type = second.type
            if isinstance(first_type, Mixed) or isinstance(second_type, Mixed):
                if isinstance(first, RecordSet) and isinstance(
                    second, RecordSet
                ):
                    result_dataframe = cls.generate_result_dataframe(
                        first, second
                    )
        else:
            if isinstance(first, RecordSet):
                first_type = first.structure.components["f"].type
            else:
                first_type = first.type
            return first_type, result_dataframe

        if isinstance(first_type, Mixed) or isinstance(second_type, Mixed):
            if result_dataframe is None:
                raise Exception(
                    "Mixed type promotion requires a result dataframe"
                )
            type_promotion, result_dataframe = (
                binary_implicit_type_promotion_with_mixed_types(
                    result_dataframe, first_type, second_type
                )
            )
        else:
            type_promotion = binary_implicit_type_promotion(
                first_type, second_type
            )

        return type_promotion, result_dataframe

    @classmethod
    def validate(  # type: ignore[override]
        cls,
        condition: CondOperand,
        then_op: CondOperand,
        else_op: CondOperand | None = None,
    ) -> CondOperand:
        """ """
        origin = cls.create_origin_expression(condition, then_op, else_op)
        # check condition
        cls.check_condition(condition)
        # check structures
        rslt_structure, rslt_dataframe = cls.check_structures(
            condition, then_op, else_op, origin
        )
        # check_types (with implicit cast)
        rslt_type, rslt_dataframe = cls.check_types(
            then_op, rslt_dataframe, else_op
        )
        # Create the result structure with label
        if isinstance(rslt_structure, Structure):
            recordset = cls._create_labeled_recordset(
                origin=origin,
                rslt_type=rslt_type,
                rslt_structure=rslt_structure,
                result_dataframe=rslt_dataframe,
            )
            return recordset
        labeled_scalar = cls.create_labeled_scalar(
            rslt_structure, rslt_type, origin
        )
        return labeled_scalar


class Nvl(ConditionalOperator):
    """ """

    op: ClassVar[str | None] = tokens.NVL

    @classmethod
    def create_origin_expression(cls, left: Operand, right: Operand) -> str:
        left_name = getattr(left, "name", None) or left.origin
        right_name = getattr(right, "name", None) or right.origin

        origin = f"{cls.op}({left_name},{right_name})"
        return origin

    @classmethod
    def check_structures(
        cls,
        left: CondOperand,
        right: CondOperand,
        origin: str,
    ) -> tuple[Structure | CondOperand, pd.DataFrame | None]:
        """Result structure of ``nvl(left, right)``.

        §8.2.2 admits ``rset`` and ``scal`` operands only, so a set is
        rejected up front. The four remaining combinations are exhaustive:
        none of them leaves the operator without a result structure.
        """
        cls._check_combinable_operand(left, "4-6-2-2")
        cls._check_combinable_operand(right, "4-6-2-2")
        if isinstance(left, RecordSet):
            if isinstance(right, RecordSet):
                cls._check_structures(left, right, origin)
                return left.structure, cls.generate_result_dataframe(
                    left, right
                )
            return left.structure, left.records
        if isinstance(right, RecordSet):
            raise SemanticError("4-6-2-1")
        return left, None

    @classmethod
    def check_types(
        cls,
        first: CondOperand,
        result_dataframe: pd.DataFrame | None,
        second: CondOperand | None = None,
    ) -> tuple[ScalarType, pd.DataFrame | None]:
        """ """
        first_type: ScalarType
        if isinstance(first, RecordSet):
            first_type = first.structure.components["f"].type
        else:
            first_type = first.type

        second_type: ScalarType
        if isinstance(second, RecordSet):
            second_type = second.structure.components["f"].type
        elif isinstance(second, Scalar):
            second_type = second.type
        else:
            raise Exception("Nvl requires a second operand")

        if isinstance(first_type, Mixed) or isinstance(second_type, Mixed):
            if result_dataframe is None:
                raise Exception(
                    "Mixed type promotion requires a result dataframe"
                )
            type_promotion, result_dataframe = (
                binary_implicit_type_promotion_with_mixed_types(
                    result_dataframe, first_type, second_type
                )
            )
        else:
            type_promotion = binary_implicit_type_promotion(
                first_type, second_type
            )
            if result_dataframe is not None:
                if "data_type_left" in result_dataframe.columns:
                    result_dataframe = result_dataframe.drop(
                        columns=["data_type_left", "data_type_right"]
                    )
                # pandas-stubs rejects ScalarType as a broadcast value;
                # runtime stores it in an object-dtype column.
                result_dataframe = result_dataframe.assign(
                    data_type=type_promotion,  # type: ignore[arg-type]
                )

        return type_promotion, result_dataframe

    @classmethod
    def validate(  # type: ignore[override]
        cls, left: CondOperand, right: CondOperand
    ) -> CondOperand:
        """ """
        origin: str = cls.create_origin_expression(left, right)
        # check structures
        rslt_structure, rslt_dataframe = cls.check_structures(
            left, right, origin
        )
        # check_types
        rslt_type, rslt_dataframe = cls.check_types(
            first=left, result_dataframe=rslt_dataframe, second=right
        )
        # Create the result structure with label
        if isinstance(rslt_structure, Structure):
            recordset = cls._create_labeled_recordset(
                origin=origin,
                rslt_type=rslt_type,
                rslt_structure=rslt_structure,
                result_dataframe=rslt_dataframe,
            )
            return recordset
        labeled_scalar = cls.create_labeled_scalar(
            rslt_structure=rslt_structure, rslt_type=rslt_type, origin=origin
        )
        return labeled_scalar


class Filter(ConditionalOperator):
    op: ClassVar[str | None] = tokens.FILTER
    propagate_attributes: ClassVar[bool] = False

    @classmethod
    def create_origin_expression(
        cls, selection: Operand, condition: Operand
    ) -> str:
        selection_name = getattr(selection, "name", None) or getattr(
            selection, "origin", None
        )
        condition_name = getattr(condition, "name", None) or getattr(
            condition, "origin", None
        )

        origin = f"{cls.op} ( {selection_name}, {condition_name} )"
        return origin

    @classmethod
    def _check_filter_structures(
        cls, selection: RecordSet, condition: RecordSet
    ) -> Structure:
        origin: str = cls.create_origin_expression(selection, condition)
        if cls._check_same_recordset_structures(selection, condition, origin):
            return selection.structure

        else:
            condition_is_subset = cls.check_condition_is_subset(
                selection=selection, condition=condition
            )
            if condition_is_subset:
                return selection.structure
            raise errors.SemanticError(
                "4-6-0-2", operand=selection.name, condition=condition.name
            )

    @classmethod
    def validate(  # type: ignore[override]
        cls, selection: Operand, condition: Operand
    ) -> RecordSet:

        if isinstance(selection, RecordSet) and isinstance(
            condition, RecordSet
        ):
            if selection.has_only_global_components:
                add_semantic_warning(
                    f"Performing a filter operation on recordset: {selection.name} which has only global key components"
                )

            check_condition_type = ScalarFactory().scalar_factory("Boolean")
            condition_fact_component = condition.get_fact_component()
            error_info = {"operand_name": condition.name, "op": cls.op}
            unary_implicit_type_promotion(
                condition_fact_component.type,
                check_condition_type,
                error_info=error_info,
            )
            result_structure = cls._check_filter_structures(
                selection, condition
            )

            result_dataframe: pd.DataFrame | None = None
            if selection.records is not None and condition.records is not None:
                result_dataframe = cls.generate_result_dataframe(
                    selection, condition
                )

            return cls.create_labeled_recordset(
                selection=selection,
                condition=condition,
                result_structure=result_structure,
                result_dataframe=result_dataframe,
            )

        raise errors.SemanticError("4-6-3-1")

    @classmethod
    def create_labeled_recordset(
        cls,
        selection: RecordSet,
        condition: RecordSet,
        result_structure: Structure,
        result_dataframe: pd.DataFrame | None,
    ) -> RecordSet:
        origin: str = cls.create_origin_expression(selection, condition)
        recordset = cls._create_labeled_recordset(
            origin=origin,
            rslt_type=result_structure.components["f"].type,
            rslt_structure=result_structure,
            result_dataframe=result_dataframe,
        )
        return recordset
