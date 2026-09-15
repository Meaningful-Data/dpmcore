#!/usr/bin/env python
"""Check that ``dpmcore export-calculations`` matches drr_operations'.

The calculations export is a downstream contract (the KRI/CODIS
deployment reads it), so the acceptance test for the dpmcore
implementation is a diff against the EBA ``drr_operations`` script over
the same database. This runs both, compares the JSON outputs, and prints
a compact verdict per module: byte-identical, content-identical (same
JSON, different key order), or different — with a breakdown of where.

It cannot run in CI: it needs a private drr_operations checkout and a
reachable DPM SQL Server. Run it by hand whenever the export pipeline
changes.

Usage (both defaults come from the environment, see below):

    python scripts/check_export_parity.py
    python scripts/check_export_parity.py --modules KRI \
        --reference-date 2026-12-31
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# Both defaults describe a local parity setup and differ per developer,
# so they come from the environment rather than being baked in:
#   DPM_PARITY_DB_URL   SQLAlchemy URL of the DPM database to compare against
#   DPM_PARITY_DRR_PATH checkout of the EBA drr_operations repository
_DRR_PATH_ENV = os.environ.get("DPM_PARITY_DRR_PATH")
DEFAULT_DRR_PATH = Path(_DRR_PATH_ENV) if _DRR_PATH_ENV else None
DEFAULT_DB_URL = os.environ.get("DPM_PARITY_DB_URL")
DEFAULT_WORKDIR = Path("/tmp/export_parity")  # noqa: S108
PUBLICATION_DATE = "2026-01-01"


def _read_env_file(path):
    """Parse a KEY=VALUE .env file into a dict."""
    env = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                env[key.strip()] = value.strip()
    return env


def _run_eba(drr_path, module, reference_date, output):
    """Run drr_operations' export_calculations for *module*."""
    env = dict(os.environ)
    env.update(_read_env_file(drr_path / ".env"))
    cmd = [
        str(drr_path / ".venv" / "bin" / "python"),
        "development/export_calculations.py",
        module,
        "--reference-date",
        reference_date,
        "--publication-date",
        PUBLICATION_DATE,
        "--output",
        str(output),
    ]
    return subprocess.run(  # noqa: S603
        cmd, cwd=drr_path, env=env, capture_output=True, text=True
    )


def _run_dpmcore(module, reference_date, db_url, output):
    """Run ``dpmcore export-calculations`` for *module*."""
    cmd = [
        sys.executable,
        "-c",
        "from dpmcore.cli.main import main; main()",
        "export-calculations",
        "--module-code",
        module,
        "--reference-date",
        reference_date,
        "--publication-date",
        PUBLICATION_DATE,
        "--database",
        db_url,
        "--output",
        str(output),
        "--datapoints-output",
        str(_datapoints_path(output)),
    ]
    return subprocess.run(cmd, capture_output=True, text=True)  # noqa: S603


def _datapoints_path(output):
    """The companion datapoint file next to an export file."""
    return output.with_name(f"{output.stem}_datapoints.json")


def _strip_ref_ids(obj):
    """Drop operand_reference_id fields (counter, order-dependent)."""
    if isinstance(obj, dict):
        return {
            k: _strip_ref_ids(v)
            for k, v in obj.items()
            if k != "operand_reference_id"
        }
    if isinstance(obj, list):
        return [_strip_ref_ids(x) for x in obj]
    return obj


def _pair_by_code(block):
    """Pair a calculations block's children with their operation codes.

    Returns ``(mapping, problems)``. A code that is null or repeated
    cannot identify a calculation, so those children are reported
    instead of silently collapsing onto one key.
    """
    codes = block["operation_codes"]
    children = block["ast"]["children"]
    problems = []
    if len(codes) != len(children):
        problems.append(
            f"{len(codes)} operation_codes for {len(children)} calculations"
        )
    mapping = {}
    duplicates = set()
    for code, child in zip(codes, children):  # noqa: B905
        if code is None:
            problems.append("una calculation sin operation_code (null)")
            continue
        if code in mapping:
            duplicates.add(code)
            continue
        mapping[code] = child
    if duplicates:
        problems.append(f"operation_codes repetidos: {sorted(duplicates)}")
    return mapping, problems


def _compare_calculations(ns_a, ns_b):
    """Compare the calculations block, pairing children by operation code.

    Returns a list of human-readable difference lines (empty = equal
    up to calculation order).
    """
    ca, cb = ns_a["calculations"], ns_b["calculations"]
    map_a, problems_a = _pair_by_code(ca)
    map_b, problems_b = _pair_by_code(cb)
    diffs = [f"drr_operations: {p}" for p in problems_a]
    diffs += [f"dpmcore: {p}" for p in problems_b]

    only_a = sorted(set(map_a) - set(map_b))
    only_b = sorted(set(map_b) - set(map_a))
    if only_a:
        diffs.append(f"solo en drr_operations: {only_a[:10]}")
    if only_b:
        diffs.append(f"solo en dpmcore: {only_b[:10]}")
    changed = [
        code
        for code in sorted(set(map_a) & set(map_b))
        if _strip_ref_ids(map_a[code]) != _strip_ref_ids(map_b[code])
    ]
    if changed:
        diffs.append(
            f"{len(changed)} calculations con AST distinto: {changed[:10]}"
        )
    if ca["operation_codes"] != cb["operation_codes"] and not diffs:
        diffs.append(
            "mismas calculations pero en distinto orden "
            "(orden de filas de la BD, no contractual)"
        )
    return diffs


