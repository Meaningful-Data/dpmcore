r"""CLI entry point for dpmcore.

Usage::

    dpmcore migrate --source /path/to/file.accdb --database sqlite:///dpm.db
    dpmcore serve --database sqlite:///dpm.db
    dpmcore generate-script --expressions ./rules.json \
        --module-code COREP_Con --module-version 2.0.1 \
        --database sqlite:///dpm.db --output ./script.json
    dpmcore --version
"""

from __future__ import annotations

import sys
from typing import Any, cast

import click

from dpmcore import __version__


def _print_capped_warnings(
    console: Any, label: str, warnings: list[str], limit: int = 20
) -> None:
    """Print at most *limit* warnings.

    Caps output so a large list can't flood the terminal (e.g. many
    rows repeating the same underlying error).
    """
    for warning in warnings[:limit]:
        console.print(f"[yellow]{label}:[/yellow] {warning}")
    omitted = len(warnings) - limit
    if omitted > 0:
        console.print(
            f"[yellow]... and {omitted} more {label.lower()}(s) "
            "omitted.[/yellow]"
        )


@click.group()
@click.version_option(version=__version__, prog_name="dpmcore")
def main() -> None:
    """Dpmcore — Data Point Model toolkit."""


@main.command()
@click.option(
    "--source",
    required=True,
    type=click.Path(exists=True),
    help="Path to Access .accdb / .mdb file.",
)
@click.option(
    "--database",
    required=True,
    help="SQLAlchemy database URL (e.g. sqlite:///dpm.db).",
)
@click.option(
    "--output",
    "output_path",
    default=None,
    type=click.Path(dir_okay=False, path_type=str),
    help=(
        "Final path for the resulting SQLite file. When omitted, "
        "defaults to '<stem>_<release>_<YYYYMMDD>.db' next to the "
        "input --database path. Ignored for non-SQLite engines."
    ),
)
def migrate(source: str, database: str, output_path: str | None) -> None:
    """Migrate an Access database into a SQL database."""
    from pathlib import Path

    try:
        from rich.console import Console
        from rich.table import Table
    except ImportError:
        click.echo(
            "Install 'rich' for pretty output: pip install dpmcore[cli]",
            err=True,
        )
        sys.exit(1)

    from sqlalchemy import create_engine

    from dpmcore.loaders.migration import (
        MigrationError,
        MigrationService,
    )

    console = Console()

    engine = create_engine(database)
    service = MigrationService(engine)

    try:
        result = service.migrate_from_access(
            source,
            output_path=Path(output_path) if output_path else None,
        )
    except MigrationError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)

    # Display results.
    table = Table(title="Migration Results")
    table.add_column("Table", style="cyan")
    table.add_column("Rows", justify="right", style="green")

    for name, rows in result.table_details.items():
        table.add_row(name, str(rows))

    console.print(table)
    console.print(
        f"\n[bold]Total:[/bold] {result.tables_migrated} tables, "
        f"{result.total_rows} rows "
        f"(backend: {result.backend_used})"
    )
    if result.database_path is not None:
        console.print(
            f"[bold]Database:[/bold] [green]{result.database_path}[/green]"
        )

    for warning in result.warnings:
        console.print(f"[yellow]Warning:[/yellow] {warning}")


@main.command("export-csv")
@click.argument(
    "source",
    type=click.Path(exists=True, dir_okay=False, path_type=str),
)
@click.option(
    "--output-dir",
    default="data/DPM",
    show_default=True,
    type=click.Path(file_okay=False, dir_okay=True, path_type=str),
    help="Directory to write CSV files.",
)
def export_csv(source: str, output_dir: str) -> None:
    """Export all tables from an Access database to CSV files."""
    from pathlib import Path

    try:
        from rich.console import Console
    except ImportError:
        click.echo(
            "Install 'rich' for pretty output: pip install dpmcore[cli]",
            err=True,
        )
        sys.exit(1)
    from dpmcore.services.export_csv import ExportCsvError, ExportCsvService

    console = Console()
    service = ExportCsvService()

    try:
        result = service.export_safely(source, Path(output_dir))
    except ExportCsvError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)

    for name in result.table_names:
        console.print(f"  exported [cyan]{name}[/cyan]")

    console.print(
        f"\n[bold]{result.tables_exported} tables[/bold] exported to "
        f"[green]{result.output_dir}[/green]"
    )
    console.print("Review results with manual inspection and/or git diff.")


