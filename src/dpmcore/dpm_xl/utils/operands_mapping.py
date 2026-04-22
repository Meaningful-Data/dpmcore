import itertools
import string
from collections.abc import Iterator
from typing import TYPE_CHECKING, Union

from dpmcore.dpm_xl.ast.nodes import PreconditionItem, VarID

if TYPE_CHECKING:
    # Import type only; used for annotation purposes.
    pass


class LabelHandler:
    _instance: "LabelHandler | None" = None
    labels: Iterator[str]
    operands_labels: dict[str, object]
    labels_type: dict[str, str]

    def __new__(cls) -> "LabelHandler":
        if not isinstance(cls._instance, cls):
            cls._instance = object.__new__(cls)
            cls._instance.labels = iter_all_strings()
            cls._instance.operands_labels = {}
            cls._instance.labels_type = {}
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        # Close the existing generator and reset singleton state.
        instance = cls()
        instance.labels.close()  # type: ignore[attr-defined]
        instance.labels = iter_all_strings()
        instance.operands_labels = {}
        instance.labels_type = {}


def iter_all_strings() -> Iterator[str]:
    for size in itertools.count(1):
        for s in itertools.product(string.ascii_uppercase, repeat=size):
            yield "".join(s)


def set_operand_label(
    label: str, operand: Union[str, VarID, PreconditionItem]
) -> None:
    if isinstance(operand, VarID):
        LabelHandler().operands_labels[label] = generate_operand_expression(
            operand
        )
        LabelHandler().labels_type[label] = "single"
    elif isinstance(operand, PreconditionItem):
        LabelHandler().operands_labels[label] = f"v_{operand.variable_code}"
        LabelHandler().labels_type[label] = "single"
    else:
        LabelHandler().operands_labels[label] = operand
        LabelHandler().labels_type[label] = "not_single"


def generate_operand_expression(operand: VarID) -> str:
    operand_expression = "{ "
    operand_expression += f"t{operand.table}"
    if operand.rows:
        operand_expression += f", {','.join(['r' + x for x in operand.rows])}"
    if operand.cols:
        operand_expression += f", {','.join(['c' + x for x in operand.cols])}"
    if operand.sheets:
        operand_expression += (
            f", {','.join(['s' + x for x in operand.sheets])}"
        )
    operand_expression += " }"
    return operand_expression


def get_operand_from_label(label: str) -> object | None:
    if label in LabelHandler().operands_labels:
        return LabelHandler().operands_labels[label]
    return None


def get_type_from_label(label: str) -> str | None:
    if label in LabelHandler().labels_type:
        return LabelHandler().labels_type[label]
    return None


def generate_new_label() -> str:
    label = LabelHandler().labels.__next__()
    return f"$@{label}#"
