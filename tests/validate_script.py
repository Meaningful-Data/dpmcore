#!/usr/bin/env python3
"""Reference validator for DPM-XL Script Documents, format 2.0.

Checks a Script Document against the validation rules of the Script Format
specification, chapter 6.2. Uses only the Python standard library; no DPM
database or taxonomy is required, because every rule is checkable from the
document alone.

Usage:
    python validate_script.py FILE [FILE ...]
    python validate_script.py --json FILE
    python validate_script.py --quiet FILE      # exit code only

Exit codes:
    0   every document is valid
    1   at least one document violates at least one rule
    2   a document could not be read or parsed
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

# --------------------------------------------------------------------------
# Tables from the specification
# --------------------------------------------------------------------------

#: §2.1 — the fourteen members of the Module Object, in order.
MODULE_MEMBERS = (
    "owner", "module_code", "module_version", "module_owner", "module_uri",
    "framework_code", "format_version", "dpm_release", "dates",
    "operations", "preconditions", "modules", "parameters", "dependency_groups",
)

#: §3.1 — the members of an Operation Object.
OPERATION_MEMBERS = frozenset({
    "code", "version_id", "expression", "root_operator_id", "ast",
    "severity", "from_submission_date",
})

#: §3.2 — the members of a precondition entry.
PRECONDITION_MEMBERS = frozenset({"code", "version_id", "ast",
                                  "affected_operations"})

#: §3.3.1 — the members of a module version; the last two are optional.
VERSION_MEMBERS = frozenset({"version", "URI", "from", "to", "tables"})
VERSION_OPTIONAL = frozenset({"filing_indicators", "not_evaluable"})

#: §3.3.2 — the members of a table and the axes a cell may fix.
TABLE_MEMBERS = frozenset({"variables", "open_keys"})
CELL_AXES = frozenset({"row", "column", "sheet"})

#: §5.1, §5.2 — the members of a Dependency Group and its operators.
GROUP_MEMBERS = frozenset({"requires", "validations"})
BINARY_OPERATORS = ("and", "or", "xor")
DECIDED_BY = frozenset({"condition", "scope"})

#: §5.3, §5.4 — the units of a module reference, in canonical order.
UNITS = "ASQMWD"

#: §3.4 — the six Module Parameter types.
PARAMETER_TYPES = frozenset({"Number", "Integer", "String", "Date",
                             "Boolean", "Item"})

#: §4.8.1 — the JSON type a scalar `param_type` requires of `default`.
#: "Item" is checked separately, see _matches_declared_type().
PARAMETER_DEFAULT_TYPES = {"Integer": int, "Number": float, "Boolean": bool,
                           "String": str, "Date": str}

#: §3.1.2 — permitted severities.
SEVERITIES = frozenset({"error", "warning", "info"})

#: §3.3.3 — permitted Data Type codes (DataType.Code in DPM-ML).
DATA_TYPES = frozenset({"i", "r", "s", "es", "b", "t", "e", "m", "p", "d",
                        "dt", "u", "o"})

#: §4.1.2 — Node classes and their permitted members, excluding `class_name`.
NODE_MEMBERS = {
    "FactVarID": frozenset({"table", "interval", "default", "data"}),
    "FilingIndicatorVarID": frozenset({"code", "variable_id"}),
    "Constant": frozenset({"type_", "value"}),
    "Scalar": frozenset({"item", "scalar_type"}),
    "Set": frozenset({"children"}),
    "Dimension": frozenset({"dimension_code"}),
    "ParExpr": frozenset({"expression"}),
    "UnaryOp": frozenset({"op", "operand"}),
    "BinOp": frozenset({"op", "left", "right"}),
    "ComplexNumericOp": frozenset({"op", "operands"}),
    "SetOp": frozenset({"op", "operands"}),
    "SubstrOp": frozenset({"op", "operand", "start", "length"}),
    "DateConstructorOp": frozenset({"op", "year_node", "month_node", "day_node"}),
    "AnnualiseOp": frozenset({"op", "operand", "fy_end", "component"}),
    "AggregationOp": frozenset({"op", "operand", "grouping_clause",
                                "analytic_clause"}),
    "GroupingClause": frozenset({"components"}),
    "AnalyticClause": frozenset({"partition_by", "order_by", "window"}),
    "WhereClauseOp": frozenset({"operand", "condition"}),
    "SubClauseOp": frozenset({"operand", "condition"}),
    "GetClauseOp": frozenset({"operand", "component"}),
    "RenameClauseOp": frozenset({"operand", "clauses"}),
    "FilterOp": frozenset({"selection", "condition"}),
    "CondExpr": frozenset({"condition", "then_expr", "else_expr"}),
    "ParameterRef": frozenset({"code", "param_type", "default"}),
    "TimeShiftOp": frozenset({"operand", "period_indicator", "shift_number",
                              "reference_period"}),
}

#: §4.1.3 — members whose absence is significant, so V-5 must not require them.
OPTIONAL_MEMBERS = {
    "FactVarID": frozenset({"default"}),
    "CondExpr": frozenset({"else_expr"}),
    "SubstrOp": frozenset({"start", "length"}),
    "ParameterRef": frozenset({"default"}),
}

#: §4.3.1 — the members of a Datapoint Reference.
ENTRY_MEMBERS = frozenset({"datapoint", "operand_reference_id", "x", "y", "z"})

#: §4.11, §4.12, §4.14, §4.18 — permitted `op` values per class.
#: §4.11 — the six date-component extractors share one Node shape.
DATE_COMPONENTS = frozenset({"year", "semester", "quarter", "month", "week",
                             "day"})

OPS = {
    "UnaryOp": frozenset({"+", "-", "abs", "sqrt", "exp", "ln", "isnull",
                          "not", "len"}) | DATE_COMPONENTS,
    "BinOp": frozenset({"+", "-", "*", "/", "power", "log", "nvl", "&",
                        "=", "!=", "<", "<=", ">", ">=", "match", "in",
                        "and", "or", "xor"}),
    "ComplexNumericOp": frozenset({"min", "max"}),
    "SetOp": frozenset({"set_of", "union", "intersect", "setdiff", "symdiff"}),
    "SubstrOp": frozenset({"substr"}),
    "DateConstructorOp": frozenset({"date"}),
    "AnnualiseOp": frozenset({"annualise"}),
    "AggregationOp": frozenset({"sum", "count", "avg", "median", "max_aggr",
                                "min_aggr", "rank"}),
}

#: §4.14 — (minimum, maximum) arity of each SetOp `op`; None means unbounded.
SETOP_ARITY = {"set_of": (1, 1), "union": (2, None), "intersect": (2, None),
               "setdiff": (2, 2), "symdiff": (2, 2)}

#: §4.20 — permitted window frame types and bound kinds.
WINDOW_FRAME_TYPES = frozenset({"data_points", "range"})
WINDOW_BOUND_TYPES = frozenset({"unbounded_preceding", "n_preceding",
                                "current_data_point", "n_following",
                                "unbounded_following"})
#: Window order, unbounded_preceding (most preceding) to unbounded_following.
WINDOW_BOUND_ORDER = {"unbounded_preceding": 0, "n_preceding": 1,
                      "current_data_point": 2, "n_following": 3,
                      "unbounded_following": 4}
WINDOW_N_BOUND_TYPES = frozenset({"n_preceding", "n_following"})

#: §4.1.2 — Nodes denoting data or literals rather than Operator applications.
OPERAND_CLASSES = frozenset({"FactVarID", "FilingIndicatorVarID", "Constant",
                             "Scalar", "Set", "Dimension", "ParameterRef"})

#: §4.2 — (class_name, op) -> OperatorID. `op` is None for single-Operator classes.
OPERATOR_IDS = {
    ("UnaryOp", "+"): 1, ("BinOp", "+"): 2, ("BinOp", "/"): 3,
    ("UnaryOp", "-"): 4, ("BinOp", "-"): 5, ("UnaryOp", "abs"): 6,
    ("ComplexNumericOp", "min"): 7, ("BinOp", "*"): 8,
    ("ComplexNumericOp", "max"): 9, ("BinOp", "="): 13, ("BinOp", "<="): 14,
    ("BinOp", ">="): 15, ("BinOp", "in"): 16, ("UnaryOp", "isnull"): 17,
    ("BinOp", ">"): 18, ("BinOp", "<"): 19, ("BinOp", "!="): 20,
    ("BinOp", "and"): 22, ("BinOp", "or"): 23, ("UnaryOp", "not"): 24,
    ("UnaryOp", "sqrt"): 10, ("BinOp", "match"): 21, ("BinOp", "xor"): 25,
    ("AggregationOp", "max_aggr"): 11, ("AggregationOp", "min_aggr"): 12,
    ("AggregationOp", "sum"): 26, ("AggregationOp", "count"): 27,
    ("WhereClauseOp", None): 28, ("GetClauseOp", None): 29,
    ("CondExpr", None): 30, ("FilterOp", None): 31, ("TimeShiftOp", None): 32,
    ("RenameClauseOp", None): 33, ("GroupingClause", None): 35,
    ("ParExpr", None): 37, ("SubClauseOp", None): 38,
}

#: §4.4 — Constant.type_ -> permitted JSON type of Constant.value.
CONSTANT_TYPES = {"Integer": int, "Number": float, "Boolean": bool,
                  "String": str, "Date": str, "Null": type(None)}

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ABSOLUTE_URI = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://\S+$")

#: §4.7, §4.23 — codes that name no Open Key and need no declaration.
RESERVED_COMPONENTS = frozenset({"f", "entityID", "baseCurrency", "refPeriod"})

#: §4.1.5 — sentinel for an index set whose cardinality is data-dependent and
#: therefore not statically determinable (a grouped aggregation).
OPAQUE = "OPAQUE"


class Report:
    """Collects violations keyed by rule identifier."""

    def __init__(self) -> None:
        self.violations: dict[str, list[str]] = defaultdict(list)
        self.unverified = 0

    def fail(self, rule: str, detail: str) -> None:
        self.violations[rule].append(detail)

    @property
    def count(self) -> int:
        return sum(len(v) for v in self.violations.values())

    @property
    def valid(self) -> bool:
        return self.count == 0

    def rules(self) -> list[str]:
        return sorted(self.violations, key=lambda r: int(r.split("-")[1]))


# --------------------------------------------------------------------------
# Tree traversal
# --------------------------------------------------------------------------

def child_nodes(node):
    """Yield (member_name, child_node) for each Node directly beneath `node`."""
    for key, value in node.items():
        if key == "class_name":
            continue
        if isinstance(value, dict) and "class_name" in value:
            yield key, value
        elif isinstance(value, list):
            for element in value:
                if isinstance(element, dict) and "class_name" in element:
                    yield key, element


def walk(node, parent=None, member=None):
    """Yield (node, parent, member_name) for `node` and every descendant."""
    yield node, parent, member
    for key, child in child_nodes(node):
        yield from walk(child, node, key)


def axes_of(index_set_):
    """§4.1.5 — the axes on which the indices of a set carry a component."""
    present = set()
    for position in index_set_:
        for slot, axis in enumerate("xyz"):
            if position[slot] is not None:
                present.add(axis)
    return frozenset(present)


def project(index_set_, axes):
    """§4.1.5 — the projection of an index set onto `axes`."""
    slots = [slot for slot, axis in enumerate("xyz") if axis in axes]
    return frozenset(tuple(position[slot] for slot in slots)
                     for position in index_set_)


def index_set(node, report: Report, where: str):
    """Return the Position Index set of `node` per §4.1.5, or OPAQUE.

    Reports a V-17 violation for any ill-formed Operator encountered.
    """
    cls = node["class_name"]

    if cls == "FactVarID":
        return frozenset((d.get("x"), d.get("y"), d.get("z"))
                         for d in node["data"])
    if cls in OPERAND_CLASSES:
        return frozenset()
    if cls == "ParExpr":
        return index_set(node["expression"], report, where)
    if cls == "UnaryOp":
        return index_set(node["operand"], report, where)
    if cls in ("WhereClauseOp", "SubClauseOp", "TimeShiftOp",
               "RenameClauseOp", "GetClauseOp", "SubstrOp", "AnnualiseOp"):
        return index_set(node["operand"], report, where)
    if cls == "FilterOp":
        return index_set(node["selection"], report, where)
    if cls == "SetOp":
        # §4.1.5 — the result is a Scalar Set, which carries no positions.
        for operand in node["operands"]:
            index_set(operand, report, where)
        return frozenset()
    if cls == "AggregationOp":
        inner = index_set(node["operand"], report, where)
        if node.get("analytic_clause") is not None:
            return inner                # analytic: one value per input Record
        if node.get("grouping_clause") is None:
            return frozenset()          # reduced to a Scalar
        return OPAQUE                   # one index per group, data-dependent

    # A malformed Node must be reported by V-5, not crash the walk, so every
    # operand is fetched defensively and missing ones are skipped.
    if cls == "DateConstructorOp":
        operands = [node.get("year_node"), node.get("month_node"),
                    node.get("day_node")]
    elif cls == "ComplexNumericOp":
        operands = node.get("operands") or []
    elif cls == "BinOp":
        operands = [node.get("left"), node.get("right")]
    elif cls == "CondExpr":
        operands = [node[k] for k in ("condition", "then_expr", "else_expr")
                    if node.get(k) is not None]
    elif cls == "ParameterRef":
        return frozenset()
    else:
        return frozenset()

    operands = [o for o in operands
                if isinstance(o, dict) and "class_name" in o]
    if not operands:
        return frozenset()

    sets = [index_set(o, report, where) for o in operands]
    if any(s is OPAQUE for s in sets):
        report.unverified += 1
        return OPAQUE

    # §4.1.5: S is the set of non-empty operand index sets. Operands combine by
    # natural join on the axes they share, so it is the axes that must line up,
    # not the arity.
    distinct = {s for s in sets if s}
    if not distinct:                                        # case 1: Scalar
        return frozenset()

    widest = max(distinct, key=lambda s: len(axes_of(s)))
    for operand_set in distinct:
        axes = axes_of(operand_set)
        if not axes <= axes_of(widest):                     # case 5
            report.fail("V-17", f"{where}: operand axes "
                                f"{sorted(axes)} and {sorted(axes_of(widest))} "
                                f"have no common widest operand")
            return OPAQUE
        if project(widest, axes) != project(operand_set, axes):
            report.fail("V-17", f"{where}: operands disagree on axes "
                                f"{sorted(axes) or ['(none)']} — "
                                f"{len(project(operand_set, axes))} position(s) "
                                f"against {len(project(widest, axes))}")
            return OPAQUE
    return widest


# --------------------------------------------------------------------------
# Rule checks
# --------------------------------------------------------------------------

def is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def is_date(value) -> bool:
    return isinstance(value, str) and bool(ISO_DATE.match(value))


class Context:
    """What the tree checks need to know about `modules` and `parameters`."""

    def __init__(self, module) -> None:
        self.module_code = module["module_code"]
        self.parameters = module["parameters"]
        #: table code -> the table objects of every version listing it (§3.3.2)
        self.tables: dict[str, list[dict]] = defaultdict(list)
        #: table code -> the module codes whose versions list it
        self.table_modules: dict[str, set[str]] = defaultdict(set)
        #: (filing indicator code, variable_id) -> the module codes declaring it
        self.indicators: dict[tuple, set[str]] = defaultdict(set)
        #: table codes of the own version (§3.3.1)
        self.own_tables: set[str] = set()
        #: §4.3.3 — operand_reference_id -> the (table, datapoint) it denotes
        self.cell_of_ref: dict = {}
        #: (tree label, filing indicator code, variable_id) of every
        #: FilingIndicatorVarID (§4.9)
        self.indicator_reads: list[tuple] = []

    def open_keys(self, table_code: str) -> set[str]:
        keys: set[str] = set()
        for table in self.tables.get(table_code, []):
            keys |= set(table.get("open_keys") or {})
        return keys

    def is_variable(self, table_code: str, datapoint) -> bool:
        return any(str(datapoint) in (table.get("variables") or {})
                   for table in self.tables.get(table_code, []))



def check_document(module, path: Path, report: Report) -> None:
    # V-2 — the fourteen members, in order, and no other (§2.1).
    members = list(module)
    missing = [m for m in MODULE_MEMBERS if m not in module]
    extra = [m for m in members if m not in MODULE_MEMBERS]
    if missing:
        report.fail("V-2", f"missing member(s): {missing}")
    if extra:
        report.fail("V-2", f"unrecognised member(s): {extra}")
    if missing:
        return
    if not extra and members != list(MODULE_MEMBERS):
        report.fail("V-2", f"members out of order: {members}")
    version = str(module["format_version"])
    if not re.match(r"^\d+\.\d+$", version):
        report.fail("V-2", f"format_version {version!r} is not MAJOR.MINOR")
    elif version.split(".")[0] != "2":
        report.fail("V-2", f"format_version {version!r} is not a 2.x version")

    # V-45 — identity and file name (§2.2, §2.3).
    for member in ("owner", "module_owner", "framework_code"):
        if not isinstance(module[member], str) or not module[member]:
            report.fail("V-45", f"{member} {module[member]!r} is not a "
                                f"non-empty code")
    if not isinstance(module["module_uri"], str) \
            or not ABSOLUTE_URI.match(module["module_uri"]):
        report.fail("V-45", f"module_uri {module['module_uri']!r} is not an "
                            f"absolute URI")
    expected = f"{module['owner']}-{module['module_code']}-{module['module_version']}.json"
    if path.name != expected:
        report.fail("V-45", f"file name {path.name!r}, expected {expected!r}")

    ctx = Context(module)
    check_dates(module, report)
    check_modules(module, ctx, report)

    # V-41 — scalar Parameter types only (§3.4).
    for name, declared in sorted(module["parameters"].items()):
        if declared not in PARAMETER_TYPES:
            report.fail("V-41", f"parameters/{name}: type {declared!r} is not "
                                f"one of the six scalar types of §3.4")

    operations = module["operations"]
    for code, operation in sorted(operations.items()):
        check_operation(code, operation, ctx, report)
    check_preconditions(module, operations, ctx, report)
    check_groups(module, operations, ctx, report)


def check_dates(module, report: Report) -> None:
    # V-18
    dates = module["dates"]
    if not isinstance(dates, dict) or set(dates) != {"from", "to"}:
        report.fail("V-18", f"dates {dates!r} needs exactly `from` and `to`")
        return
    check_period("dates", dates["from"], dates["to"], report)
    release = module["dpm_release"]
    if not isinstance(release, dict) or set(release) != {"release", "publication_date"}:
        report.fail("V-2", f"dpm_release {release!r} needs exactly `release` "
                           f"and `publication_date`")
    elif not is_date(release["publication_date"]):
        report.fail("V-18", f"dpm_release.publication_date "
                            f"{release['publication_date']!r}")
    for code, operation in module["operations"].items():
        if not is_date(operation.get("from_submission_date")):
            report.fail("V-18", f"{code}: from_submission_date "
                                f"{operation.get('from_submission_date')!r}")


def check_period(label, start, end, report: Report) -> bool:
    """V-18 — a `from`/`to` pair of dates; `to` may be null."""
    ok = True
    if not is_date(start):
        report.fail("V-18", f"{label}: from {start!r}")
        ok = False
    if end is not None:
        if not is_date(end):
            report.fail("V-18", f"{label}: to {end!r}")
            ok = False
        elif ok and end < start:
            report.fail("V-18", f"{label}: to {end} < from {start}")
            ok = False
    return ok


def check_modules(module, ctx: Context, report: Report) -> None:
    modules = module["modules"]
    operations = module["operations"]
    own = []
    types: dict[str, str] = {}

    for code, entry in sorted(modules.items()):
        if not isinstance(entry, dict) or set(entry) != {"versions"} \
                or not isinstance(entry["versions"], list) or not entry["versions"]:
            report.fail("V-35", f"modules/{code}: needs exactly a non-empty "
                                f"`versions` list")
            continue
        versions = entry["versions"]
        windows_ok = True
        for position, version in enumerate(versions):
            label = f"modules/{code}/{version.get('version')}"
            missing = VERSION_MEMBERS - set(version)
            extra = set(version) - VERSION_MEMBERS - VERSION_OPTIONAL
            if missing or extra:
                report.fail("V-35", f"{label}: missing {sorted(missing)}, "
                                    f"unrecognised {sorted(extra)}")
                windows_ok = False
                continue
            if not check_period(label, version["from"], version["to"], report):
                windows_ok = False
            elif version["from"] == version["to"]:
                report.fail("V-35", f"{label}: from equals to, a one-day "
                                    f"version is never listed")
            if version["to"] is None and position != len(versions) - 1:
                report.fail("V-35", f"{label}: open-ended but not the last version")
            if version["URI"] == module["module_uri"]:
                own.append((code, version))
            check_tables(label, code, version, ctx, types, report)
            check_indicators(label, code, version, ctx, report)
            not_evaluable = version.get("not_evaluable")
            if not_evaluable is not None:
                if not isinstance(not_evaluable, list) or not not_evaluable:
                    report.fail("V-35", f"{label}: empty not_evaluable")
                else:
                    unknown = [c for c in not_evaluable if c not in operations]
                    if unknown:
                        report.fail("V-35", f"{label}: not_evaluable names "
                                            f"{unknown}, not in `operations`")
        if windows_ok:
            for before, after in zip(versions, versions[1:]):
                if before["to"] is None or before["to"] >= after["from"]:
                    report.fail("V-35", f"modules/{code}: {before['version']} and "
                                        f"{after['version']} out of order or "
                                        f"overlapping")

    # V-34 — the own version (§3.3.1).
    if len(own) != 1:
        report.fail("V-34", f"{len(own)} version(s) have module_uri as URI, "
                            f"expected 1")
        return
    code, version = own[0]
    if code != module["module_code"]:
        report.fail("V-34", f"own version is under modules/{code}, expected "
                            f"{module['module_code']}")
    if version["version"] != module["module_version"]:
        report.fail("V-34", f"own version is {version['version']}, expected "
                            f"{module['module_version']}")
    dates = module["dates"]
    if isinstance(dates, dict) and (version["from"], version["to"]) \
            != (dates.get("from"), dates.get("to")):
        report.fail("V-34", f"own version window {version['from']}..{version['to']} "
                            f"differs from `dates`")
    if not version.get("filing_indicators"):
        report.fail("V-34", "own version has no filing_indicators")
    ctx.own_tables = set(version.get("tables") or {})


def check_tables(label, module_code, version, ctx: Context, types, report: Report) -> None:
    tables = version["tables"]
    if not isinstance(tables, dict):
        report.fail("V-35", f"{label}: `tables` is not an object")
        return
    for table_code, table in sorted(tables.items()):
        where = f"{label}/{table_code}"
        if not isinstance(table, dict) or set(table) != TABLE_MEMBERS:
            report.fail("V-35", f"{where}: a table has exactly `variables` "
                                f"and `open_keys`")
            continue
        ctx.tables[table_code].append(table)
        ctx.table_modules[table_code].add(module_code)
        for key, code in table["open_keys"].items():
            if code not in DATA_TYPES:
                report.fail("V-42", f"{where}: open key {key} has Data Type "
                                    f"{code!r}")
        for var_id, variable in table["variables"].items():
            # V-47 — {data_type, cells: [{row?, column?, sheet?}, ...]}
            cells = variable.get("cells") if isinstance(variable, dict) else None
            if not isinstance(variable, dict) or set(variable) != {"data_type", "cells"} \
                    or not isinstance(cells, list) or not cells \
                    or any(not isinstance(c, dict) or not c or set(c) - CELL_AXES
                           for c in cells) \
                    or len({json.dumps(c, sort_keys=True) for c in cells}) != len(cells):
                report.fail("V-47", f"{where}/{var_id}: not {{data_type, cells}} "
                                    f"with a non-empty list of distinct cells")
                continue
            # V-42 — one Data Type per VariableID (§3.3.3).
            data_type = variable["data_type"]
            if data_type not in DATA_TYPES:
                report.fail("V-42", f"{where}/{var_id}: unknown Data Type "
                                    f"{data_type!r}")
            elif types.setdefault(var_id, data_type) != data_type:
                report.fail("V-42", f"Variable {var_id}: Data Types "
                                    f"{types[var_id]!r} and {data_type!r}")


def check_indicators(label, module_code, version, ctx: Context, report: Report) -> None:
    indicators = version.get("filing_indicators")
    if indicators is None:
        return
    if not isinstance(indicators, dict) or not indicators:
        report.fail("V-35", f"{label}: empty filing_indicators")
        return
    for code, entry in sorted(indicators.items()):
        if not isinstance(entry, dict) or set(entry) != {"variable_id", "data_type"} \
                or not is_int(entry["variable_id"]) \
                or entry["data_type"] not in DATA_TYPES:
            report.fail("V-44", f"{label}: filing indicator {code} needs an "
                                f"integer variable_id and a data_type")
            continue
        ctx.indicators[(code, entry["variable_id"])].add(module_code)


def check_operation(code, operation, ctx: Context, report: Report) -> None:
    # V-3
    if operation.get("code") != code:
        report.fail("V-3", f"operations/{code}: code member is "
                           f"{operation.get('code')!r}")
    if set(operation) != OPERATION_MEMBERS:
        missing = OPERATION_MEMBERS - set(operation)
        extra = set(operation) - OPERATION_MEMBERS
        if missing:
            report.fail("V-3", f"operations/{code}: missing {sorted(missing)}")
        if extra:
            report.fail("V-3", f"operations/{code}: unrecognised "
                               f"{sorted(extra)}")
        if "ast" in missing:
            return
    # V-19
    if operation.get("severity") not in SEVERITIES:
        report.fail("V-19", f"{code}: severity {operation.get('severity')!r}")

    root = operation["ast"]

    # V-25
    if root["class_name"] in OPERAND_CLASSES:
        report.fail("V-25", f"{code}: root Node is an Operand "
                            f"({root['class_name']})")
    # V-4 — only where the root Node encodes a DPM-ML Operator (§4.2.1).
    expected = OPERATOR_IDS.get((root["class_name"], root.get("op")))
    if expected is not None and expected != operation.get("root_operator_id"):
        report.fail("V-4", f"{code}: root_operator_id "
                           f"{operation.get('root_operator_id')}, "
                           f"root Node implies {expected}")

    check_tree(code, root, ctx, report, precondition=False)


def check_tree(code, root, ctx: Context, report: Report, precondition: bool) -> None:
    """Per-Node rules, applied identically to an Operation and a precondition.

    §3.2 — a precondition tree is an Operation tree, so every rule that
    governs the Nodes of one governs the Nodes of the other.
    """
    for node, parent, member in walk(root):
        cls = node["class_name"]
        # V-5
        if cls not in NODE_MEMBERS:
            report.fail("V-5", f"{code}: unrecognised class_name {cls!r}")
            continue
        extra = set(node) - {"class_name"} - NODE_MEMBERS[cls]
        if cls == "FactVarID":
            extra -= CELL_AXES          # reported by V-46 instead
        if extra:
            report.fail("V-5", f"{code}/{cls}: unrecognised member(s) "
                               f"{sorted(extra)}")
        required = NODE_MEMBERS[cls] - set(node) - OPTIONAL_MEMBERS.get(cls, frozenset())
        if required:
            report.fail("V-5", f"{code}/{cls}: missing member(s) "
                               f"{sorted(required)}")
            continue
        if cls in OPS and node.get("op") not in OPS[cls]:
            report.fail("V-5", f"{code}/{cls}: unrecognised op "
                               f"{node.get('op')!r}")

        if cls == "FactVarID":
            check_varid(code, node, ctx, report, precondition)
        elif cls == "FilingIndicatorVarID":
            # V-44 — a declared filing indicator (§3.3.4, §4.9).
            if not isinstance(node.get("code"), str) or not is_int(node.get("variable_id")):
                report.fail("V-44", f"{code}: FilingIndicatorVarID needs a String "
                                    f"code and an integer variable_id")
            elif (node["code"], node["variable_id"]) not in ctx.indicators:
                report.fail("V-44", f"{code}: {node['code']} {node['variable_id']} "
                                    f"is no filing indicator of `modules`")
            else:
                ctx.indicator_reads.append((code, node["code"], node["variable_id"]))
        elif cls == "Constant":
            check_constant(code, node, report)
        elif cls == "Set":
            check_set(code, node, report)
        elif cls == "BinOp" and node.get("op") == "match":
            # §4.12 constraint 3 — the pattern is a String literal.
            pattern = node.get("right") or {}
            if pattern.get("class_name") != "Constant" \
                    or pattern.get("type_") != "String":
                report.fail("V-31", f"{code}: `match` pattern is "
                                    f"{pattern.get('class_name')}, expected a "
                                    f"String Constant")
        elif cls == "BinOp" and node.get("op") == "in":
            if node["right"].get("class_name") not in ("Set", "SetOp"):
                report.fail("V-21", f"{code}: `in` right operand is "
                                    f"{node['right'].get('class_name')}, "
                                    f"expected Set or SetOp")
        elif cls == "GroupingClause":
            check_grouping(code, node, parent, member, ctx.open_keys, report)
        elif cls == "AnalyticClause":
            check_analytic(code, node, parent, member, report)
        elif cls == "AggregationOp":
            # V-30 — the two clauses are mutually exclusive, `rank` is
            # analytic by definition, and `rank` rejects a window clause (§4.18).
            if node.get("grouping_clause") is not None \
                    and node.get("analytic_clause") is not None:
                report.fail("V-30", f"{code}: AggregationOp has both a "
                                    f"grouping_clause and an analytic_clause")
            if node.get("op") == "rank":
                if node.get("analytic_clause") is None:
                    report.fail("V-30", f"{code}: `rank` without an AnalyticClause")
                elif node.get("analytic_clause", {}).get("window") is not None:
                    report.fail("V-30", f"{code}: `rank` cannot have a window clause")
        elif cls == "SetOp":
            check_setop(code, node, report)
        elif cls == "SubstrOp":
            check_substr(code, node, report)
        elif cls == "RenameClauseOp":
            check_rename(code, node, report)
        elif cls == "GetClauseOp":
            if not isinstance(node.get("component"), str):
                report.fail("V-31", f"{code}: GetClauseOp component is "
                                    f"{node.get('component')!r}, expected a String")
        elif cls == "ParameterRef":
            check_parameter_ref(code, node, ctx.parameters, report)

    check_dimension_placement(code, root, report)
    index_set(root, report, code)


def check_varid(code, node, ctx: Context, report: Report, precondition: bool) -> None:
    entries = node["data"]
    table = node["table"]

    # V-46 — coordinates live in `modules`, not in the tree (§4.3.1).
    if CELL_AXES & (set(node) | {k for e in entries if isinstance(e, dict) for k in e}):
        report.fail("V-46", f"{code}: FactVarID over {table} carries row, column "
                            f"or sheet")

    # V-7
    if not isinstance(entries, list) or not entries:
        report.fail("V-7", f"{code}: FactVarID with empty `data`")
        return
    seen: set[tuple] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            report.fail("V-7", f"{code}: data entry {entry!r} is not an object")
            return
        extra = set(entry) - ENTRY_MEMBERS - CELL_AXES
        if extra:
            report.fail("V-5", f"{code}: data entry has unrecognised "
                               f"member(s) {sorted(extra)}")
        if not is_int(entry.get("datapoint")):
            report.fail("V-7", f"{code}: datapoint {entry.get('datapoint')!r} is "
                               f"not an integer")
        if not is_int(entry.get("operand_reference_id")):
            report.fail("V-7", f"{code}: operand_reference_id "
                               f"{entry.get('operand_reference_id')!r} is not an "
                               f"integer")
        for index in ("x", "y", "z"):
            value = entry.get(index)
            if index in entry and (not is_int(value) or value < 1):
                report.fail("V-7", f"{code}: {index} is {value!r}, "
                                   f"expected a positive integer")
        position = (entry.get("x"), entry.get("y"), entry.get("z"))
        if position in seen:
            report.fail("V-7", f"{code}: duplicate Position Index {position}")
        seen.add(position)
        # V-15 — an operand_reference_id identifies a cell reference, so it may
        # recur, but never for two different (table, datapoint) pairs (§4.3.3).
        if "operand_reference_id" in entry:
            ref = entry["operand_reference_id"]
            pair = (table, entry.get("datapoint"))
            previous = ctx.cell_of_ref.setdefault(ref, pair)
            if previous != pair:
                report.fail("V-15", f"{code}: operand_reference_id {ref} denotes "
                                    f"{pair} here and {previous} elsewhere")

    # V-6 — an index is on every entry or on none (§4.3.2).
    for index in ("x", "y", "z"):
        count = sum(index in entry for entry in entries)
        if count not in (0, len(entries)):
            report.fail("V-6", f"{code}: {index} on {count} of "
                               f"{len(entries)} entries")

    # V-43 — what the FactVarID reads exists in `modules`.
    for entry in entries:
        if not ctx.is_variable(table, entry.get("datapoint")):
            report.fail("V-43", f"{code}: datapoint {entry.get('datapoint')} is "
                              f"not a Variable of {table} in any version of "
                              f"`modules`")


def check_constant(code, node, report: Report) -> None:
    # V-20
    declared = node.get("type_")
    value = node.get("value")
    expected = CONSTANT_TYPES.get(declared)
    if expected is None:
        report.fail("V-20", f"{code}: Constant type_ {declared!r}")
        return
    ok = isinstance(value, expected)
    if declared != "Boolean" and isinstance(value, bool):
        ok = False                      # bool is a subclass of int in Python
    if declared == "Number" and isinstance(value, int) and not isinstance(value, bool):
        ok = True                       # a JSON integer is a valid Number
    if not ok:
        report.fail("V-20", f"{code}: Constant type_ {declared!r} with value "
                            f"of JSON type {type(value).__name__}")


def check_set(code, node, report: Report) -> None:
    # V-21 — `children` may be empty (the `{}` literal, §4.6).
    children = node.get("children")
    if not isinstance(children, list):
        report.fail("V-21", f"{code}: Set `children` is not an array")
        return
    for child in children:
        if child.get("class_name") not in ("Scalar", "Constant"):
            report.fail("V-21", f"{code}: Set child is "
                                f"{child.get('class_name')}, expected Scalar "
                                f"or Constant")


def check_grouping(code, node, parent, member, open_keys, report: Report) -> None:
    # V-22
    if parent is None or parent.get("class_name") != "AggregationOp" \
            or member != "grouping_clause":
        report.fail("V-22", f"{code}: GroupingClause is not the "
                            f"`grouping_clause` of an AggregationOp")
        return
    # V-23
    components = node.get("components") or []
    if not components:
        report.fail("V-23", f"{code}: GroupingClause with empty `components`")
    table = None
    renamed: set[str] = set()
    for descendant, _, _ in walk(parent["operand"]):
        if descendant["class_name"] == "RenameClauseOp":
            renamed.update(c.get("to_component")
                           for c in descendant.get("clauses") or [])
        if descendant["class_name"] == "FactVarID" and table is None:
            table = descendant["table"]
    # §4.19 — a component resolves against the operand as it presents itself,
    # so a `to_component` introduced by a RenameClauseOp counts.
    keys = (open_keys(table) if table else set()) | renamed | RESERVED_COMPONENTS
    for component in components:
        if component not in ("r", "c", "s") and component not in keys:
            report.fail("V-23", f"{code}: grouping component {component!r} is "
                                f"neither an axis token nor a Component of "
                                f"{table}")


def check_analytic(code, node, parent, member, report: Report) -> None:
    """V-22, V-30 — placement and shape of an AnalyticClause (§4.20)."""
    if parent is None or parent.get("class_name") != "AggregationOp" \
            or member != "analytic_clause":
        report.fail("V-22", f"{code}: AnalyticClause is not the "
                            f"`analytic_clause` of an AggregationOp")
    order_by = node.get("order_by")
    window = node.get("window")
    is_rank = parent is not None and parent.get("op") == "rank"
    must_have_order_by = is_rank or (window is not None)

    if not isinstance(order_by, list):
        report.fail("V-30", f"{code}: AnalyticClause `order_by` is not an array")
    elif must_have_order_by and not order_by:
        report.fail("V-30", f"{code}: AnalyticClause with empty `order_by`")
    elif order_by:
        for key in order_by:
            if not isinstance(key, dict) or "key_name" not in key:
                report.fail("V-30", f"{code}: order_by entry {key!r} has no "
                                    f"`key_name`")
            elif key.get("direction") not in ("asc", "desc"):
                report.fail("V-30", f"{code}: order_by direction "
                                    f"{key.get('direction')!r}")
    if not isinstance(node.get("partition_by"), list):
        report.fail("V-30", f"{code}: `partition_by` is not an array")
    if window is not None:
        check_window(code, window, node.get("order_by"), report)


def check_window(code, window, order_by, report: Report) -> None:
    """V-30 — the frame of a non-null AnalyticClause window (§4.20)."""
    if not isinstance(window, dict) or set(window) != {"frame_type", "start", "end"}:
        report.fail("V-30", f"{code}: window members "
                            f"{sorted(window) if isinstance(window, dict) else window!r}")
        return
    if window["frame_type"] not in WINDOW_FRAME_TYPES:
        report.fail("V-30", f"{code}: window frame_type {window['frame_type']!r}")
    # §4.20 — a `range` ordered by refPeriod, a Date, gives each `n` its unit.
    dated = window["frame_type"] == "range" and isinstance(order_by, list) \
        and len(order_by) == 1 and isinstance(order_by[0], dict) \
        and order_by[0].get("key_name") == "refPeriod"
    seen = []
    for side in ("start", "end"):
        bound = window[side]
        if not isinstance(bound, dict) or "bound_type" not in bound \
                or bound["bound_type"] not in WINDOW_BOUND_TYPES \
                or set(bound) - {"bound_type", "n", "period_indicator"}:
            report.fail("V-30", f"{code}: window {side} {bound!r}")
            return
        kind = bound["bound_type"]
        if kind not in WINDOW_N_BOUND_TYPES and "n" in bound:
            report.fail("V-30", f"{code}: window {side} {kind!r} carries an `n`")
        if "period_indicator" in bound and (
                kind not in WINDOW_N_BOUND_TYPES or window["frame_type"] != "range"
                or bound["period_indicator"] not in list(UNITS)):
            report.fail("V-30", f"{code}: window {side} period_indicator "
                                f"{bound['period_indicator']!r}")
        if dated and kind in WINDOW_N_BOUND_TYPES and "period_indicator" not in bound:
            report.fail("V-30", f"{code}: window {side} over refPeriod has no "
                                f"period_indicator")
        if kind in WINDOW_N_BOUND_TYPES and (not isinstance(bound.get("n"), int)
                                             or isinstance(bound.get("n"), bool)
                                             or bound["n"] < 1):
            report.fail("V-30", f"{code}: window {side} n {bound.get('n')!r}")
        seen.append(WINDOW_BOUND_ORDER[kind])
    if seen[0] > seen[1]:
        report.fail("V-30", f"{code}: window start is after its end")
    if window["frame_type"] == "range" and any(
            window[s].get("bound_type") in WINDOW_N_BOUND_TYPES
            for s in ("start", "end")) \
            and len(order_by or []) != 1:
        report.fail("V-30", f"{code}: `range` window with an `n` bound needs "
                            f"exactly one order_by key")


def check_setop(code, node, report: Report) -> None:
    """V-31 — SetOp arity (§4.14)."""
    operands = node.get("operands")
    if not isinstance(operands, list):
        report.fail("V-31", f"{code}: SetOp `operands` is not an array")
        return
    bounds = SETOP_ARITY.get(node.get("op"))
    if bounds is None:
        return                          # unrecognised op already reported by V-5
    low, high = bounds
    if len(operands) < low or (high is not None and len(operands) > high):
        report.fail("V-31", f"{code}: SetOp {node.get('op')!r} has "
                            f"{len(operands)} operand(s)")


def check_substr(code, node, report: Report) -> None:
    """V-31 — `start` and `length` are plain integers or null/absent (§4.15)."""
    for member in ("start", "length"):
        if member in node and node[member] is not None:
            value = node[member]
            if not isinstance(value, int) or isinstance(value, bool):
                report.fail("V-31", f"{code}: SubstrOp {member} is {value!r}, "
                                    f"expected a JSON integer or null")


def check_rename(code, node, report: Report) -> None:
    """V-31 — rename pairs are simultaneous and disjoint (§4.24)."""
    clauses = node.get("clauses")
    if not isinstance(clauses, list) or not clauses:
        report.fail("V-31", f"{code}: RenameClauseOp with empty `clauses`")
        return
    sources, targets = set(), set()
    for clause in clauses:
        if not isinstance(clause, dict) or set(clause) != {"from_component",
                                                           "to_component"}:
            report.fail("V-31", f"{code}: rename clause {clause!r} is malformed")
            continue
        sources.add(clause["from_component"])
        targets.add(clause["to_component"])
    overlap = sources & targets
    if overlap:
        report.fail("V-31", f"{code}: rename sources and targets overlap on "
                            f"{sorted(overlap)}")


def _matches_declared_type(value, declared: str) -> bool:
    """§4.4, §4.8.1 — does `value` have the JSON type `declared` requires?

    `declared` is a scalar param_type name ("Number", …) or "Item".
    """
    if declared == "Item":
        return isinstance(value, str)
    expected = PARAMETER_DEFAULT_TYPES[declared]
    ok = isinstance(value, expected)
    if declared != "Boolean" and isinstance(value, bool):
        ok = False                      # bool is a subclass of int in Python
    if declared == "Number" and isinstance(value, int) \
            and not isinstance(value, bool):
        ok = True                       # a JSON integer is a valid Number
    if declared == "Date" and isinstance(value, str):
        ok = bool(ISO_DATE.match(value))
    return ok


def check_parameter_ref(code, node, parameters, report: Report) -> None:
    """V-29 — a ParameterRef agrees with its declaration (§3.4, §4.8.1)."""
    name = node.get("code")
    declared = node.get("param_type")
    if name not in parameters:
        report.fail("V-29", f"{code}: ParameterRef {name!r} is not declared "
                            f"in `parameters`")
    elif parameters[name] != declared:
        report.fail("V-29", f"{code}: ParameterRef {name!r} has param_type "
                            f"{declared!r}, declared {parameters[name]!r}")

    # §4.8.1 — `default` is optional and nullable, and a non-null value must
    # suit the declared type. An Item default is a bare value, never a
    # Scalar Node.
    if "default" not in node:
        return
    fallback = node["default"]
    if fallback is None:
        return
    if declared == "Item":
        if not _matches_declared_type(fallback, "Item"):
            report.fail("V-29", f"{code}: ParameterRef {name!r} of type "
                                f"\"Item\" has a default that is not a String")
        return
    if declared not in PARAMETER_DEFAULT_TYPES:
        return                          # unknown type already reported
    if not _matches_declared_type(fallback, declared):
        report.fail("V-29", f"{code}: ParameterRef {name!r} of type "
                            f"{declared!r} has default {fallback!r}")


def check_dimension_placement(code, root, report: Report) -> None:
    """V-22 — the four positions a Dimension may occupy (§4.7)."""
    condition_holders = ("WhereClauseOp", "SubClauseOp", "FilterOp")

    def descend(node, permitted: bool) -> None:
        cls = node["class_name"]
        if cls == "Dimension" and not permitted:
            report.fail("V-22", f"{code}: Dimension outside a clause "
                                f"condition or a SubstrOp operand")
        for member, child in child_nodes(node):
            enters = ((cls in condition_holders and member == "condition")
                      or (cls == "SubstrOp" and member == "operand"))
            descend(child, permitted or enters)
    descend(root, False)


def check_preconditions(module, operations, ctx: Context, report: Report) -> None:
    for code, precondition in sorted(module["preconditions"].items()):
        # V-3
        if precondition.get("code") != code:
            report.fail("V-3", f"preconditions/{code}: code member is "
                               f"{precondition.get('code')!r}")
        if set(precondition) != PRECONDITION_MEMBERS:
            missing = PRECONDITION_MEMBERS - set(precondition)
            extra = set(precondition) - PRECONDITION_MEMBERS
            if missing:
                report.fail("V-3", f"preconditions/{code}: missing "
                                   f"{sorted(missing)}")
            if extra:
                report.fail("V-3", f"preconditions/{code}: unrecognised "
                                   f"{sorted(extra)}")
            if "ast" in missing:
                continue

        root = precondition["ast"]
        label = f"preconditions/{code}"
        check_tree(label, root, ctx, report, precondition=True)

        # V-12 — the tree must not vary on any axis: its index set is either
        # empty or the single all-absent index. That the result is Boolean is
        # a semantic constraint, settled before a document is produced, so it
        # is deliberately not checked here.
        positions = index_set(root, report, label)
        if positions is not OPAQUE and axes_of(positions):
            report.fail("V-12", f"{label}: tree varies on axes "
                                f"{sorted(axes_of(positions))} and yields "
                                f"{len(positions)} results; a precondition "
                                f"yields one Boolean")
        # V-13 — narrowed to preconditions.
        affected = precondition.get("affected_operations") or []
        if not affected:
            report.fail("V-13", f"{code}: empty affected_operations")
        for target in affected:
            if target not in operations:
                report.fail("V-13", f"{code}: affected operation {target!r} "
                                    f"is not in `operations`")


def module_references(node, report: Report, label: str, top: bool = True):
    """V-36 — yield every module reference of a `requires`, checking its shape."""
    if not isinstance(node, dict) or len(node) != 1:
        report.fail("V-36", f"{label}: {node!r} is not an object with exactly "
                            f"one operator")
        return
    (operator, argument), = node.items()
    if operator == "is":
        if not top:
            report.fail("V-36", f"{label}: `is` below the top of requires")
        if not isinstance(argument, dict) or "code" not in argument:
            report.fail("V-36", f"{label}: `is` holds {argument!r}, not a "
                                f"module reference")
            return
        yield argument
        return
    if operator not in BINARY_OPERATORS:
        report.fail("V-36", f"{label}: unknown operator {operator!r}")
        return
    if not isinstance(argument, dict) or set(argument) != {"left", "right", "decided_by"}:
        report.fail("V-36", f"{label}: `{operator}` needs exactly left, right "
                            f"and decided_by")
        return
    if argument["decided_by"] not in DECIDED_BY:
        report.fail("V-36", f"{label}: decided_by {argument['decided_by']!r}")
    for side in ("left", "right"):
        operand = argument[side]
        if isinstance(operand, dict) and "code" in operand:
            yield operand
        else:
            yield from module_references(operand, report, label, top=False)


def reference_key(reference):
    """§5.4 rule 2 — the canonical order of module references."""
    lag = reference.get("ref_date_lag")
    if lag is None:
        return (reference["code"], 2, 0, 0, 0)
    if lag == 0:
        return (reference["code"], 0, 0, 0, 0)
    unit = reference.get("ref_date_lag_unit")
    return (reference["code"], 1, UNITS.index(unit) if unit in UNITS else len(UNITS),
            abs(lag), 0 if lag < 0 else 1)


def check_canonical(node, report: Report, label: str) -> None:
    """V-38 — a chain nests right, references precede nested operators and
    are ordered, none repeats within the chain, and members are in order."""
    if not node or "is" in node:
        return
    (operator, argument), = node.items()
    reason = argument["decided_by"]
    operands, current = [], node
    while isinstance(current, dict) and "code" not in current \
            and list(current) == [operator] \
            and current[operator]["decided_by"] == reason:
        if list(current[operator]) != ["left", "right", "decided_by"]:
            report.fail("V-38", f"{label}: members of `{operator}` are not in "
                                f"the order left, right, decided_by")
        left = current[operator]["left"]
        if isinstance(left, dict) and list(left) == [operator] \
                and left[operator].get("decided_by") == reason:
            report.fail("V-38", f"{label}: a `{operator}` chain nests to the left")
        operands.append(left)
        current = current[operator]["right"]
    operands.append(current)
    references = [o for o in operands if "code" in o]
    nested = [o for o in operands if "code" not in o]
    if operands != references + nested:
        report.fail("V-38", f"{label}: references do not precede nested operators")
    for reference in references:
        expected = [m for m in ("code", "ref_date_lag", "ref_date_lag_unit")
                    if m in reference]
        if list(reference) != expected:
            report.fail("V-38", f"{label}: reference members {list(reference)} "
                                f"are not in canonical order")
    if references != sorted(references, key=reference_key):
        report.fail("V-38", f"{label}: references out of canonical order")
    if len({json.dumps(r, sort_keys=True) for r in references}) != len(references):
        report.fail("V-38", f"{label}: a reference repeats within one chain")
    firsts = [first_reference(o) for o in nested]
    if all(firsts) and firsts != sorted(firsts, key=reference_key):
        report.fail("V-38", f"{label}: nested operators out of order")
    for operand in nested:
        check_canonical(operand, report, label)


def first_reference(node):
    while isinstance(node, dict) and "code" not in node and len(node) == 1:
        (_, argument), = node.items()
        node = argument.get("left") if isinstance(argument, dict) else None
    return node if isinstance(node, dict) and "code" in node else None


def check_groups(module, operations, ctx: Context, report: Report) -> None:
    groups = module["dependency_groups"]
    modules = module["modules"]
    group_of: dict[str, str] = {}
    required: dict[str, set[str]] = {}
    seen_requires: dict[str, str] = {}

    for name, group in sorted(groups.items()):
        if not isinstance(group, dict) or set(group) != GROUP_MEMBERS:
            report.fail("V-36", f"dependency_groups/{name}: a group has exactly "
                                f"`requires` and `validations`")
            continue
        # V-33
        validations = group["validations"]
        if not isinstance(validations, list) or not validations:
            report.fail("V-33", f"{name}: empty group")
            validations = []
        for code in validations:
            if code in group_of:
                report.fail("V-33", f"{code} is in groups {group_of[code]} and {name}")
            group_of.setdefault(code, name)

        # V-39
        requires = group["requires"]
        key = json.dumps(requires, sort_keys=True)
        if key in seen_requires:
            report.fail("V-39", f"{name}: same requires as {seen_requires[key]}")
        seen_requires.setdefault(key, name)

        # V-36, V-37
        if requires == {}:
            references = []
        else:
            before = report.count
            references = list(module_references(requires, report, name))
            if report.count == before:
                check_canonical(requires, report, name)         # V-38
        for reference in references:
            check_reference(name, reference, module["module_code"], modules, report)
        required[name] = {r.get("code") for r in references}

        # V-40 — a group's validations read only tables it requires.
        allowed = set(ctx.own_tables)
        for code in required[name]:
            for version in (modules.get(code) or {}).get("versions") or []:
                if isinstance(version, dict):
                    allowed |= set(version.get("tables") or {})
        for code in validations:
            operation = operations.get(code)
            if not isinstance(operation, dict) or "ast" not in operation:
                continue
            read = {node.get("table") for node, _, _ in walk(operation["ast"])
                    if node.get("class_name") == "FactVarID"}
            if read - allowed:
                report.fail("V-40", f"{name}/{code}: reads {sorted(read - allowed)}, "
                                    f"which the group does not require")

    # V-33 — a partition of `operations`.
    missing = sorted(set(operations) - set(group_of))
    unknown = sorted(set(group_of) - set(operations))
    if missing:
        report.fail("V-33", f"{len(missing)} Operation(s) in no group, e.g. {missing[0]}")
    if unknown:
        report.fail("V-33", f"{len(unknown)} grouped code(s) not in `operations`, "
                            f"e.g. {unknown[0]}")

    # V-44 — a filing indicator is of the own module, or of a module required
    # by the group of every Operation that reads it or that its precondition gates.
    own = module["module_code"]
    for label, indicator, variable_id in ctx.indicator_reads:
        owners = ctx.indicators.get((indicator, variable_id), set())
        if own in owners:
            continue
        if label.startswith("preconditions/"):
            precondition = module["preconditions"][label.split("/", 1)[1]]
            gated = precondition.get("affected_operations") or []
        else:
            gated = [label]
        for operation in gated:
            group = group_of.get(operation)
            if group is not None and not owners & required.get(group, set()):
                report.fail("V-44", f"{label}: filing indicator {indicator} belongs "
                                    f"to {sorted(owners)}, which group {group} of "
                                    f"{operation} does not require")


def check_reference(group, reference, own_code, modules, report: Report) -> None:
    """V-37 — the members and values of a module reference (§5.3)."""
    lag = reference.get("ref_date_lag", "missing")
    expected = {"code", "ref_date_lag"} | ({"ref_date_lag_unit"} if lag != 0 else set())
    if set(reference) != expected:
        report.fail("V-37", f"{group}: reference members {sorted(reference)}, "
                            f"expected {sorted(expected)}")
    if reference.get("code") not in modules:
        report.fail("V-37", f"{group}: {reference.get('code')!r} is not a key of "
                            f"`modules`")
    if lag is not None and not is_int(lag):
        report.fail("V-37", f"{group}: ref_date_lag {lag!r}")
    if lag != 0 and reference.get("ref_date_lag_unit") not in list(UNITS):
        report.fail("V-37", f"{group}: ref_date_lag_unit "
                            f"{reference.get('ref_date_lag_unit')!r}")
    if reference.get("code") == own_code and lag == 0:
        report.fail("V-37", f"{group}: the own module at lag 0; the anchor is "
                            f"always there")


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def validate(path: Path) -> Report:
    report = Report()
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        report.fail("V-2", f"root is a JSON {type(raw).__name__}, "
                           f"expected the Module Object")
        return report
    try:
        check_document(raw, path, report)
    except (KeyError, TypeError, AttributeError, ValueError) as error:
        report.fail("V-5", f"malformed document, checking stopped: {error!r}")
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate DPM-XL Script Documents (format 2.0) against "
                    "the rules of Script Format §6.2.")

    parser.add_argument("files", nargs="+", type=Path,
                        help="Script Document(s) to validate")
    parser.add_argument("--json", action="store_true",
                        help="emit machine-readable results")
    parser.add_argument("--quiet", action="store_true",
                        help="suppress output; report through the exit code")
    parser.add_argument("--max-examples", type=int, default=3, metavar="N",
                        help="violations to show per rule (default 3)")
    args = parser.parse_args(argv)

    results = {}
    failed = False
    for path in args.files:
        try:
            results[str(path)] = validate(path)
        except (OSError, json.JSONDecodeError) as error:
            if not args.quiet:
                print(f"{path}: cannot read: {error}", file=sys.stderr)
            return 2
        if not results[str(path)].valid:
            failed = True

    if args.quiet:
        return 1 if failed else 0

    if args.json:
        print(json.dumps({
            name: {"valid": report.valid,
                   "violations": {rule: report.violations[rule]
                                  for rule in report.rules()},
                   "unverified_operators": report.unverified}
            for name, report in results.items()
        }, indent=2))
        return 1 if failed else 0

    width = max(len(name) for name in results)
    for name, report in results.items():
        status = "VALID" if report.valid else f"{report.count} violation(s)"
        print(f"{name:<{width}}  {status}")
        for rule in report.rules():
            details = report.violations[rule]
            print(f"    {rule}  ({len(details)})")
            for detail in details[:args.max_examples]:
                print(f"        {detail}")
            if len(details) > args.max_examples:
                print(f"        ... and {len(details) - args.max_examples} more")

    total = sum(report.count for report in results.values())
    unverified = sum(report.unverified for report in results.values())
    print()
    print(f"{len(results)} document(s), {total} violation(s)"
          + (f", {unverified} Operator(s) not statically verifiable"
             if unverified else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
