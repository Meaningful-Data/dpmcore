from collections.abc import Iterator
from typing import Any

import numpy as np
import pandas as pd

from dpmcore.dpm_xl.types.time import timeParser, timePeriodParser
from dpmcore.errors import DataTypeError, SemanticError


class ScalarType:
    """ """

    default: Any = None

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}"

    def strictly_same_class(self, obj: "ScalarType") -> bool:
        if not isinstance(obj, ScalarType):
            raise Exception("Not use strictly_same_class")
        return self.__class__ == obj.__class__

    def __eq__(self, other: object) -> bool:
        return self.__class__.__name__ == other.__class__.__name__

    def is_included(self, set_: set["type[ScalarType]"]) -> bool:
        return self.__class__ in set_

    def is_subtype(self, obj: "ScalarType") -> bool:
        if not isinstance(obj, ScalarType):
            raise Exception("Not use is_subtype")
        return issubclass(self.__class__, obj.__class__)

    def is_null_type(self) -> bool:
        return False

    def set_interval(self, interval: bool) -> None:
        raise SemanticError("3-4", operand_type=self.__class__.__name__)

    __str__ = __repr__


class String(ScalarType):
    """ """

    default: Any = ""

    def __init__(self) -> None:
        super().__init__()

    def check_type(
        self, value: object
    ) -> bool | None:  # Not needed for semantic, but can be util later
        if isinstance(value, str):
            return True
        raise DataTypeError(value, String)  # type: ignore[arg-type]

    def cast(self, value: object) -> str:
        return str(value)

    @property
    def dtype(self) -> str:
        return "string"


class Number(ScalarType):
    """ """

    def __init__(self, interval: bool = False) -> None:
        super().__init__()
        self.interval: bool = interval

    def check_type(self, value: object) -> bool | None:
        if isinstance(value, float):
            return True

        raise DataTypeError(value, Number)  # type: ignore[arg-type]

    def cast(self, value: object) -> float:
        return float(value)  # type: ignore[arg-type]

    def set_interval(self, interval: bool) -> None:
        self.interval = interval

    @property
    def dtype(self) -> str:
        return "Float64"


class Integer(Number):
    """ """

    def __init__(self, interval: bool = False) -> None:
        super().__init__(interval)

    def check_type(self, value: object) -> bool | None:
        if isinstance(value, int):
            return True

        raise DataTypeError(value, Integer)  # type: ignore[arg-type]

    def cast(self, value: object) -> int:
        return int(round(float(value), 0))  # type: ignore[arg-type]

    @property
    def dtype(self) -> str:
        return "Int64"


class TimeInterval(ScalarType):
    """ """

    default: Any = pd.NA

    def __init__(self) -> None:
        super().__init__()

    def check_type(self, value: object) -> bool | None:
        if isinstance(value, str):
            return True

        raise DataTypeError(value, TimeInterval)  # type: ignore[arg-type]

    def cast(self, value: object) -> Any:
        return timeParser(value)  # type: ignore[arg-type]

    @property
    def dtype(self) -> str:
        return "string"


class Date(TimeInterval):
    """ """

    default: Any = np.nan

    def __init__(self) -> None:
        super().__init__()

    def check_type(self, value: object) -> bool | None:
        pass

    def cast(self, value: object) -> str:
        return str(value)

    @property
    def dtype(self) -> str:
        return "string"


class TimePeriod(TimeInterval):
    """ """

    default: Any = pd.NA

    def __init__(self) -> None:
        super().__init__()

    def check_type(self, value: object) -> bool | None:
        pass

    def cast(self, value: object) -> Any:
        return timePeriodParser(value)  # type: ignore[arg-type]

    @property
    def dtype(self) -> str:
        return "string"


class Duration(ScalarType):
    pass


class Boolean(ScalarType):
    """ """

    default: Any = np.nan

    def __init__(self) -> None:
        super().__init__()

    def check_type(self, value: object) -> bool | None:
        if isinstance(value, bool):
            return True
        return None

    def cast(self, value: object) -> Any:
        if isinstance(value, str):
            if value.lower() == "true":
                return True
            elif value.lower() == "false":
                return False
            elif value.lower() == "1":
                return True
            elif value.lower() == "0":
                return False
            else:
                return np.nan
        if isinstance(value, int):
            return value != 0
        if isinstance(value, float):
            return value != 0.0
        if isinstance(value, bool):
            return value
        if isinstance(value, np.bool_):
            return np.bool_(value)
        if pd.isnull(value):  # type: ignore[call-overload]
            return np.nan
        return np.nan

    @property
    def dtype(self) -> str:
        return "boolean"


class Null(ScalarType):  # I think it is needed
    """All the Data Types are assumed to contain the conventional value null, which means “no value”, or “absence of known value” or “missing value”.
    Note that the null value, therefore, is the only value of multiple different types.
    """

    default: Any = None

    def __init__(self) -> None:
        super().__init__()

    def is_null_type(self) -> bool:
        return True

    def cast(self, value: object) -> None:
        return None


class Mixed(ScalarType):
    """ """

    def __init__(self) -> None:
        super().__init__()


class Item(ScalarType):
    default: Any = ""

    def __init__(self) -> None:
        super().__init__()

    def cast(self, value: object) -> str:
        return str(value)

    @property
    def dtype(self) -> str:
        return "string"


class Subcategory(ScalarType):
    pass


class ScalarFactory:
    types_dict: dict[str, type[ScalarType]] = {
        "String": String,
        "Number": Number,
        "Integer": Integer,
        "TimeInterval": TimeInterval,
        "Date": Date,
        "TimePeriod": TimePeriod,
        "Duration": Duration,
        "Boolean": Boolean,
        "Item": Item,
        "Subcategory": Subcategory,
        "Null": Null,
        "Mixed": Mixed,
    }

    database_types: dict[str, type[ScalarType]] = {
        "URI": String,
        "PER": Number,
        "ENU": Item,
        "DAT": TimeInterval,
        "STR": String,
        "INT": Integer,
        "MON": Number,
        "BOO": Boolean,
        "TRU": Boolean,
        "DEC": Number,
        "b": Boolean,
        "d": TimeInterval,
        "i": Integer,
        "m": Number,
        "p": Number,
        "e": Item,
        "s": String,
        "es": String,
        "r": Number,
        "t": Boolean,
    }

    def scalar_factory(
        self, code: str | None = None, interval: bool | None = None
    ) -> ScalarType:
        if code in ("Number", "Integer"):
            # Number/Integer constructors accept interval; pass through as-is
            # to preserve original behavior when interval is None.
            return self.types_dict[code](interval)  # type: ignore[call-arg]
        if code is not None and code in self.types_dict:
            return self.types_dict[code]()
        return Null()

    def database_types_mapping(self, code: str) -> type[ScalarType]:
        return self.database_types[code]

    def all_types(self) -> Iterator[type[ScalarType]]:
        return (v for v in self.types_dict.values())

    def from_database_to_scalar_types(
        self, code: str, interval: bool
    ) -> ScalarType:
        scalar_type = self.database_types_mapping(code)
        if isinstance(scalar_type(), Number):
            return scalar_type(interval)  # type: ignore[call-arg]
        if interval:
            raise SemanticError("3-4", operand_type=scalar_type.__name__)
        return scalar_type()
