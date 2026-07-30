"""Run the DB-driven validations-script generation for every MDPM reference
module and diff the result against the reference.

Each reference file `scripts/mdpm_references/<MODULE>-<VERSION>.json` defines
one module to test. For each, we:
  1. Call `generate_module` (DB → ASTGeneratorService) to produce dpmcore's
     equivalent JSON in memory.
  2. Compare six blocks against the MDPM reference: operations, preconditions,
     tables, variables, dependency_modules (dep URIs + per-URI tables /
     variables + per-(uri, table) variables), and dependency_information
     (intra classification + cross-scope fingerprint + alternative deps).
  3. Aggregate per-module deltas and totals, categorise findings against the
     known divergence classes (see
     `~/.claude/projects/-home-victorp-dpmcore/memory/project_mdpm_parity_findings.md`),
     and flag anything that doesn't fit a known pattern as a "new" finding.

Outputs:
  - scripts/parity_report.json (full per-module detail)
  - scripts/parity_report.txt  (human-readable summary)

Usage:
    poetry run python scripts/check_all_modules_parity.py
    poetry run python scripts/check_all_modules_parity.py --db sqlite:///dpm_4.2.1_20260624.db
"""

import argparse
import json
import re
import sys
import traceback
from pathlib import Path

from generate_module_from_db import generate_module
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

_REFERENCES_DIR = Path("scripts/mdpm_references")
_DEFAULT_DB = "sqlite:///dpm_4.2.1_20260624.db"
_FILENAME_RE = re.compile(r"^(?P<code>.+)-(?P<version>\d+\.\d+\.\d+)\.json$")


# Expression-shape probes for Finding 1 (compound-AND / abs / .b variants)
def _looks_like_finding_1(expressions: list[str]) -> bool:
    for e in expressions:
        if " and " in e or "abs(" in e:
            return True
        # `.b` table variant in `with {tX_yy.zz.b ...}` form
        if re.search(r"\{t[^,}]+\.b[,\s}]", e):
            return True
    return False


def _diff_set(ref: set, new: set) -> dict:
    return {
        "ref_count": len(ref),
        "new_count": len(new),
        "only_in_ref": sorted(ref - new),
        "only_in_new": sorted(new - ref),
    }


def _diff_preconditions(ref_pc: dict, new_pc: dict) -> dict:
    """MDPM keys are p_<OperationID>; dpmcore keys are p_<variable_vid>.
    Compare on (variable_id, variable_code) instead — that's the AST identity.
    """

    def fingerprint(pc_dict):
        out = {}
        for k, v in pc_dict.items():
            ast = v.get("ast") or {}
            if ast.get("class_name") == "PreconditionItem":
                key = (ast.get("variable_id"), ast.get("variable_code"))
            else:
                key = ("compound", json.dumps(ast, sort_keys=True))
            out[key] = (k, v)
        return out

    ref_fp = fingerprint(ref_pc)
    new_fp = fingerprint(new_pc)
    ref_keys = set(ref_fp)
    new_keys = set(new_fp)

    matched_ast = ref_keys & new_keys
    naming_mismatches = 0
    affected_op_mismatches = 0
    for fp in matched_ast:
        ref_key, ref_val = ref_fp[fp]
        new_key, new_val = new_fp[fp]
        if ref_key != new_key or ref_val.get("code") != new_val.get("code"):
            naming_mismatches += 1
        if set(ref_val.get("affected_operations", [])) != set(
            new_val.get("affected_operations", [])
        ):
            affected_op_mismatches += 1

    return {
        "ref_count": len(ref_pc),
        "new_count": len(new_pc),
        "ast_matched": len(matched_ast),
        "only_in_ref_ast": [
            list(k) for k in sorted(ref_keys - new_keys, key=lambda x: str(x))
        ],
        "only_in_new_ast": [
            list(k) for k in sorted(new_keys - ref_keys, key=lambda x: str(x))
        ],
        "naming_mismatches": naming_mismatches,
        "affected_operations_mismatches": affected_op_mismatches,
    }


