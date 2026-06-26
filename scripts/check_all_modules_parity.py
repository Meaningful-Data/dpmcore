"""Run the DB-driven validations-script generation for every MDPM reference
module and diff the result against the reference.

Each reference file `scripts/mdpm_references/<MODULE>-<VERSION>.json` defines
one module to test. For each, we:
  1. Call `generate_module` (DB → ASTGeneratorService) to produce dpmcore's
     equivalent JSON in memory.
  2. Compare four blocks against the MDPM reference: operations, preconditions,
     tables, variables.
  3. Aggregate per-module deltas and totals, categorise findings against the
     three known divergence classes (see
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

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from generate_module_from_db import generate_module


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
        "only_in_ref_ast": [list(k) for k in sorted(ref_keys - new_keys, key=lambda x: str(x))],
        "only_in_new_ast": [list(k) for k in sorted(new_keys - ref_keys, key=lambda x: str(x))],
        "naming_mismatches": naming_mismatches,
        "affected_operations_mismatches": affected_op_mismatches,
    }


def _classify(module_result: dict) -> list[str]:
    """Tag each module with the known finding labels that explain its deltas.
    Anything left unexplained surfaces as 'unclassified'."""
    tags: list[str] = []
    cmp = module_result.get("comparison") or {}
    ops = cmp.get("operations") or {}
    pcs = cmp.get("preconditions") or {}
    tabs = cmp.get("tables") or {}

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

    # Anything else weird → unclassified
    unexplained = (
        bool(ops.get("only_in_ref"))   # MDPM-only ops (dpmcore should have ALL)
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
        msg = (result.get("error") or "")
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
        },
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
        "unclassified": "❓",
    }
    tags = r.get("tags") or []
    emoji = "".join(dict.fromkeys(tag_to_emoji.get(t, "?") for t in tags))
    cmp = r["comparison"]
    ops = cmp["operations"]
    tabs = cmp["tables"]
    vars_ = cmp["variables"]
    pcs = cmp["preconditions"]
    return (
        f"{emoji:4} {r['file']:40} "
        f"ops={ops['new_count']:>4}/{ops['ref_count']:<4} "
        f"(+{len(ops['only_in_new']):>3}/-{len(ops['only_in_ref']):>3}) "
        f"tables={tabs['new_count']:>3}/{tabs['ref_count']:<3} "
        f"vars={vars_['new_count']:>5}/{vars_['ref_count']:<5} "
        f"pc_ast={pcs['ast_matched']:>2}/{pcs['ref_count']:<2} "
        f"pc_naming_diff={pcs['naming_mismatches']:>2} "
        f"tags={','.join(tags)}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=_DEFAULT_DB)
    parser.add_argument("--refs-dir", default=str(_REFERENCES_DIR))
    parser.add_argument("--out-json", default="scripts/parity_report.json")
    parser.add_argument("--out-txt", default="scripts/parity_report.txt")
    parser.add_argument(
        "--limit", type=int, default=None,
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
