from typing import List

from dpmcore import errors
from dpmcore.dpm_xl.operators.base import Binary, Operator
from dpmcore.dpm_xl.operators.conditional import ConditionalOperator
from dpmcore.dpm_xl.symbols import FactComponent, RecordSet
from dpmcore.dpm_xl.types.promotion import unary_implicit_type_promotion
from dpmcore.dpm_xl.types.scalar import ScalarFactory
from dpmcore.dpm_xl.utils import tokens
from dpmcore.dpm_xl.utils.operands_mapping import (
    generate_new_label,
    set_operand_label,
)


class ClauseOperator(Operator):
    op = None
    check_new_names = False
    precondition = False
    propagate_attributes = True

    @classmethod
    def validate(cls, operand, key_names, new_names=None, condition=None):
        if not isinstance(operand, RecordSet):
            raise errors.SemanticError("4-5-0-2", operator=cls.op)

        if condition:
            cls._validate_condition(operand, condition)

        if (
            any(x in operand.get_standard_components() for x in key_names)
            or tokens.FACT in key_names
        ):
            raise errors.SemanticError("4-5-0-1", recordset=operand.name)

        dpm_components = {
            **operand.get_dpm_components(),
            **operand.get_attributes(),
        }

        not_found = [name for name in key_names if name not in dpm_components]
        if not_found:
            raise errors.SemanticError(
                "2-8", op=cls.op, dpm_keys=not_found, recordset=operand.name
            )

        if cls.op == tokens.RENAME:
            if len(new_names) > len(set(new_names)):
                seen = set()
                duplicated = list(
                    {x for x in new_names if x in seen or seen.add(x)}
                )
                raise errors.SemanticError("4-5-1-2", duplicated=duplicated)
            existing_components = [
                name for name in new_names if name in dpm_components
            ]
            if existing_components:
                raise errors.SemanticError(
                    "4-5-1-1",
                    names=existing_components,
                    recordset=operand.name,
                )

            for name, new_name in list(zip(key_names, new_names, strict=False)):
                if new_name in (
                    tokens.ROW,
                    tokens.COLUMN,
                    tokens.SHEET,
                    tokens.FACT,
                    tokens.INDEX_X,
                    tokens.INDEX_Y,
                    tokens.INDEX_Z,
                ):
                    raise errors.SemanticError(
                        "4-5-1-3", recordset=operand.name
                    )
                elif name not in operand.structure.components:
                    raise errors.SemanticError(
                        "4-5-1-4", component=name, recordset=operand.name
                    )
                cls.rename_component(
                    operand=operand, name=name, new_name=new_name
                )

        if cls.op == tokens.WHERE:
            origin = cls.generate_origin_expression(operand, condition)
        elif cls.op == tokens.RENAME:
            origin = cls.generate_origin_expression(
                operand, key_names, new_names
            )
        else:
            origin = cls.generate_origin_expression(operand, key_names[0])

        return cls.generate_result_structure(
            operand, key_names, condition, origin
        )

    @classmethod
    def _validate_condition(cls, operand: RecordSet, condition):
        boolean_type = ScalarFactory().scalar_factory("Boolean")
        if isinstance(condition, RecordSet):
            fact_component = condition.get_fact_component()
            unary_implicit_type_promotion(fact_component.type, boolean_type)
            cls._check_structures(operand, condition)
        else:
            unary_implicit_type_promotion(condition.type, boolean_type)

    @classmethod
    def _check_structures(cls, operand: RecordSet, condition: RecordSet):
        operand_structure = operand.structure
        condition_structure = condition.structure
        if len(operand_structure.get_key_components()) == len(
            condition.get_key_components()
        ):
            origin = f"{operand.origin}[where {condition.origin}]"
            # For better error management
            class_check = Binary()
            class_check.op = cls.op
            class_check.check_same_components(
                operand_structure, condition_structure, origin
            )
        else:
            is_subset = ConditionalOperator.check_condition_is_subset(
                operand, condition
            )
            if not is_subset:
                raise errors.SemanticError(
                    "4-5-2-2", operand=operand.name, condition=condition.name
                )

    @classmethod
    def rename_component(cls, operand: RecordSet, name: str, new_name: str):
        component = operand.structure.components[name]
        del operand.structure.components[name]
        component.name = new_name
        operand.structure.components[new_name] = component

    @classmethod
    def generate_result_structure(
        cls, operand: RecordSet, key_names: List[str], condition, origin
    ):

        new_label = generate_new_label()
        operand.structure.replace_components_parent(new_label)

        if cls.op == tokens.GET:
            selected_component = key_names[0]
            component = operand.structure.components[selected_component]
            del operand.structure.components[tokens.FACT]
            fact_component = FactComponent(
                type_=component.type, parent=component.parent
            )
            operand.structure.components[tokens.FACT] = fact_component

        if not cls.propagate_attributes:
            operand.structure.remove_attributes()

        result = RecordSet(
            structure=operand.structure, name=new_label, origin=origin
        )
        if condition and isinstance(condition, RecordSet):
            result_dataframe = ConditionalOperator.generate_result_dataframe(
                operand, condition
            )
            result.records = result_dataframe
        else:
            result.records = operand.records
        set_operand_label(result.name, result.origin)
        return result

    @classmethod
    def generate_origin_expression(cls, *args) -> str:
        pass


