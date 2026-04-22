import calendar
import operator
from datetime import date, datetime
from typing import Any, Callable

import pandas as pd
from pandas._libs.missing import NAType

duration_mapping = {"A": 6, "S": 5, "Q": 4, "M": 3, "W": 2, "D": 1}

duration_mapping_reversed = {6: "A", 5: "S", 4: "Q", 3: "M", 2: "W", 1: "D"}


class TimePeriod:
    _year: int
    _period_indicator: str
    _period_number: int

    def __init__(self, period: str):
        self.year = int(period[:4])
        if len(period) > 4:
            self.period_indicator = period[4]
        else:
            self.period_indicator = "A"
        if len(period) > 5:
            self.period_number = int(period[5:])
        else:
            self.period_number = 1

    def __str__(self) -> str:
        if self.period_indicator == "A":
            return f"{self.year}{self.period_indicator}"
        return f"{self.year}{self.period_indicator}{self.period_number}"

    @staticmethod
    def _check_year(year: int) -> None:
        if year < 1900 or year > 9999:
            raise ValueError(
                f"Invalid year {year}, must be between 1900 and 9999."
            )

    @property
    def year(self) -> int:
        return self._year

    @year.setter
    def year(self, value: int) -> None:
        self._check_year(value)
        self._year = value

    @property
    def period_indicator(self) -> str:
        return self._period_indicator

    @period_indicator.setter
    def period_indicator(self, value: str) -> None:
        if value not in PeriodDuration():
            raise ValueError(
                f"Cannot set period indicator as {value}. Possible values: {PeriodDuration().member_names}"
            )
        self._period_indicator = value

    @property
    def period_number(self) -> int:
        return self._period_number

    @period_number.setter
    def period_number(self, value: int) -> None:
        if not PeriodDuration.check_period_range(self.period_indicator, value):
            raise ValueError(
                f"Period Number must be between 1 and "
                f"{PeriodDuration.periods[self.period_indicator]} "
                f"for period indicator {self.period_indicator}."
            )
        self._period_number = value

    def _meta_comparison(
        self, other: "TimePeriod", py_op: Callable[[int, int], bool]
    ) -> bool:
        return py_op(
            duration_mapping[self.period_indicator],
            duration_mapping[other.period_indicator],
        )

    def start_date(self, as_date: bool = False) -> date | str:
        """Gets the starting date of the Period."""
        date_value = period_to_date(
            year=self.year,
            period_indicator=self.period_indicator,
            period_number=self.period_number,
            start=True,
        )
        if as_date:
            return date_value
        return date_value.isoformat()

    def end_date(self, as_date: bool = False) -> date | str:
        """Gets the ending date of the Period."""
        date_value = period_to_date(
            year=self.year,
            period_indicator=self.period_indicator,
            period_number=self.period_number,
            start=False,
        )
        if as_date:
            return date_value
        return date_value.isoformat()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TimePeriod):
            return NotImplemented
        return self._meta_comparison(other, operator.eq)

    def __ne__(self, other: object) -> bool:
        if not isinstance(other, TimePeriod):
            return NotImplemented
        return not self._meta_comparison(other, operator.eq)

    def __lt__(self, other: "TimePeriod") -> bool:
        return self._meta_comparison(other, operator.lt)

    def __le__(self, other: "TimePeriod") -> bool:
        return self._meta_comparison(other, operator.le)

    def __gt__(self, other: "TimePeriod") -> bool:
        return self._meta_comparison(other, operator.gt)

    def __ge__(self, other: "TimePeriod") -> bool:
        return self._meta_comparison(other, operator.ge)

    def change_indicator(self, new_indicator: str) -> None:
        if self.period_indicator == new_indicator:
            return
        date_value = period_to_date(
            self.year, self.period_indicator, self.period_number
        )
        self.period_indicator = new_indicator
        new_period = date_to_period(date_value, period_indicator=new_indicator)
        if new_period is None:
            raise ValueError(f"Invalid Period Indicator {new_indicator}")
        self.period_number = new_period.period_number


class Time:
    _date1: str = "0"
    _date2: str = "Z"

    def __init__(self, date1: str, date2: str):
        self.date1 = date1
        self.date2 = date2
        if date1 > date2:
            raise ValueError(
                f"Invalid Time with duration less than 0 ({self.length} days)"
            )

    @classmethod
    def from_dates(cls, date1: date, date2: date) -> "Time":
        return cls(date1.isoformat(), date2.isoformat())

    @classmethod
    def from_iso_format(cls, dates: str) -> "Time":
        return cls(*dates.split("/", maxsplit=1))

    @property
    def date1(self) -> str:
        return self._date1

    @date1.setter
    def date1(self, value: str) -> None:
        date.fromisoformat(value)
        if value > self.date2:
            raise ValueError(
                f"({value} > {self.date2}). Cannot set date1 with a value greater than date2."
            )
        self._date1 = value

    @property
    def date2(self) -> str:
        return self._date2

    @date2.setter
    def date2(self, value: str) -> None:
        date.fromisoformat(value)
        if value < self.date1:
            raise ValueError(
                f"({value} < {self.date1}). Cannot set date2 with a value lower than date1."
            )
        self._date2 = value

    def date1_asdate(self) -> date:
        return date.fromisoformat(self._date1)

    def date2_asdate(self) -> date:
        return date.fromisoformat(self._date2)

    @property
    def length(self) -> int:
        date_left = date.fromisoformat(self.date1)
        date_right = date.fromisoformat(self.date2)
        return (date_right - date_left).days

    __len__ = length

    def __str__(self) -> str:
        return f"{self.date1}/{self.date2}"

    __repr__ = __str__

    def _meta_comparison(
        self, other: "Time", py_op: Callable[[int, int], bool]
    ) -> bool:
        return py_op(self.length, other.length)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Time):
            return NotImplemented
        return self._meta_comparison(other, operator.eq)

    def __ne__(self, other: object) -> bool:
        if not isinstance(other, Time):
            return NotImplemented
        return self._meta_comparison(other, operator.ne)

    def __lt__(self, other: "Time") -> bool:
        return self._meta_comparison(other, operator.lt)

    def __le__(self, other: "Time") -> bool:
        return self._meta_comparison(other, operator.le)

    def __gt__(self, other: "Time") -> bool:
        return self._meta_comparison(other, operator.gt)

    def __ge__(self, other: "Time") -> bool:
        return self._meta_comparison(other, operator.ge)

    @classmethod
    def from_time_period(cls, value: TimePeriod) -> "Time":
        date1 = period_to_date(
            value.year, value.period_indicator, value.period_number, start=True
        )
        date2 = period_to_date(
            value.year,
            value.period_indicator,
            value.period_number,
            start=False,
        )
        return cls.from_dates(date1, date2)


