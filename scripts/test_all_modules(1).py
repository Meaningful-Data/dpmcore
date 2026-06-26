"""test_all_modules.py
===================
QA completo: procesa todos los ficheros JSON de MDPM en scripts/mdpm_references/,
llama a DPMcore con todas las operaciones y precondiciones de cada módulo,
y compara los resultados.

Uso:
    poetry run python scripts/test_all_modules.py

Salida:
    - Resumen por pantalla
    - scripts/qa_report.json   con el detalle completo
    - scripts/qa_report.txt    con el informe legible
"""

import json
import sys
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────────────────────────────────────

DB_URL = "sqlite:///dpm_4.2.1_20260624.db"
REFERENCES_DIR = Path("scripts/mdpm_references")
REPORT_JSON = Path("scripts/qa_report.json")
REPORT_TXT = Path("scripts/qa_report.txt")


# ─────────────────────────────────────────────────────────────────────────────
# EXTRACCIÓN DEL JSON DE MDPM
# ─────────────────────────────────────────────────────────────────────────────


def ast_to_precond_items(ast: dict) -> list:
    """Extrae todas las PreconditionItem del AST como lista de expresiones simples
    'X := true'. DPMcore las combina internamente al recibir varias tuplas
    para la misma operación — no acepta expresiones compuestas con 'and'/'or'.
    """
    cn = ast.get("class_name", "")
    if cn == "PreconditionItem":
        return [f"{ast['variable_code']} := true"]
    elif cn == "BinOp":
        return ast_to_precond_items(ast["left"]) + ast_to_precond_items(
            ast["right"]
        )
    elif cn == "ParExpr":
        return ast_to_precond_items(ast["expression"])
    return []


