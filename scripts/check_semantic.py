"""Check DPM-XL expression semantics for all OperationVersion rules."""

import argparse
import csv
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from dpmcore.services.semantic import SemanticService

_DEFAULT_DB = (
    Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "test_data.db"
)

WIDTH = 80
BAR = "=" * WIDTH

_TTY = sys.stdout.isatty()
_GREEN = "\033[32m" if _TTY else ""
_RED = "\033[31m" if _TTY else ""
_DIM = "\033[2m" if _TTY else ""
_RESET = "\033[0m" if _TTY else ""


def _fmt_size(path: Path) -> str:
    mb = path.stat().st_size / (1024 * 1024)
    return f"{mb:.1f} MB"


def _fmt_duration(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def _load_rows(db_path: Path):
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT
                    ov.OperationVID,
                    o.Code,
                    r.Code  AS ReleaseCode,
                    ov.Expression
                FROM OperationVersion ov
                JOIN   Operation o ON o.OperationID = ov.OperationID
                LEFT JOIN Release r ON r.ReleaseID  = ov.StartReleaseID
                WHERE  ov.Expression IS NOT NULL
                  AND  trim(ov.Expression) != ''
                ORDER BY o.Code, ov.OperationVID
                """
            )
        ).fetchall()
    engine.dispose()
    return rows


def main() -> int:
    """Run semantic validation on all OperationVersion rules in the DB."""
    parser = argparse.ArgumentParser(
        description=(
            "Check DPM-XL expression semantics for all rules in the DB."
        ),
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=_DEFAULT_DB,
        help=f"Path to the SQLite DPM database (default: {_DEFAULT_DB})",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=None,
        help=(
            "Path for the failures CSV output "
            "(default: <db_stem>_failures.csv next to the DB)"
        ),
    )
    args = parser.parse_args()

    db_path: Path = args.db.resolve()
    if not db_path.exists():
        print(f"ERROR: database not found: {db_path}", file=sys.stderr)
        return 1

    csv_path: Path = (
        args.csv.resolve()
        if args.csv
        else db_path.parent / f"{db_path.stem}_failures.csv"
    )

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------
    print(f"\n{BAR}")
    print("  DPM Semantic Validation Runner")
    print(BAR)

    rows = _load_rows(db_path)
    total = len(rows)
    total_str = f"{total:,}"
    counter_width = len(str(total))

    print(f"  Database   : {db_path}")
    print(f"  Size       : {_fmt_size(db_path)}")
    print(f"  Validations: {total:,}")
    print(f"  CSV output : {csv_path}")
    print(
        "  Started    : "
        + datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    )
    print(BAR)
    print()

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------
    engine = create_engine(f"sqlite:///{db_path}")
    session = sessionmaker(bind=engine)()
    svc = SemanticService(session)

    passed = 0
    failures = []

    t_start = time.monotonic()

    for i, (operation_vid, op_code, release_code, expression) in enumerate(
        rows, 1
    ):
        label = op_code or str(operation_vid)
        release = release_code or ""

        result = svc.validate(expression.strip(), release_code=release or None)

        idx = f"[{i:{counter_width},}/{total_str}]"
        preview = expression.replace("\n", " ").strip()
        line = f"{idx} {label:<12} {_DIM}{preview}{_RESET}"

        if result.is_valid:
            passed += 1
            print(f"{line}  {_GREEN}PASS{_RESET}")
        else:
            err = result.error_message or "(no message)"
            err_code = result.error_code or ""
            failures.append(
                (
                    i,
                    operation_vid,
                    label,
                    release,
                    expression.strip(),
                    err_code,
                    err,
                )
            )
            print(f"{line}  {_RED}FAIL{_RESET}")
            print(f"  {_DIM}└─{_RESET} {err}")

    session.close()
    engine.dispose()

    elapsed = time.monotonic() - t_start
    failed = len(failures)
    pct_pass = passed / total * 100 if total else 0.0
    pct_fail = failed / total * 100 if total else 0.0

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print()
    print(BAR)
    print("  SUMMARY")
    print(BAR)
    print(f"  Database   : {db_path}")
    print(f"  Size       : {_fmt_size(db_path)}")
    print(f"  Total      : {total:,}")
    print(f"  {_GREEN}Passed{_RESET}     : {passed:,}  ({pct_pass:.1f}%)")
    print(f"  {_RED}Failed{_RESET}     : {failed:,}  ({pct_fail:.1f}%)")
    print(f"  Duration   : {_fmt_duration(elapsed)}")
    print(BAR)

    # ------------------------------------------------------------------
    # Failures list
    # ------------------------------------------------------------------
    if failures:
        print()
        print(BAR)
        print("  FAILURES")
        print(BAR)
        for (
            idx,
            _operation_vid,
            label,
            release,
            expression,
            _err_code,
            error,
        ) in failures:
            idx_str = f"[{idx:{counter_width},}/{total_str}]"
            release_info = f" | release: {release}" if release else ""
            print(f"\n{idx_str} {label}{release_info}")
            print(f"  Expression : {expression}")
            print(f"  Error      : {error}")
        print()
        print(BAR)

        with csv_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(
                [
                    "index",
                    "operation_vid",
                    "code",
                    "release",
                    "error_code",
                    "error",
                    "expression",
                ]
            )
            for (
                idx,
                operation_vid,
                label,
                release,
                expression,
                err_code,
                error,
            ) in failures:
                writer.writerow(
                    [
                        idx,
                        operation_vid,
                        label,
                        release,
                        err_code,
                        error,
                        expression,
                    ]
                )
        print(f"\n  CSV written: {csv_path}")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