@main.command("build-meili-json")
@click.option(
    "--source-dir",
    type=click.Path(exists=True, file_okay=False, path_type=str),
    default=None,
    help="Directory containing exported CSV tables. Defaults to data/DPM.",
)
@click.option(
    "--access-file",
    type=click.Path(exists=True, dir_okay=False, path_type=str),
    default=None,
    help=(
        "Access .accdb / .mdb file. Exported to a temporary"
        " CSV directory before building."
    ),
)
@click.option(
    "--ecb-validations-file",
    type=click.Path(exists=True, dir_okay=False, path_type=str),
    default=None,
    help=(
        "Optional ECB validations CSV file to import"
        " before generating the JSON."
    ),
)
@click.option(
    "--output",
    default="operations.json",
    show_default=True,
    type=click.Path(dir_okay=False, path_type=str),
    help="Output JSON file.",
)
def build_meili_json(
    source_dir: str | None,
    access_file: str | None,
    ecb_validations_file: str | None,
    output: str,
) -> None:
    """Build the Meilisearch operations JSON from CSV tables or Access."""
    try:
        from rich.console import Console
    except ImportError:
        click.echo(
            "Install 'rich' for pretty output: pip install dpmcore[cli]",
            err=True,
        )
        sys.exit(1)

    from dpmcore.services.meili_build import MeiliBuildError, MeiliBuildService

    console = Console()

    try:
        result = MeiliBuildService().build(
            output_file=output,
            source_dir=source_dir,
            access_file=access_file,
            ecb_validations_file=ecb_validations_file,
        )
    except MeiliBuildError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)

    console.print(
        f"[green]Generated[/green] {result.operations_written} operations "
        f"into [cyan]{result.output_file}[/cyan]"
    )

    if result.used_access_file:
        console.print("[green]Main DPM source loaded from Access file[/green]")
    else:
        console.print(
            "[green]Main DPM source loaded from CSV directory[/green]"
        )

    if result.ecb_validations_imported:
        console.print("[green]ECB validations imported[/green]")


@main.command("update-db")
@click.option(
    "--target",
    required=True,
    help="Target DB.",
)
@click.option(
    "--access-file",
    type=click.Path(exists=True, dir_okay=False, path_type=str),
    default=None,
    help="Optional Access file. If omitted, data/DPM CSVs are used.",
)
@click.option(
    "--ecb-validations-file",
    type=click.Path(exists=True, dir_okay=False, path_type=str),
    default=None,
    help="Optional ECB validations CSV file.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Load and validate data without replacing the active database.",
)
@click.option(
    "--keep-staging",
    is_flag=True,
    default=False,
    help="Keep temporary SQLite file or staging/backup schemas for debugging.",
)
def update_db(
    target: str,
    access_file: str | None,
    ecb_validations_file: str | None,
    dry_run: bool,
    keep_staging: bool,
) -> None:
    """Safely update a DPM database."""
    try:
        from rich.console import Console
    except ImportError:
        click.echo(
            "Install 'rich' for pretty output: pip install dpmcore[cli]",
            err=True,
        )
        sys.exit(1)

    from dpmcore.services.database_update import (
        DatabaseUpdateError,
        DatabaseUpdateService,
    )

    console = Console(soft_wrap=True)

    if access_file is not None:
        console.print(
            f"Updating [cyan]{target}[/cyan] from Access file "
            f"[cyan]{access_file}[/cyan]..."
        )
    else:
        console.print(f"Updating [cyan]{target}[/cyan] from data/DPM CSVs...")

    try:
        result = DatabaseUpdateService().update(
            target=target,
            access_file=access_file,
            ecb_validations_file=ecb_validations_file,
            dry_run=dry_run,
            keep_staging=keep_staging,
        )
    except DatabaseUpdateError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)

    migration = result.migration_result

    console.print(
        f"[green]Updated[/green] {result.target_type} target "
        f"[cyan]{result.target}[/cyan]"
    )
    console.print(
        f"[bold]{migration.tables_migrated} tables[/bold], "
        f"{migration.total_rows} rows loaded"
    )

    if result.used_access_file:
        console.print("[green]Source loaded from Access file[/green]")
    else:
        console.print("[green]Source loaded from data/DPM CSVs[/green]")

    if result.ecb_validations_imported:
        console.print("[green]ECB validations imported[/green]")

    _print_capped_warnings(console, "Warning", migration.warnings)

    if result.dry_run:
        console.print(
            "[yellow]Dry run completed. "
            "Active database was not modified.[/yellow]"
        )

    if result.staging_location:
        console.print(
            f"[yellow]Staging artifact:[/yellow] "
            f"[cyan]{result.staging_location}[/cyan]"
        )