def _is_export_document(obj):
    """Whether *obj* is a calculations export (one URI → one namespace)."""
    if not isinstance(obj, dict) or len(obj) != 1:
        return False
    namespace = next(iter(obj.values()))
    return isinstance(namespace, dict) and "calculations" in namespace


def _compare_pair(name, file_a, file_b):
    """Compare one output file pair; print verdict; return ok bool."""
    for label, path in (("drr_operations", file_a), ("dpmcore", file_b)):
        if not path.exists():
            print(f"  {name}: FALTA el fichero de {label} ({path})")
            return False

    bytes_a = file_a.read_bytes()
    bytes_b = file_b.read_bytes()
    if bytes_a == bytes_b:
        print(f"  {name}: IGUALES (byte a byte)")
        return True

    a = json.loads(bytes_a)
    b = json.loads(bytes_b)
    if a == b:
        print(
            f"  {name}: IGUALES en contenido (solo cambia el orden de claves)"
        )
        return True

    if not (_is_export_document(a) and _is_export_document(b)):
        print(f"  {name}: DIFIEREN (contenido JSON distinto)")
        return False

    if list(a) != list(b):
        print(f"  {name}: DIFIEREN — URI del módulo distinta")
        return False

    ns_a, ns_b = next(iter(a.values())), next(iter(b.values()))
    print(f"  {name}: DIFIEREN — detalle por sección:")
    for key in sorted(set(ns_a) | set(ns_b)):
        if key == "calculations":
            continue
        state = "igual" if ns_a.get(key) == ns_b.get(key) else "DISTINTO"
        print(f"    - {key}: {state}")
    for line in _compare_calculations(ns_a, ns_b) or ["calculations: igual"]:
        print(f"    - {line}")
    return False


def _parse_args():
    """Parse the command line."""
    parser = argparse.ArgumentParser(
        description="Compare drr_operations vs dpmcore calculation exports"
    )
    parser.add_argument("--modules", nargs="+", default=["KRI", "CODIS"])
    parser.add_argument("--reference-date", default="2026-12-31")
    parser.add_argument(
        "--db-url",
        default=DEFAULT_DB_URL,
        required=DEFAULT_DB_URL is None,
        help="SQLAlchemy URL of the DPM database (env DPM_PARITY_DB_URL)",
    )
    parser.add_argument(
        "--drr-path",
        type=Path,
        default=DEFAULT_DRR_PATH,
        required=DEFAULT_DRR_PATH is None,
        help="Path to the drr_operations checkout (env DPM_PARITY_DRR_PATH)",
    )
    parser.add_argument("--workdir", type=Path, default=DEFAULT_WORKDIR)
    return parser.parse_args()


def _check_module(args, module):
    """Export *module* with both pipelines and compare; return a verdict."""
    eba_out = args.workdir / f"eba_{module}.json"
    dpm_out = args.workdir / f"dpmcore_{module}.json"

    print("  exportando con drr_operations...")
    proc = _run_eba(args.drr_path, module, args.reference_date, eba_out)
    if proc.returncode != 0 or not eba_out.exists():
        print(f"  ERROR drr_operations: {proc.stderr.strip()[-300:]}")
        return "ERROR drr_operations"

    print("  exportando con dpmcore...")
    proc = _run_dpmcore(module, args.reference_date, args.db_url, dpm_out)
    if proc.returncode != 0 or not dpm_out.exists():
        print(f"  ERROR dpmcore: {proc.stderr.strip()[-300:]}")
        return "ERROR dpmcore"

    ok_main = _compare_pair("export", eba_out, dpm_out)
    ok_dp = _compare_pair(
        "datapoints",
        _datapoints_path(eba_out),
        _datapoints_path(dpm_out),
    )
    return "OK" if ok_main and ok_dp else "DIFERENCIAS"


def main():
    """Run both exporters per module, compare, and print a summary."""
    args = _parse_args()
    args.workdir.mkdir(parents=True, exist_ok=True)

    results = {}
    for module in args.modules:
        print(f"\n=== {module} ===")
        results[module] = _check_module(args, module)

    print("\n=== RESUMEN ===")
    for module, verdict in results.items():
        print(f"  {module}: {verdict}")
    print(f"  (ficheros en {args.workdir})")
    return 0 if all(v == "OK" for v in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
