#!/usr/bin/env python
"""Check that dpmcore's export_calculations matches drr_operations'.

Runs both export scripts for the given modules against the same
database, compares the JSON outputs, and prints a compact summary:
byte-identical, content-identical (same JSON, different key/row
order), or different — with a rough breakdown of where they diverge.

Usage (defaults target the local DPM_EBA SQL Server container):

    python scripts/check_export_parity.py
    python scripts/check_export_parity.py --modules KRI \
        --reference-date 2026-12-31

Requires the drr_operations checkout (its .venv and .env) and a
reachable database; see --drr-path and --db-url.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

DEFAULT_DRR_PATH = Path.home() / "dev" / "EBA" / "drr_operations"
DEFAULT_DB_URL = (
    "mssql+pyodbc://SA:DRR%40local1@localhost:1433/DPM_EBA"
    "?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
)
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
    import os

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
    """Run dpmcore's export_calculations for *module*."""
    script = Path(__file__).with_name("export_calculations.py")
    cmd = [
        sys.executable,
        str(script),
        module,
        "--reference-date",
        reference_date,
        "--publication-date",
        PUBLICATION_DATE,
        "--db",
        db_url,
        "--output",
        str(output),
    ]
    return subprocess.run(  # noqa: S603
        cmd, capture_output=True, text=True
    )


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


def _compare_calculations(ns_a, ns_b):
    """Compare the calculations block pairing children by operation code.

    Returns a list of human-readable difference lines (empty = equal
    up to calculation order).
    """
    diffs = []
    ca, cb = ns_a["calculations"], ns_b["calculations"]
    map_a = dict(
        zip(ca["operation_codes"], ca["ast"]["children"], strict=False)
    )
    map_b = dict(
        zip(cb["operation_codes"], cb["ast"]["children"], strict=False)
    )
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


def _compare_pair(name, file_a, file_b):
    """Compare one output file pair; print verdict; return ok bool."""
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

    # Main export: compare section by section
    if isinstance(a, dict) and len(a) == 1 and "calculations" in str(a):
        ns_a, ns_b = next(iter(a.values())), next(iter(b.values()))
        if list(a) != list(b):
            print(f"  {name}: DIFIEREN — URI del módulo distinta")
            return False
        print(f"  {name}: DIFIEREN — detalle por sección:")
        for key in sorted(set(ns_a) | set(ns_b)):
            if key == "calculations":
                continue
            state = "igual" if ns_a.get(key) == ns_b.get(key) else "DISTINTO"
            print(f"    - {key}: {state}")
        for line in _compare_calculations(ns_a, ns_b) or [
            "calculations: igual"
        ]:
            print(f"    - {line}")
    else:
        print(f"  {name}: DIFIEREN (contenido JSON distinto)")
    return False


def main():
    """Run both exporters per module, compare, and print a summary."""
    parser = argparse.ArgumentParser(
        description="Compare drr_operations vs dpmcore calculation exports"
    )
    parser.add_argument("--modules", nargs="+", default=["KRI", "CODIS"])
    parser.add_argument("--reference-date", default="2026-12-31")
    parser.add_argument("--db-url", default=DEFAULT_DB_URL)
    parser.add_argument("--drr-path", type=Path, default=DEFAULT_DRR_PATH)
    parser.add_argument("--workdir", type=Path, default=DEFAULT_WORKDIR)
    args = parser.parse_args()

    args.workdir.mkdir(parents=True, exist_ok=True)
    results = {}

    for module in args.modules:
        print(f"\n=== {module} ===")
        eba_out = args.workdir / f"eba_{module}.json"
        dpm_out = args.workdir / f"dpmcore_{module}.json"

        print("  exportando con drr_operations...")
        proc = _run_eba(args.drr_path, module, args.reference_date, eba_out)
        if proc.returncode != 0 or not eba_out.exists():
            print(f"  ERROR drr_operations: {proc.stderr.strip()[-300:]}")
            results[module] = "ERROR drr_operations"
            continue

        print("  exportando con dpmcore...")
        proc = _run_dpmcore(module, args.reference_date, args.db_url, dpm_out)
        if proc.returncode != 0 or not dpm_out.exists():
            print(f"  ERROR dpmcore: {proc.stderr.strip()[-300:]}")
            results[module] = "ERROR dpmcore"
            continue

        ok_main = _compare_pair("export", eba_out, dpm_out)
        ok_dp = _compare_pair(
            "datapoints",
            eba_out.with_name(f"eba_{module}_datapoints.json"),
            dpm_out.with_name(f"dpmcore_{module}_datapoints.json"),
        )
        results[module] = "OK" if ok_main and ok_dp else "DIFERENCIAS"

    print("\n=== RESUMEN ===")
    for module, verdict in results.items():
        print(f"  {module}: {verdict}")
    print(f"  (ficheros en {args.workdir})")
    return 0 if all(v == "OK" for v in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