def _diff_dependency_modules(ref_dm: dict, new_dm: dict) -> dict:
    """Diff ``dependency_modules`` at three levels.

    Level 1 — set of dependency URIs (``only_in_ref`` / ``only_in_new``).
    Level 2 — per-URI ``tables`` and ``variables`` sets, for URIs present
              on both sides.
    Level 3 — per-``(uri, table)`` ``variables`` map (datapoint → type),
              for tables present on both sides. Only tables whose variable
              sets actually differ are reported to keep the payload small.

    The block was invisible to the parity check until this addition: bugs
    #250 (over-declaration of dep-module tables / variables) and #251
    (missing home-module operand variables inside a dep module) both live
    strictly inside ``dependency_modules`` and were surfaced only after
    #253 shipped. Diffing here catches future regressions of the same
    shape at QA time.
    """
    ref_dm = ref_dm or {}
    new_dm = new_dm or {}
    ref_uris = set(ref_dm.keys())
    new_uris = set(new_dm.keys())

    per_uri: dict[str, dict] = {}
    for uri in ref_uris & new_uris:
        ref_entry = ref_dm.get(uri) or {}
        new_entry = new_dm.get(uri) or {}
        ref_tables = set((ref_entry.get("tables") or {}).keys())
        new_tables = set((new_entry.get("tables") or {}).keys())
        ref_variables = set((ref_entry.get("variables") or {}).keys())
        new_variables = set((new_entry.get("variables") or {}).keys())

        table_variables: dict[str, dict] = {}
        for tbl in ref_tables & new_tables:
            ref_tv = set(
                (
                    (ref_entry["tables"][tbl] or {}).get("variables") or {}
                ).keys()
            )
            new_tv = set(
                (
                    (new_entry["tables"][tbl] or {}).get("variables") or {}
                ).keys()
            )
            if ref_tv != new_tv:
                table_variables[tbl] = _diff_set(ref_tv, new_tv)

        per_uri[uri] = {
            "tables": _diff_set(ref_tables, new_tables),
            "variables": _diff_set(ref_variables, new_variables),
            "table_variables": table_variables,
        }

    return {
        "ref_count": len(ref_uris),
        "new_count": len(new_uris),
        "only_in_ref": sorted(ref_uris - new_uris),
        "only_in_new": sorted(new_uris - ref_uris),
        "per_uri": per_uri,
    }


def _dep_module_totals(dep_diff: dict) -> dict:
    """Roll up counts across all shared URIs for at-a-glance signalling."""
    over_tables = under_tables = 0
    over_vars = under_vars = 0
    over_tv = under_tv = 0
    tv_tables_with_diff = 0
    for uri_diff in dep_diff.get("per_uri", {}).values():
        over_tables += len(uri_diff["tables"]["only_in_new"])
        under_tables += len(uri_diff["tables"]["only_in_ref"])
        over_vars += len(uri_diff["variables"]["only_in_new"])
        under_vars += len(uri_diff["variables"]["only_in_ref"])
        for tv_diff in uri_diff["table_variables"].values():
            over_tv += len(tv_diff["only_in_new"])
            under_tv += len(tv_diff["only_in_ref"])
            tv_tables_with_diff += 1
    return {
        "tables_only_in_new_total": over_tables,
        "tables_only_in_ref_total": under_tables,
        "variables_only_in_new_total": over_vars,
        "variables_only_in_ref_total": under_vars,
        "table_variables_only_in_new_total": over_tv,
        "table_variables_only_in_ref_total": under_tv,
        "tables_with_variable_diff": tv_tables_with_diff,
    }


