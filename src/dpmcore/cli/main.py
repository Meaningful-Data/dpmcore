"""CLI entry point for dpmcore.

Usage::

    dpmcore migrate --source /path/to/file.accdb --database sqlite:///dpm.db
    dpmcore serve --database sqlite:///dpm.db
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
            "Install 'rich' for pretty output: "
            "pip install dpmcore[cli]",
            err=True,
        )
        sys.exit(1)

    from sqlalchemy import create_engine

    from dpmcore.services.migration import (
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
        import uvicorn  # type: ignore[import-untyped]
    except ImportError:
        click.echo(
            "Server dependencies not installed. Run:\n"
            "  pip install dpmcore[server]",
            err=True,
        )
        sys.exit(1)

    # Import here so the server module is only loaded when needed.
    from dpmcore.server.app import create_app  # type: ignore[import-not-found]

    app = create_app(database)
    uvicorn.run(app, host=host, port=port)


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
                module_code, release_code, output_path, config,
            )
        else:
            codes = [c.strip() for c in table_codes.split(",")]  # type: ignore[union-attr]
            path = svc.export_tables(
                codes, release_code, output_path, config,
            )

    click.echo(f"Exported to {path}")
