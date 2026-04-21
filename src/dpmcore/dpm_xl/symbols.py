from typing import List, Union

from dpmcore.dpm_xl.types.scalar import ScalarFactory
from dpmcore.errors import SemanticError
from dpmcore.dpm_xl.utils.tokens import DPM, STANDARD


class Operand:
    """
    Superclass of all Symbols.

    :parameter name: Name of the operand
    :parameter origin: Expression to be used to generate this operand.

    Example of origin expression:

    A + B = C -> D = C

    A: First operand of the addition
    B: Second operand of the addition

    C: Second operand of the equality
    D: First operand of the equality (Origin: A + B)
    """

    def __init__(self, name: Union[str, None], origin: str):
        self.name = name
        self.origin = origin


class Scalar(Operand):
    """
    Operand to be used when finding a single Cell Reference or an Item
    """

    def __init__(self, type_, name, origin):
        super().__init__(name, origin)
        self.type = type_

    def __repr__(self):
        return "<{class_name}(type='{type}',)>".format(
            class_name=self.__class__.__name__, type=self.type
        )


class Component:
    """
    Superclass of all components inside a recordset
    """

    def __init__(
        self, name: str, type_, parent: str, is_global: bool = False
    ) -> None:
        if type_.__class__ in ScalarFactory().all_types():
            self.name = name
            self.type = type_
            self.parent = parent
            self.is_global = is_global
        else:
            raise Exception(
                "INTERNAL: Wrong data type on Component generation"
            )


class KeyComponent(Component):
    """
    Component used to specify the row, column, sheet or property in a Recordset

    :parameter name: Name of the component
    :parameter type_: Data type of the component
    :parameter subtype: Specifies if it is a Standard component (Row, Column or Sheet) or a DPM component
    """

    def __init__(
        self,
        name: str,
        type_: ScalarFactory().all_types,
        subtype: str,
        parent: str,
        is_global: bool = False,
    ) -> None:
        super().__init__(name, type_, parent, is_global)
        self.name = name
        if subtype in (DPM, STANDARD):
            self.subtype = subtype
        else:
            raise SemanticError("2-7", component_name=name)


class FactComponent(Component):
    """
    Component used to specify the data type of the recordset
    """

    def __init__(self, type_: ScalarFactory().all_types, parent: str) -> None:
        super().__init__("f", type_, parent)


class AttributeComponent(Component):
    """
    Components that are included in the recordset as auxiliar information.
    These components are drop normally except for rename and where operators.
    """

    def __init__(
        self, name: str, type_: ScalarFactory().all_types, parent: str
    ) -> None:
        super().__init__(name, type_, parent)


class Structure:
    """
    Structure for the Recordset. Components must have unique names and only one Fact Component can be present.
    """

    def __init__(self, components: List[Component]) -> None:
        components_names = [
            c.name for c in components if isinstance(c, Component)
        ]
        if len(components_names) != len(set(components_names)) or len(
            components
        ) != len(components_names):
            raise Exception(
                "Duplicated Component Names, check key_components query."
            )
        facts_components = [
            c.name for c in components if isinstance(c, FactComponent)
        ]
        if len(facts_components) > 1:
            raise Exception("Duplicated Fact Component")
        self.components = {c.name: c for c in components}

    def get_key_components(self) -> dict:
        dpm_components = self.get_dpm_components()
        standard_components = self.get_standard_components()
        return {**dpm_components, **standard_components}

    def get_key_components_names(self) -> List[str]:
        return [elto for elto in self.get_key_components()]

    def get_dpm_components(self) -> dict:
        dpm_components = {
            elto_k: elto_v
            for elto_k, elto_v in self.components.items()
            if (isinstance(elto_v, KeyComponent) and elto_v.subtype == DPM)
        }
        return dpm_components

    def get_standard_components(self):
        standard_components = {
            elto_k: elto_v
            for elto_k, elto_v in self.components.items()
            if (
                isinstance(elto_v, KeyComponent) and elto_v.subtype == STANDARD
            )
        }
        return standard_components

    def get_standard_components_names(self) -> List[str]:
        return [elto for elto in self.get_standard_components()]

    def get_fact_component(self):
        fact_component = [
            elto_v
            for elto_v in self.components.values()
            if (isinstance(elto_v, FactComponent))
        ]
        return fact_component[0]

    def get_attributes(self):
        attributes = {
            elto_k: elto_v
            for elto_k, elto_v in self.components.items()
            if (isinstance(elto_v, AttributeComponent))
        }
        return attributes

    def replace_components_parent(self, parent: str):
        for component in self.get_key_components().values():
            component.parent = parent

    def get_attributes_names(self):
        return [
            attribute
            for attribute in self.components
            if isinstance(self.components[attribute], AttributeComponent)
        ]

    def remove_attributes(self):
        attributes_names = self.get_attributes_names()
        for attribute_name in attributes_names:
            del self.components[attribute_name]


class RecordSet(Operand):
    """
    Recordset are collections of Records that share a same Structure.
    Technically, Recordsets are two-dimensional labelled data structures (tabular),
    which can be assimilated to Relational Tables or Data Frames.
    The columns (fields) of the Recordset are provided by the Components of its Structure.
    The rows of the Recordset are its composing Records.

    :parameter structure: Structure of the recordset
    :var records: Pandas dataframe to hold the data related to this Recordset
    """

    def __init__(self, structure: Structure, name: str, origin: str) -> None:
        if not isinstance(structure, Structure):
            raise Exception("Data Validation Error")
        super().__init__(name, origin)
        self.structure: Structure = structure
        self.records = None
        self.name = name
        self.errors = None
        self.interval = None
        self.default = None
        self.has_only_global_components = all(
            [
                component.is_global
                for component in structure.get_key_components().values()
            ]
        )

    def get_key_components(self) -> dict:
        return self.structure.get_key_components()

    def get_key_components_names(self) -> List[str]:
        return self.structure.get_key_components_names()

    def get_dpm_components(self):
        return self.structure.get_dpm_components()

    def get_standard_components(self):
        return self.structure.get_standard_components()

    def get_standard_components_names(self) -> List[str]:
        return self.structure.get_standard_components_names()

    def get_fact_component(self):
        return self.structure.get_fact_component()

    def get_attributes(self):
        return self.structure.get_attributes()


class ScalarSet(Operand):
    """
    Scalar set are a collection of scalars used in the IN operator.
    """

    def __init__(self, type_, name, origin):
        super().__init__(name, origin)
        self.type = type_


class ConstantOperand(Scalar):
    def __init__(self, type_, name, origin, value):
        super().__init__(name=name, origin=origin, type_=type_)
        self.value = value  # TODO: Check this