def _diff_dependency_information(ref_di: dict, new_di: dict) -> dict:
    """Diff ``dependency_information`` in three sub-blocks.

    - ``intra_instance_validations``: set of operation codes classified as
      intra-instance. Bug #141 ("Validation wrongly classified intra for a
      module that hosts none of its tables") lived here and was invisible
      before this addition.
    - ``cross_instance_dependencies``: list of cross-scope groups. Each
      entry combines ``modules`` (list of
      ``{URI, module_version, ref_period}``), ``affected_operations``
      (list of op codes), and a ``from/to_reference_date`` pair. Two
      entries are equivalent when the (modules, dates) fingerprint
      matches; ``affected_operations`` is set-diffed within a shared
      entry.
    - ``alternative_dependencies``: set of alternative dependency groups
      (each a set of dep URIs). dpmcore always emits this key; the reference
      only carries it for a handful of modules — treat "ref does not have it"
      as no-comparison rather than a diff.
    """
    ref_di = ref_di or {}
    new_di = new_di or {}

    ref_intra = set(ref_di.get("intra_instance_validations") or [])
    new_intra = set(new_di.get("intra_instance_validations") or [])

    ref_cross = ref_di.get("cross_instance_dependencies") or []
    new_cross = new_di.get("cross_instance_dependencies") or []

    def _cross_fingerprint(entry: dict) -> tuple:
        modules = tuple(
            sorted(
                (
                    m.get("URI"),
                    m.get("module_version"),
                    m.get("ref_period"),
                )
                for m in (entry.get("modules") or [])
            )
        )
        return (
            modules,
            entry.get("from_reference_date"),
            entry.get("to_reference_date"),
        )

    ref_cross_by_fp = {_cross_fingerprint(e): e for e in ref_cross}
    new_cross_by_fp = {_cross_fingerprint(e): e for e in new_cross}
    ref_cross_fps = set(ref_cross_by_fp)
    new_cross_fps = set(new_cross_by_fp)

    affected_ops_mismatches: list[dict] = []
    for fp in ref_cross_fps & new_cross_fps:
        ref_ops = set(ref_cross_by_fp[fp].get("affected_operations") or [])
        new_ops = set(new_cross_by_fp[fp].get("affected_operations") or [])
        if ref_ops != new_ops:
            affected_ops_mismatches.append(
                {
                    "modules": [list(m) for m in fp[0]],
                    "from_reference_date": fp[1],
                    "to_reference_date": fp[2],
                    "only_in_ref": sorted(ref_ops - new_ops),
                    "only_in_new": sorted(new_ops - ref_ops),
                }
            )

    # Alternative dependencies: each entry is a list of URIs (a group).
    # Compare as a set of frozensets so ordering and duplicate URIs don't
    # confuse the diff. Only compare when the reference actually has the
    # block — dpmcore emits it universally, ref has it in 3/107 modules.
    ref_alt_raw = ref_di.get("alternative_dependencies")
    new_alt_raw = new_di.get("alternative_dependencies") or []

    def _alt_set(alt) -> set:
        return {
            frozenset(group or [])
            for group in (alt or [])
            if isinstance(group, (list, tuple, set))
        }

    if ref_alt_raw is None:
        alt_diff = {"ref_present": False, "new_count": len(new_alt_raw)}
    else:
        ref_alt = _alt_set(ref_alt_raw)
        new_alt = _alt_set(new_alt_raw)
        alt_diff = {
            "ref_present": True,
            "ref_count": len(ref_alt),
            "new_count": len(new_alt),
            "only_in_ref": [sorted(g) for g in (ref_alt - new_alt)],
            "only_in_new": [sorted(g) for g in (new_alt - ref_alt)],
        }

    return {
        "intra_instance_validations": _diff_set(ref_intra, new_intra),
        "cross_instance_dependencies": {
            "ref_count": len(ref_cross),
            "new_count": len(new_cross),
            "matched": len(ref_cross_fps & new_cross_fps),
            "only_in_ref_fingerprints": [
                {
                    "modules": [list(m) for m in fp[0]],
                    "from_reference_date": fp[1],
                    "to_reference_date": fp[2],
                }
                for fp in sorted(
                    ref_cross_fps - new_cross_fps, key=lambda x: str(x)
                )
            ],
            "only_in_new_fingerprints": [
                {
                    "modules": [list(m) for m in fp[0]],
                    "from_reference_date": fp[1],
                    "to_reference_date": fp[2],
                }
                for fp in sorted(
                    new_cross_fps - ref_cross_fps, key=lambda x: str(x)
                )
            ],
            "affected_operations_mismatches": affected_ops_mismatches,
        },
        "alternative_dependencies": alt_diff,
    }