@main.command()
@click.option(
    "--database",
    required=True,
    help="SQLAlchemy database URL.",
)
@click.option("--host", default="127.0.0.1", help="Bind host.")
@click.option("--port", default=8000, type=int, help="Bind port.")
def serve(database: str, host: str, port: int) -> None:
    """Start the dpmcore REST API server."""
    try:
        import uvicorn
    except ImportError:
        click.echo(
            "Server dependencies not installed. Run:\n"
            "  pip install dpmcore[server]",
            err=True,
        )
        sys.exit(1)

    # Import here so the server module is only loaded when needed.
    from dpmcore.server.app import create_app

    app = create_app(database)
    uvicorn.run(app, host=host, port=port)


def _process_preconditions_from_json(
    preconditions_raw: list[Any],
) -> list[tuple[str, list[str]] | dict[str, Any]] | None:
    """Convert raw precondition entries to script() format."""
    if not preconditions_raw:
        return None

    preconditions: list[tuple[str, list[str]] | dict[str, Any]] = []
    for entry in preconditions_raw:
        has_custom = "code" in entry or "version_id" in entry
        if isinstance(entry, dict) and has_custom:
            preconditions.append(entry)
        elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
            preconditions.append((entry[0], list(entry[1])))
        elif isinstance(entry, dict) and "expression" in entry:
            preconditions.append(
                (
                    entry["expression"],
                    list(entry.get("affected_operations", [])),
                )
            )
    return preconditions or None


@main.command("generate-script")
@click.option(
    "--expressions",
    "expressions_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help=(
        "Path to a JSON file with shape "
        '{"expressions": [[expr, code], ...], '
        '"preconditions": [[pre_expr, [code, ...]], ...], '
        '"severities": {code: severity}}. '
        "The 'preconditions' and 'severities' keys are optional."
    ),
)
@click.option(
    "--module-code",
    required=True,
    help="Primary module code (e.g. COREP_Con).",
)
@click.option(
    "--module-version",
    required=True,
    help="Primary module version (e.g. 2.0.1).",
)
@click.option(
    "--severity",
    default=None,
    help=(
        "Global default severity (error/warning/info). Defaults to "
        "'warning' when omitted. Per-validation overrides go in the "
        "'severities' map of the input JSON."
    ),
)
@click.option(
    "--release",
    default=None,
    help=(
        "Release code (e.g. '4.2'). When omitted, resolves to the "
        "latest release whose window contains the requested module "
        "version."
    ),
)
@click.option(
    "--database",
    required=True,
    help="SQLAlchemy database URL.",
)
@click.option(
    "--output",
    required=True,
    type=click.Path(dir_okay=False),
    help="Path to write the generated script JSON.",
)
def generate_script(
    expressions_path: str,
    module_code: str,
    module_version: str,
    severity: str | None,
    release: str | None,
    database: str,
    output: str,
) -> None:
    """Generate an engine-ready DPM-XL validations script."""
    import json
    from pathlib import Path

    try:
        from rich.console import Console
    except ImportError:
        click.echo(
            "Install 'rich' for pretty output: pip install dpmcore[cli]",
            err=True,
        )
        sys.exit(1)

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from dpmcore.services.ast_generator import ASTGeneratorService

    console = Console()

    try:
        raw_text = Path(expressions_path).read_text(encoding="utf-8")
    except OSError as exc:
        click.echo(f"Could not read {expressions_path}: {exc}", err=True)
        sys.exit(1)
    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        click.echo(
            f"Invalid JSON in {expressions_path}: {exc}",
            err=True,
        )
        sys.exit(1)
    if not isinstance(raw, dict) or "expressions" not in raw:
        click.echo(
            "Invalid expressions file: expected a JSON object with an "
            "'expressions' key (and optional 'preconditions', "
            "'severities'). The flat-list form is no longer supported.",
            err=True,
        )
        sys.exit(1)

    items = [tuple(pair) for pair in raw["expressions"]]
    preconditions_raw = raw.get("preconditions") or []
    preconditions = _process_preconditions_from_json(preconditions_raw)

    severities_raw = raw.get("severities")
    severities: dict[str, str] | None = None
    if severities_raw is not None:
        if not isinstance(severities_raw, dict):
            click.echo(
                "Invalid 'severities' field: expected an object keyed "
                "by validation_code.",
                err=True,
            )
            sys.exit(1)
        severities = {str(k): str(v) for k, v in severities_raw.items()}

    engine = create_engine(database)
    with Session(engine) as session:
        svc = ASTGeneratorService(session)
        result = svc.script(
            expressions=items,
            module_code=module_code,
            module_version=module_version,
            preconditions=preconditions or None,
            severity=severity,
            severities=severities,
            release=release,
        )

    if not result.get("success"):
        console.print(
            f"[red]Script generation failed:[/red] {result.get('error')}"
        )
        sys.exit(1)

    Path(output).write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8"
    )

    enriched = result.get("enriched_ast") or {}
    n_dep = sum(
        len((ns_block or {}).get("dependency_modules") or {})
        for ns_block in enriched.values()
        if isinstance(ns_block, dict)
    )
    console.print(
        f"[green]Wrote script to[/green] {output} "
        f"({len(items)} expressions, {n_dep} dependency modules)"
    )


