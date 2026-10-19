"""The ``modules`` section of the export (Script Format 2.0).

Every module the export refers to, its own included, keyed by DPM module
code. Each lists the versions a read can land in, in date order, with
their reference-date windows, the tables and Variables read from them
(every table and Variable on the export's own version), and the
operations a version cannot serve (``not_evaluable``). A consumer picks
the version whose window holds a read's target date, so a dependency
read at another period reaches the version in force then.

Nothing here is specific to calculations: the input is what each
statement of the script reads (:class:`Read`) and the operation code of
each statement.
"""

from __future__ import annotations

import calendar
import logging
from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    FrozenSet,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
    cast,
)

import pandas as pd

from dpmcore.dpm_xl.model_queries import ViewDatapointsQuery
from dpmcore.errors import NotFound
from dpmcore.orm.packaging import ModuleVersion, ModuleVersionComposition
from dpmcore.orm.query_utils import chunked_in
from dpmcore.orm.release_sort_order import (
    compute_sort_order,
    load_release_sort_orders,
)
from dpmcore.orm.rendering import TableVersion, TableVersionCell
from dpmcore.orm.variables import VariableVersion
from dpmcore.services._open_keys import (
    get_open_key_properties,
    get_open_keys_for_tables,
)
from dpmcore.services.calculations_export.queries import (
    get_module_uri,
    modules_of_table_vids,
    to_date,
    windowed_table_vids,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

ONE_DAY = timedelta(days=1)

_MONTHS_PER_PERIOD = {"A": 12, "S": 6, "Q": 3, "M": 1}
_DAYS_PER_PERIOD = {"W": 7, "D": 1}
_AXES = (
    ("row", "row_code"),
    ("column", "column_code"),
    ("sheet", "sheet_code"),
)

Window = Tuple[Optional[date], Optional[date]]
"""A reference-date window; ``None`` leaves that side open."""


@dataclass(frozen=True)
class RefDateLag:
    """How far from the anchor's reference date a read lands.

    Kept in months for ``A``, ``S``, ``Q`` and ``M`` shifts and in days
    for ``W`` and ``D``, so that nested shifts add up.

    Attributes:
        value: The offset in ``unit``; negative is earlier.
        unit: ``"M"`` or ``"D"``.
    """

    value: int
    unit: str = "M"

    @classmethod
    def of_time_shift(
        cls, period: str, shift_number: int
    ) -> Optional["RefDateLag"]:
        """Return the lag of ``time_shift(x, period, shift_number)``.

        A positive shift reads the past: ``time_shift(x, A, 1)`` at T
        reads x at T-1A.

        Args:
            period: The period indicator (``A``, ``S``, ``Q``, ``M``,
                ``W`` or ``D``).
            shift_number: The number of periods shifted.

        Returns:
            The lag, or ``None`` for an unknown period indicator.
        """
        if period in _MONTHS_PER_PERIOD:
            return cls(-shift_number * _MONTHS_PER_PERIOD[period], "M")
        if period in _DAYS_PER_PERIOD:
            return cls(-shift_number * _DAYS_PER_PERIOD[period], "D")
        return None

    def target(self, anchor: date) -> date:
        """Return the date a read at this lag lands on from ``anchor``.

        A lag in months lands on the last day of the month reached, as
        Script Format 2.0 computes a reference's target date.
        """
        if self.value == 0:
            return anchor
        if self.unit == "D":
            return anchor + timedelta(days=self.value)
        months = anchor.month - 1 + self.value
        year, month = anchor.year + months // 12, months % 12 + 1
        return date(year, month, calendar.monthrange(year, month)[1])


AT_T = RefDateLag(0)
"""A read at the anchor's own reference date."""


def combine_lags(
    outer: Optional[RefDateLag], inner: Optional[RefDateLag]
) -> Optional[RefDateLag]:
    """Return the lag of a shift applied inside another.

    ``None`` stands for a read that can land on any date. Months and days
    do not add up into one lag, so mixing them gives ``None`` too.
    """
    if outer is None or inner is None:
        return None
    if outer.value == 0:
        return inner
    if inner.value == 0:
        return outer
    if outer.unit != inner.unit:
        return None
    return RefDateLag(outer.value + inner.value, outer.unit)


@dataclass(frozen=True)
class Read:
    """The Variables one statement reads from one table, at one lag.

    Attributes:
        statement: Position of the statement in the script.
        table: Code of the table read.
        variable_ids: The ``VariableID``s the selection covers.
        lag: Where the read lands; ``None`` when no lag describes it (a
            ``where`` or ``sub`` on ``refPeriod``, or an analytic
            ordered by it) and it can land on any date.
    """

    statement: int
    table: str
    variable_ids: FrozenSet[int]
    lag: Optional[RefDateLag] = AT_T


@dataclass(frozen=True)
class ModuleVersionInfo:
    """One module version, as far as its window and release go.

    Attributes:
        module_vid: The module version.
        version_number: Its version number.
        start: First reference date; ``None`` when the DPM has none.
        end: Last reference date; ``None`` when open-ended.
        start_release_id: The release it was published in.
        end_release_id: The release that ended it; ``None`` while it
            is current.
    """

    module_vid: int
    version_number: Optional[str]
    start: Optional[date]
    end: Optional[date]
    start_release_id: Optional[int]
    end_release_id: Optional[int] = None


def is_working_release(
    sort_orders: Mapping[int, int], release_id: Optional[int]
) -> bool:
    """Whether ``release_id`` is a working release, such as ``Playground``.

    It sorts after every published release.
    """
    return release_id is not None and sort_orders.get(
        release_id, -1
    ) >= compute_sort_order(None, None)


def as_published(
    version: ModuleVersionInfo, sort_orders: Mapping[int, int]
) -> ModuleVersionInfo:
    """Return ``version`` as published: open if a working release ended it.

    A working release that ends a version also rewrites its end date in
    the same row, and the database keeps no other, so the version is
    taken as open until its next published successor starts. This
    assumes it was open as published; one that had an end date of its
    own is stretched to that successor.
    """
    if is_working_release(sort_orders, version.end_release_id):
        return replace(version, end=None)
    return version


def is_ghost(version: ModuleVersionInfo) -> bool:
    """Whether ``version`` never applied: its window ends on its start.

    An inverted window (ending before it starts) never applied either.
    """
    return (
        version.start is not None
        and version.end is not None
        and version.end <= version.start
    )


def version_chain(
    versions: Iterable[ModuleVersionInfo],
    sort_orders: Mapping[int, int],
    *,
    keep: Optional[int] = None,
    drafts: bool = False,
) -> List[ModuleVersionInfo]:
    """Return the versions of one module that applied, in date order.

    Unless ``drafts``, the versions are read as published: those of a
    working release are dropped, and one a working release ended is
    open again (:func:`as_published`). Then ghosts and versions without
    a start date are dropped. Of two versions starting on the same date
    a published one beats one of a working release, and otherwise the
    later release wins. The version ``keep`` (the export's own) is
    never dropped. Each window is then cut where its successor starts,
    so no two overlap.

    Args:
        versions: Every version of the module.
        sort_orders: ``{release_id: sort_order}``.
        keep: A ``module_vid`` to keep whatever its window or release.
        drafts: Whether to read the versions as the working release
            left them, as when the export itself is resolved at one.

    Returns:
        The versions, earliest first, with non-overlapping windows.
    """
    draft = compute_sort_order(None, None)
    if not drafts:
        versions = [as_published(version, sort_orders) for version in versions]

    def rank(version: ModuleVersionInfo) -> Tuple[bool, int]:
        order = (
            sort_orders.get(version.start_release_id, -1)
            if version.start_release_id is not None
            else -1
        )
        return (order < draft, order)

    def applied(version: ModuleVersionInfo) -> bool:
        if version.module_vid == keep:
            return True
        published, _ = rank(version)
        return (
            (published or drafts)
            and version.start is not None
            and not is_ghost(version)
        )

    def wins(
        candidate: ModuleVersionInfo, incumbent: ModuleVersionInfo
    ) -> bool:
        if incumbent.module_vid == keep:
            return False
        if candidate.module_vid == keep:
            return True
        return rank(candidate) > rank(incumbent)

    by_start: Dict[date, ModuleVersionInfo] = {}
    for version in filter(applied, versions):
        start = version.start or date.min
        incumbent = by_start.get(start)
        if incumbent is None or wins(version, incumbent):
            by_start[start] = version
    return _cut_overlaps([by_start[start] for start in sorted(by_start)], keep)


def _cut_overlaps(
    ordered: List[ModuleVersionInfo], keep: Optional[int]
) -> List[ModuleVersionInfo]:
    """End each window the day before its successor starts, if later."""
    if not ordered:
        return []
    chain: List[ModuleVersionInfo] = []
    for version, successor in zip(ordered, [*ordered[1:], None], strict=True):
        if successor is None or successor.start is None:
            chain.append(version)
            continue
        cut = successor.start - ONE_DAY
        if version.end is not None and version.end <= cut:
            chain.append(version)
            continue
        if version.module_vid == keep:
            logger.warning(
                "Module version %s %s overlaps its successor %s; its "
                "window is cut on %s",
                version.module_vid,
                version.version_number,
                successor.version_number,
                cut,
            )
        chain.append(replace(version, end=cut))
    return chain


def target_window(window: Window, lag: Optional[RefDateLag]) -> Window:
    """Return the dates a read at ``lag`` lands on from ``window``.

    Args:
        window: The anchor dates, the export's own version window.
        lag: The read's lag; ``None`` lands anywhere.

    Returns:
        The window of target dates.
    """
    if lag is None:
        return (None, None)
    start, end = window
    return (
        lag.target(start) if start is not None else None,
        lag.target(end) if end is not None else None,
    )


def overlaps(version: ModuleVersionInfo, window: Window) -> bool:
    """Whether ``version``'s window shares a date with ``window``."""
    start, end = window
    if end is not None and version.start is not None and version.start > end:
        return False
    return not (
        start is not None and version.end is not None and version.end < start
    )


def reference_window(
    session: "Session", own: Mapping[str, Any], release_id: Optional[int]
) -> Window:
    """Return the reference-date window of the export's own version.

    Read as published (:func:`as_published`), unless the export is
    itself resolved at a working release.

    Args:
        session: SQLAlchemy session.
        own: The export's own module version, as
            :func:`~dpmcore.services.calculations_export.queries.get_module_metadata`
            returns it.
        release_id: Release the export is resolved at.
    """
    sort_orders = load_release_sort_orders(session)
    end = to_date(own["to_date"])
    if not is_working_release(sort_orders, release_id) and (
        is_working_release(sort_orders, own.get("end_release_id"))
    ):
        end = None
    return (to_date(own["from_date"]), end)


def build_modules(
    session: "Session",
    *,
    own: Mapping[str, Any],
    window: Window,
    module_uri: str,
    reads: Sequence[Read],
    operation_codes: Sequence[Optional[str]],
    release_id: Optional[int],
) -> Dict[str, Any]:
    """Build the ``modules`` section of an export.

    Args:
        session: SQLAlchemy session.
        own: The export's own module version, as
            :func:`~dpmcore.services.calculations_export.queries.get_module_metadata`
            returns it.
        window: The own version's window (:func:`reference_window`).
        module_uri: The URI of the export's own version.
        reads: What each statement reads.
        operation_codes: The operation code of each statement.
        release_id: Release the read tables were resolved at.

    Returns:
        ``{module_code: {"versions": [...]}}``, ordered by code.
    """
    return _ModulesBuilder(
        session, own, window, module_uri, operation_codes, release_id
    ).build(reads)


@dataclass
class _ModuleReads:
    """What one module contributes to the export."""

    module_ids: Set[int]
    base_vids: Set[int]
    reads: Dict[Read, None]


class _ModulesBuilder:
    """Assembles ``modules`` for one export."""

    def __init__(
        self,
        session: "Session",
        own: Mapping[str, Any],
        window: Window,
        module_uri: str,
        operation_codes: Sequence[Optional[str]],
        release_id: Optional[int],
    ) -> None:
        """Bind the export's own version and its release."""
        self.session = session
        self.own_vid = int(own["module_vid"])
        self.own_code = own["code"]
        self.own_module_id = own["module_id"]
        self.window = window
        self.module_uri = module_uri
        self.operation_codes = operation_codes
        self.release_id = release_id
        self.sort_orders = load_release_sort_orders(session)
        # Working-release versions are listed only in an export that is
        # itself resolved at a working release.
        self.drafts = is_working_release(self.sort_orders, release_id)
        self._base_vid: Dict[str, int] = {}
        self._key_properties: Dict[int, FrozenSet[int]] = {}
        self._default_types: Set[int] = set()

    def build(self, reads: Sequence[Read]) -> Dict[str, Any]:
        """Return ``modules`` for ``reads``."""
        groups = self._group_by_module(reads)
        modules: Dict[str, Any] = {}
        for code in sorted(groups):
            versions = self._versions(code, groups[code])
            if versions:
                modules[code] = {"versions": versions}
            else:
                logger.warning(
                    "Module %s has no version to list and is left out of "
                    "modules",
                    code,
                )
        if self._default_types:
            ids = sorted(self._default_types)
            logger.warning(
                "%s Variable(s) in modules have no data type and default "
                "to 'm': %s",
                len(ids),
                ", ".join(map(str, ids[:20]))
                + (", ..." if len(ids) > 20 else ""),
            )
        return modules

    def _group_by_module(
        self, reads: Sequence[Read]
    ) -> Dict[str, _ModuleReads]:
        """Assign each read to every module holding its table.

        A table held by several modules is read from whichever is
        provided, so each of them gets the read. A table of the own
        module is read from the own module only, at any lag. The
        export's own module is always there.
        """
        groups: Dict[str, _ModuleReads] = {
            self.own_code: _ModuleReads({self.own_module_id}, set(), {})
        }
        codes = list(dict.fromkeys(read.table for read in reads))
        self._base_vid = windowed_table_vids(
            self.session, codes, self.release_id
        )
        dropped = [code for code in codes if code not in self._base_vid]
        if dropped:
            # The operands come from each table's live version, which
            # need not exist at the export's release.
            logger.warning(
                "%s table(s) read have no version at the export's release "
                "and are left out of modules: %s",
                len(dropped),
                ", ".join(sorted(dropped)),
            )
        holders = modules_of_table_vids(
            self.session, set(self._base_vid.values()), self.release_id
        )
        for read in reads:
            table_vid = self._base_vid.get(read.table)
            if table_vid is None:
                continue
            rows = holders.get(table_vid, [])
            own = [r for r in rows if r.module_id == self.own_module_id]
            for row in own or rows:
                group = groups.setdefault(
                    row.module_code, _ModuleReads(set(), set(), {})
                )
                group.module_ids.add(int(row.module_id))
                group.base_vids.add(int(row.module_vid))
                group.reads[read] = None
        return groups

    def _versions(
        self, code: str, group: _ModuleReads
    ) -> List[Dict[str, Any]]:
        """Return the ``versions`` of one module."""
        is_own = code == self.own_code
        every = _module_versions(self.session, group.module_ids)
        chain = version_chain(
            every,
            self.sort_orders,
            keep=self.own_vid if is_own else None,
            drafts=self.drafts,
        )
        lags = {read.lag for read in group.reads}
        if is_own:
            lags.add(AT_T)
        targets = [target_window(self.window, lag) for lag in lags]
        listed = [
            version
            for version in chain
            if any(overlaps(version, target) for target in targets)
        ]
        fallback = not listed
        if fallback:
            # Nothing it holds can be read on the export's dates; the
            # versions the tables were resolved in still describe them,
            # unless they never applied.
            listed = [v for v in chain if v.module_vid in group.base_vids]
            if listed:
                logger.warning(
                    "No version of module %s covers a date its reads land "
                    "on; listing %s",
                    code,
                    ", ".join(str(v.version_number) for v in listed),
                )

        entries: List[Dict[str, Any]] = []
        for version in listed:
            here = (
                list(group.reads)
                if fallback
                else [
                    read
                    for read in group.reads
                    if overlaps(version, target_window(self.window, read.lag))
                ]
            )
            entry = self._version_entry(version, here)
            if entry is not None:
                entries.append(entry)
        return entries

    def _version_entry(
        self, version: ModuleVersionInfo, reads: Sequence[Read]
    ) -> Optional[Dict[str, Any]]:
        """Return one ``versions[]`` entry, ``None`` when it has no URI."""
        is_own = version.module_vid == self.own_vid
        uri = self.module_uri if is_own else self._uri(version)
        if uri is None:
            return None

        holders = _variable_holders(
            self.session,
            version.module_vid,
            {var for read in reads for var in read.variable_ids},
        )
        self._load_key_properties(
            [vid for tables in holders.values() for vid in tables]
            + [self._base_vid[read.table] for read in reads]
        )
        read_tables: Dict[int, Set[int]] = {}
        table_codes: Dict[int, str] = {}
        failing: Set[int] = set()
        for read in reads:
            reference = self._key_properties[self._base_vid[read.table]]
            for variable_id in read.variable_ids:
                tables = holders.get(variable_id, {})
                table_codes.update(tables)
                matching = {
                    vid
                    for vid in tables
                    if self._key_properties[vid] == reference
                }
                same_code = {
                    vid for vid, code in tables.items() if code == read.table
                }
                for vid in (same_code & matching) or matching or same_code:
                    read_tables.setdefault(vid, set()).add(variable_id)
                if not matching:
                    # R4: a Variable it reads is not in this version, or
                    # only in a table whose open keys differ.
                    failing.add(read.statement)

        listed: Mapping[int, Optional[Set[int]]] = read_tables
        if is_own:
            # The own version describes every table and Variable.
            composition = _composition(self.session, version.module_vid)
            table_codes.update(composition)
            listed = dict.fromkeys(composition)

        entry: Dict[str, Any] = {
            "version": version.version_number,
            "URI": uri,
            "from": _date_text(version.start),
            "to": _date_text(version.end),
            "tables": self._tables(version, listed, table_codes),
        }
        not_evaluable = sorted(
            {
                code
                for statement in failing
                if (code := self.operation_codes[statement]) is not None
            }
        )
        if not_evaluable:
            entry["not_evaluable"] = not_evaluable
            logger.info(
                "%s %s cannot serve %s",
                version.module_vid,
                version.version_number,
                ", ".join(not_evaluable),
            )
        return entry

    def _uri(self, version: ModuleVersionInfo) -> Optional[str]:
        """Return a dependency version's URI, ``None`` when unusable."""
        try:
            uri, _ = get_module_uri(self.session, version.module_vid)
        except NotFound:
            logger.warning(
                "Module version %s %s has no URI and is left out of modules",
                version.module_vid,
                version.version_number,
            )
            return None
        if uri == self.module_uri:
            # Exactly one version carries module_uri: the export's own.
            logger.warning(
                "Module version %s %s resolves to the export's own URI "
                "(%s) and is left out of modules",
                version.module_vid,
                version.version_number,
                uri,
            )
            return None
        return uri

    def _load_key_properties(self, table_vids: Iterable[int]) -> None:
        """Fetch the open-key properties of the tables not seen yet."""
        missing = sorted(
            {vid for vid in table_vids if vid not in self._key_properties}
        )
        if missing:
            self._key_properties.update(
                get_open_key_properties(self.session, missing)
            )

    def _tables(
        self,
        version: ModuleVersionInfo,
        listed: Mapping[int, Optional[Set[int]]],
        table_codes: Mapping[int, str],
    ) -> Dict[str, Dict[str, Any]]:
        """Describe the tables of ``version`` the export reads.

        Args:
            version: The module version.
            listed: ``{table_vid: VariableIDs}``; ``None`` lists every
                Variable of the table.
            table_codes: ``{table_vid: table code}``.

        Returns:
            ``{table code: {"variables": {...}, "open_keys": {...}}}``,
            ordered by code. Open keys are named as of the version's
            own release. A table without Variables, such as an abstract
            one, is left out.
        """
        if not listed:
            return {}
        release = version.start_release_id
        if release is not None and release not in self.sort_orders:
            release = None
        codes = sorted({table_codes[vid] for vid in listed})
        open_keys = get_open_keys_for_tables(
            self.session, codes, release_id=release, table_vids=list(listed)
        )
        tables: Dict[str, Dict[str, Any]] = {}
        for vid in sorted(listed, key=lambda v: (table_codes[v], v)):
            code = table_codes[vid]
            cells = ViewDatapointsQuery.get_table_version_cells(
                self.session, code, [vid]
            )
            entry = tables.setdefault(
                code, {"variables": {}, "open_keys": open_keys.get(code, {})}
            )
            entry["variables"].update(self._variables(cells, listed[vid]))
        for entry in tables.values():
            entry["variables"] = dict(
                sorted(entry["variables"].items(), key=lambda kv: int(kv[0]))
            )
        return {
            code: entry for code, entry in tables.items() if entry["variables"]
        }

    def _variables(
        self, cells: pd.DataFrame, wanted: Optional[Set[int]]
    ) -> Dict[str, Dict[str, Any]]:
        """Return ``{VariableID: {data_type, cells}}`` from a cell frame.

        Each cell names only the axes it fixes; a Variable the DPM places
        in two cells of the table lists both.
        """
        cells = cells[cells["variable_id"].notna()]
        variables: Dict[str, Dict[str, Any]] = {}
        for raw_id, rows in cells.groupby("variable_id", sort=True):
            variable_id = int(cast(float, raw_id))
            if wanted is not None and variable_id not in wanted:
                continue
            data_types = rows["data_type"].dropna()
            if data_types.empty:
                self._default_types.add(variable_id)
            positions: List[Dict[str, str]] = []
            for record in rows.to_dict(orient="records"):
                cell = {
                    axis: str(record[column])
                    for axis, column in _AXES
                    if not pd.isna(record[column])
                }
                if cell not in positions:
                    positions.append(cell)
            positions.sort(key=lambda c: tuple(c.get(a, "") for a, _ in _AXES))
            variables[str(variable_id)] = {
                "data_type": (
                    str(data_types.iloc[0]) if not data_types.empty else "m"
                ),
                "cells": positions,
            }
        return variables


def _date_text(value: Optional[date]) -> Optional[str]:
    """Render a window bound, ``None`` passing through."""
    return str(value) if value is not None else None


def _module_versions(
    session: "Session", module_ids: Iterable[int]
) -> List[ModuleVersionInfo]:
    """Return every version of the given Modules, unfiltered.

    Not release-windowed: a superseded version is closed, yet it is the
    one the earlier data was reported under.
    """
    ids = sorted({int(module_id) for module_id in module_ids})
    if not ids:
        return []
    rows = (
        session.query(
            ModuleVersion.module_vid,
            ModuleVersion.version_number,
            ModuleVersion.from_reference_date,
            ModuleVersion.to_reference_date,
            ModuleVersion.start_release_id,
            ModuleVersion.end_release_id,
        )
        .filter(ModuleVersion.module_id.in_(ids))
        .order_by(ModuleVersion.module_vid)
        .all()
    )
    return [
        ModuleVersionInfo(
            module_vid=int(row.module_vid),
            version_number=row.version_number,
            start=to_date(row.from_reference_date),
            end=to_date(row.to_reference_date),
            start_release_id=(
                int(row.start_release_id)
                if row.start_release_id is not None
                else None
            ),
            end_release_id=(
                int(row.end_release_id)
                if row.end_release_id is not None
                else None
            ),
        )
        for row in rows
    ]


def _variable_holders(
    session: "Session", module_vid: int, variable_ids: Set[int]
) -> Dict[int, Dict[int, str]]:
    """Return where each Variable sits in Module Version ``module_vid``.

    Only the Variables asked for are looked up: the module's other
    tables are never loaded.

    Returns:
        ``{VariableID: {TableVID: table code}}`` over non-void cells.
    """
    if not variable_ids:
        return {}
    query = (
        session.query(
            VariableVersion.variable_id.label("variable_id"),
            TableVersion.table_vid.label("table_vid"),
            TableVersion.code.label("code"),
        )
        .select_from(ModuleVersionComposition)
        .join(
            TableVersion,
            TableVersion.table_vid == ModuleVersionComposition.table_vid,
        )
        .join(
            TableVersionCell,
            TableVersionCell.table_vid == TableVersion.table_vid,
        )
        .join(
            VariableVersion,
            VariableVersion.variable_vid == TableVersionCell.variable_vid,
        )
        .filter(
            ModuleVersionComposition.module_vid == int(module_vid),
            TableVersionCell.is_void == False,  # noqa: E712
        )
        .distinct()
    )
    holders: Dict[int, Dict[int, str]] = {}
    for row in chunked_in(
        query, VariableVersion.variable_id, sorted(variable_ids)
    ):
        holders.setdefault(int(row.variable_id), {})[int(row.table_vid)] = (
            row.code
        )
    return holders


def _composition(session: "Session", module_vid: int) -> Dict[int, str]:
    """Return ``{TableVID: table code}`` of every table of a module version."""
    rows = (
        session.query(TableVersion.table_vid, TableVersion.code)
        .join(
            ModuleVersionComposition,
            ModuleVersionComposition.table_vid == TableVersion.table_vid,
        )
        .filter(ModuleVersionComposition.module_vid == int(module_vid))
        .all()
    )
    return {int(row.table_vid): row.code for row in rows if row.code}
