"""Generate a validations-script JSON for a module directly from the DPM DB.

Pulls every validation OperationVersion scoped to the given ModuleVersion,
together with its precondition (via PreconditionOperationVID) and severity
(OperationScope.Severity), then hands them to ASTGeneratorService.script —
the same internal workflow used by `dpmcore generate-script`, but seeded
from the DB instead of an external expressions file.

Output shape matches `scripts/mdpm_references/<MODULE>-<VERSION>.json`, so it
can be diffed against the MDPM reference for parity checking.

Usage:
    poetry run python scripts/generate_module_from_db.py IRRBB 1.2.0
    poetry run python scripts/generate_module_from_db.py IRRBB 1.2.0 \\
        --db sqlite:///dpm_4.2.1_20260624.db --out IRRBB-1.2.0.json
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from dpmcore.services.ast_generator import ASTGeneratorService


def _load_module(session: Session, module_code: str, module_version: str):
    sql = text(
        """
        SELECT
            ov.OperationVID         AS vid,
            o.Code                  AS code,
            ov.Expression           AS expression,
            ov.PreconditionOperationVID AS precond_vid,
            os.Severity             AS severity,
            pov.Expression          AS precond_expression,
            po.Code                 AS precond_code
        FROM OperationVersion ov
        JOIN Operation o ON o.OperationID = ov.OperationID
        JOIN OperationScope os ON os.OperationVID = ov.OperationVID
        JOIN OperationScopeComposition osc
            ON osc.OperationScopeID = os.OperationScopeID
        JOIN ModuleVersion mv ON mv.ModuleVID = osc.ModuleVID
        LEFT JOIN OperationVersion pov
            ON pov.OperationVID = ov.PreconditionOperationVID
        LEFT JOIN Operation po ON po.OperationID = pov.OperationID
        WHERE mv.Code = :code
          AND mv.VersionNumber = :version
          AND o.Type = 'validation'
          AND ov.Expression IS NOT NULL
          AND trim(ov.Expression) != ''
        ORDER BY o.Code, ov.OperationVID
        """
    )
    return (
        session.execute(sql, {"code": module_code, "version": module_version})
        .mappings()
        .all()
    )


def generate_module(
    session: Session,
    module_code: str,
    module_version: str,
    release: str | None = None,
) -> dict:
    """Run the DB → ASTGeneratorService pipeline for one module.

    Returns the raw `script()` result dict ({"success", "enriched_ast",
    "error"}) plus an "input_stats" key with the count of expressions and
    preconditions pulled from the DB.
    """
    rows = _load_module(session, module_code, module_version)
    if not rows:
        return {
            "success": False,
            "enriched_ast": None,
            "error": (
                f"No validations found for {module_code} {module_version}"
            ),
            "input_stats": {"expressions": 0, "preconditions": 0},
        }

    expressions = [(r["expression"], r["code"]) for r in rows]
    severities = {r["code"]: r["severity"] for r in rows if r["severity"]}

    precond_to_codes: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        if r["precond_vid"] is None or not r["precond_expression"]:
            continue
        precond_to_codes[r["precond_expression"]].append(r["code"])
    preconditions = [
        (expr, codes) for expr, codes in precond_to_codes.items()
    ] or None

    svc = ASTGeneratorService(session)
    result = svc.script(
        expressions=expressions,
        module_code=module_code,
        module_version=module_version,
        preconditions=preconditions,
        severities=severities or None,
        release=release,
    )
    result["input_stats"] = {
        "expressions": len(expressions),
        "preconditions": len(precond_to_codes),
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("module_code", help="Module code, e.g. IRRBB")
    parser.add_argument("module_version", help="Module version, e.g. 1.2.0")
    parser.add_argument(
        "--db",
        default="sqlite:///dpm_4.2.1_20260624.db",
        help="SQLAlchemy DB URL (default: %(default)s)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output path (default: <MODULE>-<VERSION>.json in cwd)",
    )
    parser.add_argument(
        "--release",
        default=None,
        help="Optional release code (default: auto-resolved by dpmcore)",
    )
    args = parser.parse_args()

    out_path = Path(
        args.out or f"{args.module_code}-{args.module_version}.json"
    )

    engine = create_engine(args.db)
    with Session(engine) as session:
        result = generate_module(
            session,
            args.module_code,
            args.module_version,
            release=args.release,
        )

    stats = result.get("input_stats", {})
    print(
        f"Loaded {stats.get('expressions', 0)} validations, "
        f"{stats.get('preconditions', 0)} distinct preconditions from DB."
    )

    if not result.get("success"):
        print(
            f"Script generation failed: {result.get('error')}", file=sys.stderr
        )
        return 2

    out_path.write_text(
        json.dumps(result["enriched_ast"], indent=2, default=str),
        encoding="utf-8",
    )
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