def extract_mdpm(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    root_key = list(raw.keys())[0]
    mod = raw[root_key]

    operations = {
        code: {
            "expression": op["expression"],
            "severity": op["severity"],
            "from_submission_date": op.get("from_submission_date"),
            "version_id": op.get("version_id"),
        }
        for code, op in mod.get("operations", {}).items()
    }

    # Construimos la lista de precondiciones como (expr_simple, [ops])
    # Una precondición compuesta (A and B) se desglosa en dos tuplas separadas:
    #   ("A := true", [ops])
    #   ("B := true", [ops])
    precondition_tuples = []  # lista final para DPMcore
    for pc in mod.get("preconditions", {}).values():
        items = ast_to_precond_items(pc["ast"])
        for item_expr in items:
            precondition_tuples.append((item_expr, pc["affected_operations"]))

    return {
        "module_code": mod["module_code"],
        "module_version": mod["module_version"],
        "operations": operations,
        "precondition_tuples": precondition_tuples,
        # referencia MDPM para comparar
        "mdpm_tables": mod.get("tables", {}),
        "mdpm_variables": mod.get("variables", {}),
        "mdpm_precondition_variables": mod.get("precondition_variables", {}),
        "mdpm_dependency_information": mod.get("dependency_information", {}),
    }


# ─────────────────────────────────────────────────────────────────────────────
# LLAMADA A DPMCORE
# ─────────────────────────────────────────────────────────────────────────────


def call_dpmcore(db, mdpm: dict) -> tuple:
    expressions = [
        (op["expression"], code) for code, op in mdpm["operations"].items()
    ]

    severities = {
        code: op["severity"]
        for code, op in mdpm["operations"].items()
        if op.get("severity")
    }

    raw = db.services.ast_generator.script(
        expressions=expressions,
        module_code=mdpm["module_code"],
        module_version=mdpm["module_version"],
        preconditions=mdpm["precondition_tuples"]
        if mdpm["precondition_tuples"]
        else None,
        severities=severities or None,
    )

    if not raw.get("success"):
        raise RuntimeError(raw.get("error", "unknown error"))

    enriched = raw["enriched_ast"]
    uri_keys = [k for k in enriched if k.startswith("http")]
    if uri_keys:
        return enriched[uri_keys[0]], uri_keys[0]
    return enriched, "(root)"


# ─────────────────────────────────────────────────────────────────────────────
# COMPARACIÓN
# ─────────────────────────────────────────────────────────────────────────────


def compare_module(mdpm: dict, dpm_mod: dict) -> dict:
    ops_ok = []
    ops_diff_expr = []
    ops_diff_sev = []
    ops_missing = []

    dpm_ops = dpm_mod.get("operations", {})

    for code, ref_op in mdpm["operations"].items():
        if code not in dpm_ops:
            ops_missing.append(code)
            continue

        dpm_op = dpm_ops[code]
        expr_ok = (
            ref_op["expression"].strip()
            == (dpm_op.get("expression") or "").strip()
        )
        sev_ok = ref_op["severity"] == dpm_op.get("severity")

        if expr_ok and sev_ok:
            ops_ok.append(code)
        else:
            if not expr_ok:
                ops_diff_expr.append(
                    {
                        "code": code,
                        "mdpm": ref_op["expression"],
                        "dpmcore": dpm_op.get("expression"),
                    }
                )
            if not sev_ok:
                ops_diff_sev.append(
                    {
                        "code": code,
                        "mdpm": ref_op["severity"],
                        "dpmcore": dpm_op.get("severity"),
                    }
                )

    mdpm_tables = mdpm["mdpm_tables"]
    dpm_tables = dpm_mod.get("tables", {})
    tables_missing = [t for t in mdpm_tables if t not in dpm_tables]

    mdpm_vars = mdpm["mdpm_variables"]
    dpm_vars = dpm_mod.get("variables", {})
    vars_diff = {
        k: {"mdpm": v, "dpmcore": dpm_vars.get(k)}
        for k, v in mdpm_vars.items()
        if dpm_vars.get(k) != v
    }

    mdpm_dep = mdpm["mdpm_dependency_information"]
    dpm_dep = dpm_mod.get("dependency_information", {})
    mdpm_intra = set(mdpm_dep.get("intra_instance_validations", []))
    dpm_intra = set(dpm_dep.get("intra_instance_validations", []))
    intra_missing = sorted(mdpm_intra - dpm_intra)

    return {
        "total_ops": len(mdpm["operations"]),
        "ops_ok": len(ops_ok),
        "ops_diff_expr": ops_diff_expr,
        "ops_diff_sev": ops_diff_sev,
        "ops_missing": ops_missing,
        "tables_missing": tables_missing,
        "vars_diff": vars_diff,
        "intra_missing": intra_missing,
        "passed": (
            len(ops_diff_expr) == 0
            and len(ops_diff_sev) == 0
            and len(ops_missing) == 0
            and len(tables_missing) == 0
            and len(vars_diff) == 0
            and len(intra_missing) == 0
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# INFORME
# ─────────────────────────────────────────────────────────────────────────────


def write_report(results: list, txt_path: Path, json_path: Path):
    lines = []
    lines.append("=" * 70)
    lines.append("  QA REPORT — DPMcore vs MDPM — todos los módulos")
    lines.append("=" * 70)

    passed = [r for r in results if r.get("passed")]
    errors = [r for r in results if r.get("error")]
    failed = [r for r in results if not r.get("passed") and not r.get("error")]

    lines.append(f"\n  Total módulos procesados  : {len(results)}")
    lines.append(f"  ✅ Pasaron                : {len(passed)}")
    lines.append(f"  ❌ Fallaron (datos)        : {len(failed)}")
    lines.append(f"  💥 Error al llamar DPMcore : {len(errors)}")
    lines.append("")

    for r in results:
        tag = "✅" if r.get("passed") else ("💥" if r.get("error") else "❌")
        lines.append(
            f"\n{tag}  {r['module_code']} {r['module_version']}  ({r['file']})"
        )

        if r.get("error"):
            lines.append(f"     ERROR: {r['error']}")
            continue

        cmp = r["comparison"]
        lines.append(
            f"     Operaciones : {cmp['ops_ok']}/{cmp['total_ops']} OK"
        )

        if cmp["ops_missing"]:
            lines.append(
                f"     Ops ausentes en DPMcore ({len(cmp['ops_missing'])}):"
            )
            for c in cmp["ops_missing"]:
                lines.append(f"       - {c}")

        if cmp["ops_diff_expr"]:
            lines.append(
                f"     Ops con expresión diferente ({len(cmp['ops_diff_expr'])}):"
            )
            for d in cmp["ops_diff_expr"]:
                lines.append(f"       - {d['code']}")
                lines.append(f"           MDPM   : {d['mdpm'][:120]}")
                lines.append(
                    f"           DPMcore: {(d['dpmcore'] or 'None')[:120]}"
                )

        if cmp["ops_diff_sev"]:
            lines.append(
                f"     Ops con severidad diferente ({len(cmp['ops_diff_sev'])}):"
            )
            for d in cmp["ops_diff_sev"]:
                lines.append(
                    f"       - {d['code']}: MDPM={d['mdpm']}  DPMcore={d['dpmcore']}"
                )

        if cmp["tables_missing"]:
            lines.append(
                f"     Tablas ausentes en DPMcore ({len(cmp['tables_missing'])}):"
            )
            lines.append(f"       {cmp['tables_missing'][:10]}")

        if cmp["vars_diff"]:
            lines.append(
                f"     Variables con tipo diferente ({len(cmp['vars_diff'])}):"
            )
            for var_id, diff in list(cmp["vars_diff"].items())[:5]:
                lines.append(
                    f"       - {var_id}: MDPM={diff['mdpm']}  DPMcore={diff['dpmcore']}"
                )

        if cmp["intra_missing"]:
            lines.append(
                f"     Ops ausentes en intra_instance_validations ({len(cmp['intra_missing'])}):"
            )
            lines.append(f"       {cmp['intra_missing'][:10]}")

    lines.append("\n" + "=" * 70)

    txt = "\n".join(lines)
    print(txt)
    txt_path.write_text(txt, encoding="utf-8")
    print(f"\n  Informe texto : {txt_path}")

    json_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  Informe JSON  : {json_path}")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────


def main():
    try:
        import dpmcore
    except ImportError:
        sys.exit("ERROR: no se puede importar dpmcore.")

    db = dpmcore.connect(DB_URL)

    json_files = sorted(REFERENCES_DIR.glob("*.json"))
    if not json_files:
        sys.exit(f"No se encontraron ficheros JSON en {REFERENCES_DIR}")

    print(f"Módulos encontrados : {len(json_files)}")
    print(f"Base de datos       : {DB_URL}\n")

    results = []

    for i, path in enumerate(json_files, 1):
        print(
            f"[{i:>3}/{len(json_files)}] {path.name} ... ", end="", flush=True
        )

        try:
            mdpm = extract_mdpm(path)
        except Exception as e:
            print(f"ERROR al leer JSON: {e}")
            results.append(
                {
                    "file": path.name,
                    "module_code": path.stem,
                    "module_version": "",
                    "passed": False,
                    "error": f"Error al leer JSON: {e}",
                }
            )
            continue

        try:
            dpm_mod, uri = call_dpmcore(db, mdpm)
        except Exception as e:
            print(f"ERROR DPMcore: {e}")
            results.append(
                {
                    "file": path.name,
                    "module_code": mdpm["module_code"],
                    "module_version": mdpm["module_version"],
                    "passed": False,
                    "error": str(e),
                    "comparison": None,
                }
            )
            continue

        cmp = compare_module(mdpm, dpm_mod)
        tag = "✅" if cmp["passed"] else "❌"
        print(f"{tag}  {cmp['ops_ok']}/{cmp['total_ops']} ops OK")

        results.append(
            {
                "file": path.name,
                "module_code": mdpm["module_code"],
                "module_version": mdpm["module_version"],
                "uri": uri,
                "passed": cmp["passed"],
                "error": None,
                "comparison": cmp,
            }
        )

    print()
    write_report(results, REPORT_TXT, REPORT_JSON)

    sys.exit(0 if all(r.get("passed") for r in results) else 1)


if __name__ == "__main__":
    main()