@main.command("export-script")
@click.option(
    "--module-code",
    default=None,
    help="Primary module code (e.g. COREP_Con). Required unless "
    "--all-modules is given.",
)
@click.option(
    "--module-version",
    default=None,
    help="Primary module version (e.g. 2.0.1). Mutually exclusive with "
    "--all-versions and --release; one of the three is required.",
)
@click.option(
    "--all-modules",
    is_flag=True,
    default=False,
    help="Sweep every module in the database, instead of --module-code.",
)
@click.option(
    "--all-versions",
    is_flag=True,
    default=False,
    help="Sweep every active version of the selected module(s), "
    "instead of --module-version. Mutually exclusive with "
    "--module-version and --release.",
)
@click.option(
    "--release",
    default=None,
    help=(
        "Release code (e.g. '4.2'). Mutually exclusive with "
        "--module-version and --all-versions: on its own, resolves each "
        "selected module to its single version active at this release. "
        "One of --module-version, --all-versions, or --release is "
        "required."
    ),
)
@click.option(
    "--database",
    required=True,
    help="SQLAlchemy database URL.",
)
@click.option(
    "--output",
    default=None,
    type=click.Path(),
    help="Where to write the generated script(s). For a single "
    "module/version target, a JSON file path (defaults to "
    "'<module_code>-<module_version>.json' in the current directory). "
    "When sweeping (--all-modules/--all-versions), a directory to write "
    "one '<module_code>-<version>.json' file per target into (defaults "
    "to the current directory).",
)
def export_script(
    module_code: str | None,
    module_version: str | None,
    all_modules: bool,
    all_versions: bool,
    release: str | None,
    database: str,
    output: str | None,
) -> None:
    """Generate engine-ready DPM-XL validations scripts from the database.

    Unlike ``generate-script``, no ``--expressions`` file is needed: the
    active validations, preconditions and severities for each module
    version are discovered directly from the database. Pass
    ``--module-code``/``--module-version`` for a single target, or
    ``--all-modules``/``--all-versions`` to sweep many at once.
    ``--release`` on its own (no ``--module-version``/``--all-versions``)
    selects each targeted module's version active at that release instead.
    """
    import json
    from pathlib import Path

    try:
        from rich.console import Console
    except ImportError:
        click.echo(
            "Install 'rich' for pretty output: pip install dpmcore[cli]",
            err=True,
        )
        sys.exit(1)

    from sqlalchemy import create_engine
    from sqlalchemy.exc import ArgumentError
    from sqlalchemy.orm import Session

    from dpmcore.services.ast_generator import ASTGeneratorService

    console = Console()

    _validate_export_script_args(
        console,
        module_code=module_code,
        module_version=module_version,
        all_modules=all_modules,
        all_versions=all_versions,
        release=release,
        output=output,
    )
    sweeping = module_version is None

    try:
        engine = create_engine(database)
    except ArgumentError:
        console.print(
            f"[red]--database is not a valid SQLAlchemy URL:[/red] "
            f"{database!r}\n"
            "Pass a URL such as "
            "[bold]sqlite:////absolute/path/to.sqlite[/bold] or "
            "[bold]sqlite:///relative/path.sqlite[/bold], not a bare "
            "filesystem path."
        )
        sys.exit(1)
    with Session(engine) as session:
        svc = ASTGeneratorService(session)

        if sweeping:
            try:
                targets = svc.list_module_versions(
                    module_code=None if all_modules else module_code,
                    release=release,
                )
            except ValueError as exc:
                console.print(f"[red]{exc}[/red]")
                sys.exit(1)
            if not targets:
                console.print("[red]No active module versions matched.[/red]")
                sys.exit(1)

            out_dir = Path(output) if output else Path(".")
            out_dir.mkdir(parents=True, exist_ok=True)

            succeeded: list[tuple[str, str]] = []
            failed: list[tuple[str, str]] = []
            for code, version in targets:
                result = svc.script_for_module(
                    module_code=code, module_version=version, release=release
                )
                if not result.get("success"):
                    console.print(
                        f"[yellow]Skipped {code} {version}:[/yellow] "
                        f"{result.get('error')}"
                    )
                    failed.append((code, version))
                    continue

                out_path = out_dir / f"{code}-{version}.json"
                out_path.write_text(
                    json.dumps(result, indent=2, default=str),
                    encoding="utf-8",
                )
                n_ops, n_dep = _script_result_counts(result)
                console.print(
                    f"[green]Wrote[/green] {out_path} "
                    f"({n_ops} validations discovered, "
                    f"{n_dep} dependency modules)"
                )
                succeeded.append((code, version))

            console.print(
                f"\n[bold]{len(succeeded)} succeeded, {len(failed)} "
                f"failed[/bold] out of {len(targets)} module versions"
            )
            if failed:
                sys.exit(1)
            return

        # _validate_export_script_args guarantees both are set here (the
        # sweeping branch, which allows either to be None, returned above).
        result = svc.script_for_module(
            module_code=cast(str, module_code),
            module_version=cast(str, module_version),
            release=release,
        )

    if not result.get("success"):
        console.print(
            f"[red]Script generation failed:[/red] {result.get('error')}"
        )
        sys.exit(1)

    out_path = (
        Path(output)
        if output
        else Path(f"{module_code}-{module_version}.json")
    )
    out_path.write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8"
    )

    n_ops, n_dep = _script_result_counts(result)
    console.print(
        f"[green]Wrote script to[/green] {out_path} "
        f"({n_ops} validations discovered, {n_dep} dependency modules)"
    )


