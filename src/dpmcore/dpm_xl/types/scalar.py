import numpy as np
import pandas as pd

from dpmcore.dpm_xl.types.time import timeParser, timePeriodParser
from dpmcore.errors import DataTypeError, SemanticError


class ScalarType:
    """ """

    default = None

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}"

    def strictly_same_class(self, obj) -> bool:
        if not isinstance(obj, ScalarType):
            raise Exception("Not use strictly_same_class")
        return self.__class__ == obj.__class__

    def __eq__(self, other):
        return self.__class__.__name__ == other.__class__.__name__

    def is_included(self, set_: set) -> bool:
        return self.__class__ in set_

    def is_subtype(self, obj) -> bool:
        if not isinstance(obj, ScalarType):
            raise Exception("Not use is_subtype")
        return issubclass(self.__class__, obj.__class__)

    def is_null_type(self) -> bool:
        return False

    def set_interval(self, interval: bool):
        raise SemanticError("3-4", operand_type=self.__class__.__name__)

    __str__ = __repr__


class String(ScalarType):
    """ """

    default = ""

    def __init__(self):
        super().__init__()

    def check_type(
        self, value
    ):  # Not needed for semantic, but can be util later
        if isinstance(value, str):
            return True
        raise DataTypeError(value, String)

    def cast(self, value):
        return str(value)

    @property
    def dtype(self):
        return "string"


class Number(ScalarType):
    """ """

    def __init__(self, interval=False):
        super().__init__()
        self.interval: bool = interval

    def check_type(self, value):
        if isinstance(value, float):
            return True

        raise DataTypeError(value, Number)

    def cast(self, value):
        return float(value)

    def set_interval(self, interval: bool):
        self.interval = interval

    @property
    def dtype(self):
        return "Float64"


class Integer(Number):
    """ """

    def __init__(self, interval=False):
        super().__init__(interval)

    def check_type(self, value):
        if isinstance(value, int):
            return True

        raise DataTypeError(value, Integer)

    def cast(self, value):
        return int(round(float(value), 0))

    @property
    def dtype(self):
        return "Int64"


class TimeInterval(ScalarType):
    """ """

    default = pd.NA

    def __init__(self):
        super().__init__()

    def check_type(self, value):
        if isinstance(value, str):
            return True

        raise DataTypeError(value, TimeInterval)

    def cast(self, value):
        return timeParser(value)

    @property
    def dtype(self):
        return "string"


class Date(TimeInterval):
    """ """

    default = np.nan

    def __init__(self):
        super().__init__()

    def check_type(self, value):
        pass

    def cast(self, value):
        return str(value)

    @property
    def dtype(self):
        return "string"


class TimePeriod(TimeInterval):
    """ """

    default = pd.NA

    def __init__(self):
        super().__init__()

    def check_type(self, value):
        pass

    def cast(self, value):
        return timePeriodParser(value)

    @property
    def dtype(self):
        return "string"


class Duration(ScalarType):
    pass


class Boolean(ScalarType):
    """ """

    default = np.nan

    def __init__(self):
        super().__init__()

    def check_type(self, value):
        if isinstance(value, bool):
            return True

    def cast(self, value):
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
        if pd.isnull(value):
            return np.nan
        return np.nan

    @property
    def dtype(self):
        return "boolean"


class Null(ScalarType):  # I think it is needed
    """All the Data Types are assumed to contain the conventional value null, which means “no value”, or “absence of known value” or “missing value”.
    Note that the null value, therefore, is the only value of multiple different types.
    """

    default = None

    def __init__(self):
        super().__init__()

    def is_null_type(self) -> bool:
        return True

    def cast(self, value):
        return type(None)()


class Mixed(ScalarType):
    """ """

    def __init__(self):
        super().__init__()


class Item(ScalarType):
    default = ""

    def __init__(self):
        super().__init__()

    def cast(self, value):
        return str(value)

    @property
    def dtype(self):
        return "string"


class Subcategory(ScalarType):
    pass


class ScalarFactory:
    types_dict = {
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

    database_types = {
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

    def scalar_factory(self, code=None, interval=None):
        if code in ("Number", "Integer"):
            return self.types_dict[code](interval)
        if code in self.types_dict:
            return self.types_dict[code]()
        return Null()

    def database_types_mapping(self, code):
        return self.database_types[code]

    def all_types(self):
        return (v for v in self.types_dict.values())

    def from_database_to_scalar_types(self, code, interval):
        scalar_type = self.database_types_mapping(code)
        if isinstance(scalar_type(), Number):
            return scalar_type(interval)
        if interval:
            raise SemanticError("3-4", operand_type=scalar_type.__name__)
        return scalar_type()