def _dep_info_totals(di_diff: dict) -> dict:
    """Roll up dep-info counts for at-a-glance signalling."""
    intra = di_diff.get("intra_instance_validations", {})
    cross = di_diff.get("cross_instance_dependencies", {})
    alt = di_diff.get("alternative_dependencies", {})
    return {
        "intra_only_in_new": len(intra.get("only_in_new", [])),
        "intra_only_in_ref": len(intra.get("only_in_ref", [])),
        "cross_only_in_new": len(cross.get("only_in_new_fingerprints", [])),
        "cross_only_in_ref": len(cross.get("only_in_ref_fingerprints", [])),
        "cross_affected_op_diffs": len(
            cross.get("affected_operations_mismatches", [])
        ),
        "alt_only_in_new": len(alt.get("only_in_new", []))
        if alt.get("ref_present")
        else 0,
        "alt_only_in_ref": len(alt.get("only_in_ref", []))
        if alt.get("ref_present")
        else 0,
    }


def _classify(module_result: dict) -> list[str]:
    """Tag each module with the known finding labels that explain its deltas.
    Anything left unexplained surfaces as 'unclassified'.
    """
    tags: list[str] = []
    cmp = module_result.get("comparison") or {}
    ops = cmp.get("operations") or {}
    pcs = cmp.get("preconditions") or {}
    tabs = cmp.get("tables") or {}
    dm = cmp.get("dependency_modules") or {}
    dm_totals = module_result.get("dep_module_totals") or {}
    di_totals = module_result.get("dep_info_totals") or {}

    # Finding 1: dpmcore over-includes ops & those extras carry compound-AND /
    # abs / .b table-variant expressions
    if ops.get("only_in_new") and module_result.get("finding1_signal"):
        tags.append("finding1_dpmcore_extra_ops")

    # Finding 2: precondition AST matches but keys/code/version_id differ
    if pcs.get("ast_matched") and pcs.get("naming_mismatches"):
        tags.append("finding2_precondition_naming")

    # Finding 3: dpmcore omits tables/vars that are in the module composition
    # but never referenced. Heuristic: ref has tables/vars that dpmcore lacks,
    # and dpmcore lacks no others.
    if tabs.get("only_in_ref") and not tabs.get("only_in_new"):
        tags.append("finding3_tables_vars_missing")

    # Finding 4 (dep_modules): dependency URIs differ. Extras on either side
    # signal a scope-detection divergence; keep them as separate tags because
    # the two failure modes are opposite (dpmcore invents a dep vs dpmcore
    # forgets one).
    if dm.get("only_in_ref"):
        tags.append("finding4_dep_uri_missing_in_new")
    if dm.get("only_in_new"):
        tags.append("finding4_dep_uri_extra_in_new")

    # Finding 5 (dep_modules): for shared URIs, dpmcore over-declares dep
    # tables / variables / per-table variables — the shape of #250 (whole
    # module emitted instead of the referenced subset).
    if (
        dm_totals.get("tables_only_in_new_total")
        or dm_totals.get("variables_only_in_new_total")
        or dm_totals.get("table_variables_only_in_new_total")
    ):
        tags.append("finding5_dep_over_declaration")

    # Finding 6 (dep_modules): for shared URIs, dpmcore under-declares dep
    # tables / variables / per-table variables — the shape of #251 (home
    # operand not grafted into the dep module's variables map).
    if (
        dm_totals.get("tables_only_in_ref_total")
        or dm_totals.get("variables_only_in_ref_total")
        or dm_totals.get("table_variables_only_in_ref_total")
    ):
        tags.append("finding6_dep_under_declaration")

    # Finding 7 (dep_info): intra-instance classification differs — the
    # shape of #141 (validation wrongly classified intra).
    if di_totals.get("intra_only_in_new") or di_totals.get(
        "intra_only_in_ref"
    ):
        tags.append("finding7_intra_classification_diff")

    # Finding 8 (dep_info): cross-instance dependency fingerprint differs —
    # either a whole cross-scope group is only on one side, or the affected
    # operations of a shared fingerprint diverge.
    if (
        di_totals.get("cross_only_in_new")
        or di_totals.get("cross_only_in_ref")
        or di_totals.get("cross_affected_op_diffs")
    ):
        tags.append("finding8_cross_dependency_diff")

    # Finding 9 (dep_info): alternative_dependencies diverge for the ref
    # modules that carry the block. dpmcore-only-when-ref-absent is not
    # flagged (that would fire on 104/107 modules).
    if di_totals.get("alt_only_in_new") or di_totals.get("alt_only_in_ref"):
        tags.append("finding9_alternative_deps_diff")

    # Anything else weird → unclassified
    unexplained = (
        bool(ops.get("only_in_ref"))  # MDPM-only ops (dpmcore should have ALL)
        or bool(tabs.get("only_in_new"))  # dpmcore-only tables (unexpected)
        or pcs.get("only_in_new_ast")
        or pcs.get("only_in_ref_ast")
        or pcs.get("affected_operations_mismatches")
    )
    if unexplained:
        tags.append("unclassified")

    if not tags and (ops.get("only_in_new") or ops.get("only_in_ref")):
        tags.append("unclassified")

    return tags or ["clean"]