def _validate_version_selector_args(
    console: Any,
    *,
    module_version: str | None,
    all_versions: bool,
    release: str | None,
) -> None:
    """Validate the version-selector option combination, exiting on error.

    ``--module-version``, ``--all-versions`` and a bare ``--release`` (no
    version selector) are pairwise mutually exclusive, and exactly one of
    the three is required.
    """
    if module_version and all_versions:
        console.print(
            "[red]--module-version and --all-versions are mutually "
            "exclusive.[/red]"
        )
        sys.exit(1)
    if release is not None and (module_version or all_versions):
        console.print(
            "[red]--release is mutually exclusive with "
            "--module-version and --all-versions.[/red]"
        )
        sys.exit(1)
    if not module_version and not all_versions and release is None:
        console.print(
            "[red]Specify one of --module-version, --all-versions, or "
            "--release.[/red]"
        )
        sys.exit(1)


def _validate_export_script_args(
    console: Any,
    *,
    module_code: str | None,
    module_version: str | None,
    all_modules: bool,
    all_versions: bool,
    release: str | None,
    output: str | None,
) -> None:
    """Validate ``export-script``'s option combination, exiting on error."""
    from pathlib import Path

    if bool(module_code) == bool(all_modules):
        console.print(
            "[red]Specify exactly one of --module-code or --all-modules.[/red]"
        )
        sys.exit(1)
    _validate_version_selector_args(
        console,
        module_version=module_version,
        all_versions=all_versions,
        release=release,
    )
    if module_version and all_modules:
        console.print(
            "[red]--module-version requires --module-code, not "
            "--all-modules.[/red]"
        )
        sys.exit(1)

    sweeping = module_version is None
    if sweeping and output and Path(output).is_file():
        console.print(
            "[red]--output must be a directory when sweeping "
            "(--all-modules/--all-versions/--release).[/red]"
        )
        sys.exit(1)


