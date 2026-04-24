from typing import ClassVar

import pandas as pd

from dpmcore import errors
from dpmcore.dpm_xl.operators.base import Unary
from dpmcore.dpm_xl.symbols import RecordSet, Scalar, Structure
from dpmcore.dpm_xl.types.promotion import unary_implicit_type_promotion
from dpmcore.dpm_xl.types.scalar import (
    Integer,
    Number,
    ScalarFactory,
    ScalarType,
)
from dpmcore.dpm_xl.utils import tokens
from dpmcore.dpm_xl.warning_collector import add_semantic_warning


class AggregateOperator(Unary):
    """Aggregate operators involve all operators with a Recordset and a Grouping clause.

    The grouping clause components must be present in the operand recordset.
    """

    interval_allowed: ClassVar[bool] = True

    @staticmethod
    def check_grouping(
        grouping_clause: list[str] | None, key_components: list[str]
    ) -> None:

        if grouping_clause and not all(
            item in key_components for item in grouping_clause
        ):
            not_present = [
                item for item in grouping_clause if item not in key_components
            ]
            raise errors.SemanticError("4-4-0-2", not_present=not_present)

    @staticmethod
    def format_structure_with_grouping(
        operand: RecordSet, grouping_clause: list[str]
    ) -> Structure:
        structure = operand.structure

        components_to_delete = []

        for component in structure.components:
            if component not in grouping_clause and component != "refPeriod":
                components_to_delete.append(component)

        for item in components_to_delete:
            del structure.components[item]

        return structure

    @staticmethod
    def manage_records(
        records: pd.DataFrame | None, grouping_clause: list[str]
    ) -> pd.DataFrame | None:
        if records is None:
            return records
        columns_to_preserve = ["data_type"]
        for item in grouping_clause:
            columns_to_preserve.append(item)

        columns_to_delete = [
            item for item in records.columns if item not in columns_to_preserve
        ]

        for col in columns_to_delete:
            del records[col]

        if len(records.columns) == 1 and records.columns[0] == "data_type":
            return None

        records = records.loc[
            records.astype(str).drop_duplicates(keep="first").index
        ].reset_index(drop=True)

        return records

    @classmethod
    def create_grouped_recordset(
        cls,
        operand: RecordSet,
        grouping_clause: list[str],
        final_type: ScalarType,
    ) -> RecordSet:

        # Creating new structure with only the grouped components
        rslt_structure = cls.format_structure_with_grouping(
            operand, grouping_clause
        )
        origin = (
            f"{cls.op}({operand.name} group by {', '.join(grouping_clause)})"
        )
        result_dataframe = (
            cls.manage_records(operand.records, grouping_clause)
            if operand.records is not None
            else None
        )
        recordset = cls._create_labeled_recordset(
            origin=origin,
            rslt_type=final_type,
            rslt_structure=rslt_structure,
            result_dataframe=result_dataframe,
        )
        return recordset

    @classmethod
    def validate(
        cls, operand: RecordSet, grouping_clause: list[str] | None
    ) -> RecordSet | Scalar:
        cls.check_operator_well_defined()
        return_type = (
            None
            if cls.return_type is None
            else ScalarFactory().scalar_factory(cls.return_type.__name__)
        )
        op_type_to_check = (
            None
            if cls.type_to_check is None
            else ScalarFactory().scalar_factory(cls.type_to_check.__name__)
        )

        error_info = {"operand_name": operand.name, "op": cls.op}
        fact_component_type = operand.structure.components["f"].type

        final_type = unary_implicit_type_promotion(
            fact_component_type,
            op_type_to_check,
            return_type=return_type,
            interval_allowed=cls.interval_allowed,
            error_info=error_info,
        )
        if operand.records is not None:
            # Broadcast ScalarType into an object-dtype column.
            operand.records["data_type"] = final_type  # type: ignore[call-overload]

        if grouping_clause is None:
            # Aggregate reduces a recordset to a scalar; ``_create_labeled_scalar``
            # only needs the origin string, not a Scalar operand.
            origin = cls.create_origin_expression(operand)
            return cls._create_labeled_scalar(
                origin=origin, result_type=final_type
            )

        key_components = operand.get_key_components_names()
        cls.check_grouping(grouping_clause, key_components)
        if len(grouping_clause) == len(key_components):
            add_semantic_warning(
                f"Grouping by all the key components of the Recordset: {','.join(key_components)}"
            )

        return cls.create_grouped_recordset(
            operand, grouping_clause, final_type
        )

    @classmethod
    def generate_origin_expression(
        cls,
        operand: RecordSet | Scalar,
        group_by: list[str] | None = None,
    ) -> str:
        operand_name = getattr(operand, "name", None) or getattr(
            operand, "origin", None
        )
        if group_by:
            return f"{cls.op}({operand_name} group by {group_by})"
        else:
            return f"{cls.op}({operand_name})"


class MaxAggr(AggregateOperator):
    op: ClassVar[str | None] = tokens.MAX_AGGR


class MinAggr(AggregateOperator):
    op: ClassVar[str | None] = tokens.MIN_AGGR


class Sum(AggregateOperator):
    op: ClassVar[str | None] = tokens.SUM
    type_to_check: ClassVar[type[ScalarType] | None] = Number


class Count(AggregateOperator):
    op: ClassVar[str | None] = tokens.COUNT
    type_to_check: ClassVar[type[ScalarType] | None] = None
    return_type: ClassVar[type[ScalarType] | None] = Integer


class Avg(AggregateOperator):
    op: ClassVar[str | None] = tokens.AVG
    type_to_check: ClassVar[type[ScalarType] | None] = Number
    return_type: ClassVar[type[ScalarType] | None] = Number


class Median(AggregateOperator):
    op: ClassVar[str | None] = tokens.MEDIAN
    type_to_check: ClassVar[type[ScalarType] | None] = Number
    return_type: ClassVar[type[ScalarType] | None] = Number