def check_module(session: Session, ref_path: Path) -> dict:
    m = _FILENAME_RE.match(ref_path.name)
    if not m:
        return {"file": ref_path.name, "error": "filename does not match"}

    module_code = m.group("code")
    module_version = m.group("version")

    try:
        ref = json.loads(ref_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "file": ref_path.name,
            "module_code": module_code,
            "module_version": module_version,
            "error": f"could not read reference: {exc}",
        }
    ref_root = next(iter(ref.values()))

    try:
        result = generate_module(session, module_code, module_version)
    except Exception as exc:
        return {
            "file": ref_path.name,
            "module_code": module_code,
            "module_version": module_version,
            "error": f"generate_module raised: {exc}",
            "traceback": traceback.format_exc(limit=5),
        }

    if not result.get("success"):
        # Empty-by-design modules (DIS/DOCS frameworks) legitimately have no
        # validation ops in the DB. If the MDPM reference also has zero ops,
        # this is parity-clean, not an error.
        ref_has_no_ops = not (ref_root.get("operations") or {})
        msg = result.get("error") or ""
        if ref_has_no_ops and "No validations found" in msg:
            return {
                "file": ref_path.name,
                "module_code": module_code,
                "module_version": module_version,
                "input_stats": result.get("input_stats"),
                "tags": ["empty_by_design"],
                "comparison": None,
            }
        return {
            "file": ref_path.name,
            "module_code": module_code,
            "module_version": module_version,
            "error": result.get("error"),
            "input_stats": result.get("input_stats"),
        }

    enriched = result["enriched_ast"]
    new_root = next(iter(enriched.values()))

    ref_ops = set((ref_root.get("operations") or {}).keys())
    new_ops = set((new_root.get("operations") or {}).keys())
    ref_tables = set((ref_root.get("tables") or {}).keys())
    new_tables = set((new_root.get("tables") or {}).keys())
    ref_vars = set((ref_root.get("variables") or {}).keys())
    new_vars = set((new_root.get("variables") or {}).keys())

    # Probe extras for Finding-1 signal (compound-AND / abs / .b table variant)
    extras_exprs = [
        (new_root["operations"][c] or {}).get("expression", "")
        for c in (new_ops - ref_ops)
    ]
    finding1_signal = _looks_like_finding_1(extras_exprs)

    dep_diff = _diff_dependency_modules(
        ref_root.get("dependency_modules") or {},
        new_root.get("dependency_modules") or {},
    )
    dep_totals = _dep_module_totals(dep_diff)

    di_diff = _diff_dependency_information(
        ref_root.get("dependency_information") or {},
        new_root.get("dependency_information") or {},
    )
    di_totals = _dep_info_totals(di_diff)

    module_result = {
        "file": ref_path.name,
        "module_code": module_code,
        "module_version": module_version,
        "input_stats": result.get("input_stats"),
        "comparison": {
            "operations": _diff_set(ref_ops, new_ops),
            "tables": _diff_set(ref_tables, new_tables),
            "variables": _diff_set(ref_vars, new_vars),
            "preconditions": _diff_preconditions(
                ref_root.get("preconditions") or {},
                new_root.get("preconditions") or {},
            ),
            "dependency_modules": dep_diff,
            "dependency_information": di_diff,
        },
        "dep_module_totals": dep_totals,
        "dep_info_totals": di_totals,
        "finding1_signal": finding1_signal,
    }
    module_result["tags"] = _classify(module_result)

    # Drop heavy lists from "only_in_*" if they're huge — keep counts.
    for block in ("operations", "tables", "variables"):
        c = module_result["comparison"][block]
        for k in ("only_in_ref", "only_in_new"):
            if len(c[k]) > 50:
                c[f"{k}_truncated_total"] = len(c[k])
                c[k] = c[k][:50]

    # Same guard for dependency_modules at all three levels.
    dm = module_result["comparison"]["dependency_modules"]
    for k in ("only_in_ref", "only_in_new"):
        if len(dm[k]) > 50:
            dm[f"{k}_truncated_total"] = len(dm[k])
            dm[k] = dm[k][:50]
    for uri_diff in dm["per_uri"].values():
        for sub in ("tables", "variables"):
            for k in ("only_in_ref", "only_in_new"):
                if len(uri_diff[sub][k]) > 50:
                    uri_diff[sub][f"{k}_truncated_total"] = len(
                        uri_diff[sub][k]
                    )
                    uri_diff[sub][k] = uri_diff[sub][k][:50]
        # Cap the number of tables whose variables are enumerated to keep the
        # report readable when dozens of tables in one dep module differ.
        if len(uri_diff["table_variables"]) > 50:
            uri_diff["table_variables_truncated_total"] = len(
                uri_diff["table_variables"]
            )
            uri_diff["table_variables"] = dict(
                list(uri_diff["table_variables"].items())[:50]
            )

    return module_result