def _script_result_counts(result: dict[str, Any]) -> tuple[int, int]:
    """Count validations/dependency modules across a script() result."""
    enriched = result.get("enriched_ast") or {}
    n_ops = sum(
        len((ns_block or {}).get("operations") or {})
        for ns_block in enriched.values()
        if isinstance(ns_block, dict)
    )
    n_dep = sum(
        len((ns_block or {}).get("dependency_modules") or {})
        for ns_block in enriched.values()
        if isinstance(ns_block, dict)
    )
    return n_ops, n_dep


@main.command()
@click.option(
    "--database",
    required=True,
    help="SQLAlchemy database URL (e.g. sqlite:///dpm.db).",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Emit the result as JSON instead of a rich table.",
)
def validate(database: str, as_json: bool) -> None:
    """Validate that a database has the expected DPM schema and seed data."""
    import json as _json

    from dpmcore.connection import connect

    with connect(database) as db:
        result = db.validate_schema()

    if as_json:
        click.echo(
            _json.dumps(
                {
                    "is_valid": result.is_valid,
                    "backend": result.backend,
                    "missing_tables": result.missing_tables,
                    "missing_columns": result.missing_columns,
                    "empty_required_tables": result.empty_required_tables,
                    "elapsed_ms": round(result.elapsed_ms, 2),
                },
                indent=2,
            )
        )
        sys.exit(0 if result.is_valid else 1)

    try:
        from rich.console import Console
        from rich.table import Table
    except ImportError:
        click.echo(
            "Install 'rich' for pretty output: pip install dpmcore[cli]",
            err=True,
        )
        sys.exit(1)

    console = Console()
    status = (
        "[green]valid[/green]" if result.is_valid else "[red]invalid[/red]"
    )
    console.print(
        f"Schema: {status}  "
        f"(backend: {result.backend}, "
        f"{result.elapsed_ms:.1f} ms)"
    )

    if result.missing_tables:
        table = Table(title="Missing tables")
        table.add_column("Table", style="red")
        for name in result.missing_tables:
            table.add_row(name)
        console.print(table)

    if result.missing_columns:
        table = Table(title="Missing columns")
        table.add_column("Table", style="cyan")
        table.add_column("Columns", style="red")
        for tname, cols in result.missing_columns.items():
            table.add_row(tname, ", ".join(cols))
        console.print(table)

    if result.empty_required_tables:
        table = Table(title="Empty required tables")
        table.add_column("Table", style="yellow")
        for name in result.empty_required_tables:
            table.add_row(name)
        console.print(table)

    sys.exit(0 if result.is_valid else 1)


@main.command("export-layout")
@click.option(
    "--database",
    required=True,
    help="SQLAlchemy database URL (e.g. sqlite:///dpm.db).",
)
@click.option(
    "--module",
    "module_code",
    default=None,
    help="Module version code to export (e.g. FINREP9).",
)
@click.option(
    "--tables",
    "table_codes",
    default=None,
    help="Comma-separated table codes (e.g. F_01.01,F_01.02).",
)
@click.option(
    "--release",
    "release_code",
    default=None,
    help="Release code filter (e.g. 4.2).",
)
@click.option(
    "--output",
    "output_path",
    default=None,
    type=click.Path(),
    help="Output file path (.xlsx).",
)
@click.option("--no-annotate", is_flag=True, help="Disable annotations.")
@click.option("--no-comments", is_flag=True, help="Disable cell comments.")
def export_layout(
    database: str,
    module_code: str | None,
    table_codes: str | None,
    release_code: str | None,
    output_path: str | None,
    no_annotate: bool,
    no_comments: bool,
) -> None:
    """Export annotated table layouts to Excel."""
    if not module_code and not table_codes:
        raise click.UsageError("Provide --module or --tables.")

    from dpmcore.connection import connect
    from dpmcore.services.layout_exporter.models import ExportConfig

    config = ExportConfig(
        annotate=not no_annotate,
        add_cell_comments=not no_comments,
        add_header_comments=not no_comments,
    )

    with connect(database) as db:
        svc = db.services.layout_exporter
        if module_code:
            path = svc.export_module(
                module_code,
                release_code,
                output_path,
                config,
            )
        elif table_codes:
            codes = [c.strip() for c in table_codes.split(",")]
            path = svc.export_tables(
                codes,
                release_code,
                output_path,
                config,
            )

    click.echo(f"Exported to {path}")