def timePeriodParser(str_: str | NAType | None) -> TimePeriod | NAType:
    """Examples: 2020, 2019A, 2018Q3, 2011M12 2023S2."""
    try:
        if not isinstance(str_, str):
            return pd.NA
        if len(str_) == 0:
            return pd.NA
        return TimePeriod(str_)

    except ValueError:
        # DATAMODEL_DATASET.13
        raise ValueError("Not a valid time period format {}".format(str_))


def timeParser(str_: str | NAType | None) -> NAType | Time:
    """Example: 2000-01-01/2009-12-31."""
    try:
        if not isinstance(str_, str):
            return pd.NA
        if len(str_) == 0:
            return pd.NA
        return Time.from_iso_format(str_)

    except ValueError:
        # DATAMODEL_DATASET.10
        raise ValueError("Not a valid time format {}".format(str_))


def date_to_period(
    date_value: date, period_indicator: str
) -> TimePeriod | None:
    if period_indicator == "A":
        return TimePeriod(f"{date_value.year}A")
    elif period_indicator == "S":
        return TimePeriod(
            f"{date_value.year}S{((date_value.month - 1) // 6) + 1}"
        )
    elif period_indicator == "Q":
        return TimePeriod(
            f"{date_value.year}Q{((date_value.month - 1) // 3) + 1}"
        )
    elif period_indicator == "M":
        return TimePeriod(f"{date_value.year}M{date_value.month}")
    elif period_indicator == "W":
        cal = date_value.isocalendar()
        return TimePeriod(f"{cal[0]}W{cal[1]}")
    elif period_indicator == "D":  # Extract day of the year
        return TimePeriod(
            f"{date_value.year}D{date_value.timetuple().tm_yday}"
        )
    return None


def period_to_date(
    year: int,
    period_indicator: str,
    period_number: int,
    start: bool = False,
) -> date:
    if period_indicator == "A":
        if start:
            return date(year, 1, 1)
        else:
            return date(year, 12, 31)
    if period_indicator == "S":
        if period_number == 1:
            if start:
                return date(year, 1, 1)
            else:
                return date(year, 6, 30)
        else:
            if start:
                return date(year, 7, 1)
            else:
                return date(year, 12, 31)
    if period_indicator == "Q":
        if period_number == 1:
            if start:
                return date(year, 1, 1)
            else:
                return date(year, 3, 31)
        elif period_number == 2:
            if start:
                return date(year, 4, 1)
            else:
                return date(year, 6, 30)
        elif period_number == 3:
            if start:
                return date(year, 7, 1)
            else:
                return date(year, 9, 30)
        else:
            if start:
                return date(year, 10, 1)
            else:
                return date(year, 12, 31)
    if period_indicator == "M":
        if start:
            return date(year, period_number, 1)
        else:
            day = int(calendar.monthrange(year, period_number)[1])
            return date(year, period_number, day)
    if period_indicator == "W":  # 0 for Sunday, 1 for Monday in %w
        if start:
            return datetime.strptime(
                f"{year}-W{period_number}-1", "%G-W%V-%w"
            ).date()
        else:
            return datetime.strptime(
                f"{year}-W{period_number}-0", "%G-W%V-%w"
            ).date()
    if period_indicator == "D":
        return datetime.strptime(f"{year}-D{period_number}", "%Y-D%j").date()

    raise ValueError(f"Invalid Period Indicator {period_indicator}")


class SingletonMeta(type):
    """The Singleton class can be implemented in different ways in Python. Some
    possible methods include: base class, decorator, metaclass. We will use the
    metaclass because it is best suited for this purpose.
    """

    _instances: dict[type, Any] = {}

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        """Possible changes to the value of the `__init__` argument do not affect
        the returned instance.
        """
        if cls not in cls._instances:
            instance = super().__call__(*args, **kwargs)
            cls._instances[cls] = instance
        return cls._instances[cls]


class PeriodDuration(metaclass=SingletonMeta):
    periods = {"D": 365, "W": 53, "M": 12, "Q": 4, "S": 2, "A": 1}

    def __contains__(self, item: object) -> bool:
        return item in self.periods

    @property
    def member_names(self) -> list[str]:
        return list(self.periods.keys())

    @classmethod
    def check_period_range(cls, letter: str, value: int) -> bool:
        if letter == "A":
            return True
        return value in range(1, cls.periods[letter] + 1)
