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

import click

from dpmcore import __version__


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
def migrate(source: str, database: str) -> None:
    """Migrate an Access database into a SQL database."""
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
        result = service.migrate_from_access(source)
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
def update_db(
    target: str,
    access_file: str | None,
    ecb_validations_file: str | None,
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

    console = Console()

    if access_file is not None:
        console.print(
            f"Updating [cyan]{target}[/cyan] from Access file "
            f"[cyan]{access_file}[/cyan]..."
        )
    else:
        console.print(
            f"Updating [cyan]{target}[/cyan] from data/DPM CSVs..."
        )

    try:
        result = DatabaseUpdateService().update(
            target=target,
            access_file=access_file,
            ecb_validations_file=ecb_validations_file,
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

    for warning in migration.warnings:
        console.print(f"[yellow]Warning:[/yellow] {warning}")

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
    preconditions = [(pair[0], list(pair[1])) for pair in preconditions_raw]

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