def _summary_line(r: dict) -> str:
    if r.get("error"):
        return f"💥  {r['file']:40} ERROR: {r['error'][:80]}"
    if (r.get("tags") or []) == ["empty_by_design"]:
        return f"⚪  {r['file']:40} (empty by design, 0 ops both sides)"

    tag_to_emoji = {
        "clean": "✅",
        "finding1_dpmcore_extra_ops": "📈",
        "finding2_precondition_naming": "🔤",
        "finding3_tables_vars_missing": "📉",
        "finding4_dep_uri_missing_in_new": "🔻",
        "finding4_dep_uri_extra_in_new": "🔺",
        "finding5_dep_over_declaration": "🌊",
        "finding6_dep_under_declaration": "🕳️",
        "finding7_intra_classification_diff": "🏷️",
        "finding8_cross_dependency_diff": "🔗",
        "finding9_alternative_deps_diff": "🔀",
        "unclassified": "❓",
    }
    tags = r.get("tags") or []
    emoji = "".join(dict.fromkeys(tag_to_emoji.get(t, "?") for t in tags))
    cmp = r["comparison"]
    ops = cmp["operations"]
    tabs = cmp["tables"]
    vars_ = cmp["variables"]
    pcs = cmp["preconditions"]
    dm = cmp.get("dependency_modules") or {}
    dm_tot = r.get("dep_module_totals") or {}
    dm_over = (
        dm_tot.get("tables_only_in_new_total", 0)
        + dm_tot.get("variables_only_in_new_total", 0)
        + dm_tot.get("table_variables_only_in_new_total", 0)
    )
    dm_under = (
        dm_tot.get("tables_only_in_ref_total", 0)
        + dm_tot.get("variables_only_in_ref_total", 0)
        + dm_tot.get("table_variables_only_in_ref_total", 0)
    )
    di_tot = r.get("dep_info_totals") or {}
    intra_diff = di_tot.get("intra_only_in_new", 0) + di_tot.get(
        "intra_only_in_ref", 0
    )
    cross_diff = (
        di_tot.get("cross_only_in_new", 0)
        + di_tot.get("cross_only_in_ref", 0)
        + di_tot.get("cross_affected_op_diffs", 0)
    )
    return (
        f"{emoji:4} {r['file']:40} "
        f"ops={ops['new_count']:>4}/{ops['ref_count']:<4} "
        f"(+{len(ops['only_in_new']):>3}/-{len(ops['only_in_ref']):>3}) "
        f"tables={tabs['new_count']:>3}/{tabs['ref_count']:<3} "
        f"vars={vars_['new_count']:>5}/{vars_['ref_count']:<5} "
        f"pc_ast={pcs['ast_matched']:>2}/{pcs['ref_count']:<2} "
        f"pc_naming_diff={pcs['naming_mismatches']:>2} "
        f"dm={dm.get('new_count', 0):>2}/{dm.get('ref_count', 0):<2} "
        f"(+{dm_over:>4}/-{dm_under:<4}) "
        f"di_intra_diff={intra_diff:>3} "
        f"di_cross_diff={cross_diff:>3} "
        f"tags={','.join(tags)}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=_DEFAULT_DB)
    parser.add_argument("--refs-dir", default=str(_REFERENCES_DIR))
    parser.add_argument("--out-json", default="scripts/parity_report.json")
    parser.add_argument("--out-txt", default="scripts/parity_report.txt")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process only the first N reference files (for quick iteration)",
    )
    args = parser.parse_args()

    refs_dir = Path(args.refs_dir)
    ref_files = sorted(refs_dir.glob("*.json"))
    if args.limit:
        ref_files = ref_files[: args.limit]
    if not ref_files:
        print(f"No JSON references in {refs_dir}", file=sys.stderr)
        return 1

    print(f"Checking {len(ref_files)} modules against MDPM references…")
    print(f"DB: {args.db}\n")

    engine = create_engine(args.db)
    results = []
    with Session(engine) as session:
        for i, ref_path in enumerate(ref_files, 1):
            r = check_module(session, ref_path)
            results.append(r)
            print(f"[{i:>3}/{len(ref_files)}] {_summary_line(r)}")

    # Aggregate
    by_tag: dict[str, int] = {}
    errored = 0
    for r in results:
        if r.get("error"):
            errored += 1
            continue
        for t in r.get("tags") or []:
            by_tag[t] = by_tag.get(t, 0) + 1

    print("\n" + "=" * 70)
    print(f"  Modules processed : {len(results)}")
    print(f"  Errors            : {errored}")
    print("  Tag breakdown     :")
    for tag, count in sorted(by_tag.items(), key=lambda x: -x[1]):
        print(f"    {tag:40} {count}")
    print("=" * 70)

    Path(args.out_json).write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8"
    )
    Path(args.out_txt).write_text(
        "\n".join(_summary_line(r) for r in results) + "\n",
        encoding="utf-8",
    )
    print(f"\nReport JSON: {args.out_json}")
    print(f"Report TXT : {args.out_txt}")

    return 0 if errored == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