class Where(ClauseOperator):
    op = tokens.WHERE

    @classmethod
    def validate_condition_type(cls, condition):
        boolean_type = ScalarFactory().scalar_factory("Boolean")
        error_info = {"operand_name": condition.name, "op": cls.op}
        unary_implicit_type_promotion(
            condition.type, boolean_type, error_info=error_info
        )

    @classmethod
    def generate_origin_expression(cls, operand, condition):
        operand_name = getattr(operand, "name", None) or getattr(
            operand, "origin", None
        )
        condition_name = getattr(condition, "name", None) or getattr(
            condition, "origin", None
        )
        return f"{operand_name}[ where {condition_name}]"


class Rename(ClauseOperator):
    op = tokens.RENAME

    @classmethod
    def generate_origin_expression(cls, operand, old_names, new_names):
        origin_nodes = [
            f"{old_names[i]} to {new_names[i]}" for i in range(len(old_names))
        ]
        return f"{operand.name} [ rename " + ", ".join(origin_nodes) + "]"


class Get(ClauseOperator):
    op = tokens.GET
    propagate_attributes = False

    @classmethod
    def generate_origin_expression(cls, operand, component) -> str:
        return f"{operand.name} [ get {component} ]"


class Sub(ClauseOperator):
    op = tokens.SUB
    propagate_attributes = True

    @classmethod
    def validate(cls, operand, property_code, value):
        if not isinstance(operand, RecordSet):
            raise errors.SemanticError("4-5-0-2", operator=cls.op)

        # Validate that the property_code exists in the operand's components
        dpm_components = operand.get_dpm_components()
        if property_code not in dpm_components:
            raise errors.SemanticError(
                "2-8",
                op=cls.op,
                dpm_keys=[property_code],
                recordset=operand.name,
            )

        # Generate origin expression
        origin = cls.generate_origin_expression(operand, property_code, value)

        # Generate a new label for the result
        new_label = generate_new_label()
        operand.structure.replace_components_parent(new_label)

        # The sub operator drops the specified component from the structure
        if property_code in operand.structure.components:
            del operand.structure.components[property_code]

        # Remove attributes if not propagating
        if not cls.propagate_attributes:
            operand.structure.remove_attributes()

        result = RecordSet(
            structure=operand.structure, name=new_label, origin=origin
        )
        result.records = operand.records
        set_operand_label(result.name, result.origin)
        return result

    @classmethod
    def generate_origin_expression(cls, operand, property_code, value) -> str:
        operand_name = getattr(operand, "name", None) or getattr(
            operand, "origin", None
        )
        value_str = (
            getattr(value, "name", None)
            or getattr(value, "origin", None)
            or str(value)
        )
        return f"{operand_name}[sub {property_code} = {value_str}]"
