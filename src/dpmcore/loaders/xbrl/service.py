"""Facade service for importing XBRL taxonomies into DPM databases.

Ties together source handling (directories or zip archives),
architecture detection, the two taxonomy readers and the ORM mapper:

- **fresh mode** (default): the target database schema is dropped,
  recreated and seeded, and — for SQLite files — the result is
  renamed following the ``<stem>_<release>_<YYYYMMDD>.db``
  convention shared with :class:`~dpmcore.loaders.migration.
  MigrationService`.
- **existing mode** (``into_existing=True``): content is added to a
  populated DPM database under a new release; the whole import is
  one transaction and pre-validated with
  :class:`~dpmcore.services.schema_validation.SchemaValidationService`.
"""

from __future__ import annotations

import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from dpmcore.loaders import _sqlite_output
from dpmcore.loaders.xbrl.mapper import MappingOutcome, TaxonomyMapper
from dpmcore.loaders.xbrl.model import (
    ARCHITECTURE_AUTO,
    ARCHITECTURE_DPM1,
    ARCHITECTURE_EUROFILING_2006,
    TaxonomyModel,
    XbrlImportError,
    XModule,
    merge_models,
)


@dataclass(frozen=True)
class XbrlImportResult:
    """Outcome of a successful taxonomy import run.

    Attributes:
        architecture: Resolved taxonomy architecture.
        release_id: The release the content was imported under.
        created: Rows created, keyed by entity name.
        reused: Pre-existing rows reused, keyed by entity name.
        warnings: Non-fatal findings collected during the import.
        database_path: Final SQLite file path in fresh mode, if the
            engine points at a SQLite file.
    """

    architecture: str
    release_id: int
    created: Dict[str, int] = field(default_factory=dict)
    reused: Dict[str, int] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    database_path: Optional[Path] = None


class XbrlTaxonomyImportService:
    """Import an XBRL taxonomy into a DPM 2.0 Refit database.

    Like :class:`~dpmcore.loaders.migration.MigrationService`, this
    service requires an ``Engine`` because fresh imports run
    ``Base.metadata.create_all`` and relocate SQLite files.

    Args:
        engine: Target database engine.
    """

    def __init__(self, engine: Engine) -> None:
        """Initialise with a SQLAlchemy engine."""
        self._engine = engine

    def import_taxonomy(
        self,
        source: str | Path,
        *,
        framework_code: str,
        release_code: str,
        framework_name: Optional[str] = None,
        release_date: Optional[date] = None,
        entry_points: Optional[Sequence[str]] = None,
        architecture: str = ARCHITECTURE_AUTO,
        owner_name: str = "National Bank of Belgium",
        owner_acronym: str = "NBB",
        into_existing: bool = False,
        offline: bool = False,
        cache_dir: Optional[Path] = None,
        output_path: Optional[Path] = None,
        max_enumerated_columns: int = 512,
        single_module: bool = False,
        generate_variables: bool = True,
    ) -> XbrlImportResult:
        """Import the taxonomy at *source* into the database.

        Args:
            source: Taxonomy directory or ``.zip`` archive.
            framework_code: Code of the framework to create.
            release_code: Code of the release to import under.
            framework_name: Framework display name; defaults to the
                code.
            release_date: Release date.
            entry_points: Entry-point schema files (relative to the
                taxonomy root) for the 2006 architecture;
                auto-discovered when omitted.
            architecture: ``auto``, ``eurofiling2006`` or ``dpm1``.
            owner_name: Owning organisation name.
            owner_acronym: Owning organisation acronym.
            into_existing: Add to a populated database instead of
                rebuilding the schema.
            offline: Forbid Arelle web access.
            cache_dir: Pre-seeded Arelle web-cache directory.
            output_path: Final SQLite path in fresh mode; defaults
                to the conventional name.
            max_enumerated_columns: Column-enumeration bound for the
                2006 architecture.
            single_module: 2006 architecture only. When ``True``, the
                per-table modules synthesised from the discovered
                ``t-*.xsd`` entry points are collapsed into a single
                module (code/name taken from the framework) comprising
                all tables in discovery order. Ignored for dpm1, which
                reads its modules from ``mod/*.xsd`` schemas.
            generate_variables: When ``True`` (the default), cells are
                mapped without inline variables and the official
                variable-generation service computes and persists the
                variables, versions, contexts, compound keys and
                filing indicators. When ``False``, the mapper's inline
                per-cell variable creation is used instead.

        Returns:
            An :class:`XbrlImportResult`.

        Raises:
            XbrlImportError: If the source is invalid, the target
                database is not a DPM database (existing mode), or
                the taxonomy cannot be read.
        """
        source_path = Path(source)
        if not source_path.exists():
            raise XbrlImportError(
                f"Taxonomy source '{source_path}' does not exist."
            )
        with tempfile.TemporaryDirectory(
            prefix="dpmcore-xbrl-"
        ) as workdir:
            root = _materialise_source(source_path, Path(workdir))
            resolved, arch_root = _resolve_architecture(
                root, architecture
            )
            model = self._read_model(
                resolved,
                arch_root,
                entry_points=entry_points,
                framework_code=framework_code,
                framework_name=framework_name or framework_code,
                offline=offline,
                cache_dir=cache_dir,
                max_enumerated_columns=max_enumerated_columns,
                single_module=single_module,
            )

        self._prepare_database(into_existing)
        outcome = self._map(
            model,
            owner_name=owner_name,
            owner_acronym=owner_acronym,
            release_code=release_code,
            release_date=release_date,
            fresh=not into_existing,
            generate_variables=generate_variables,
        )

        database_path = None
        if not into_existing:
            database_path = _sqlite_output.relocate_database(
                self._engine, output_path
            )
        return XbrlImportResult(
            architecture=resolved,
            release_id=outcome.release_id,
            created=outcome.created,
            reused=outcome.reused,
            warnings=outcome.warnings,
            database_path=database_path,
        )

    # -------------------------------------------------------------- #
    # Internals
    # -------------------------------------------------------------- #

    def _read_model(
        self,
        architecture: str,
        arch_root: Path,
        *,
        entry_points: Optional[Sequence[str]],
        framework_code: str,
        framework_name: str,
        offline: bool,
        cache_dir: Optional[Path],
        max_enumerated_columns: int,
        single_module: bool,
    ) -> TaxonomyModel:
        if architecture == ARCHITECTURE_DPM1:
            from dpmcore.loaders.xbrl.reader_dpm1 import read_taxonomy

            return read_taxonomy(
                arch_root,
                framework_code=framework_code,
                framework_name=framework_name,
            )
        return self._read_eurofiling2006(
            arch_root,
            entry_points=entry_points,
            framework_code=framework_code,
            framework_name=framework_name,
            offline=offline,
            cache_dir=cache_dir,
            max_enumerated_columns=max_enumerated_columns,
            single_module=single_module,
        )

    def _read_eurofiling2006(
        self,
        arch_root: Path,
        *,
        entry_points: Optional[Sequence[str]],
        framework_code: str,
        framework_name: str,
        offline: bool,
        cache_dir: Optional[Path],
        max_enumerated_columns: int,
        single_module: bool,
    ) -> TaxonomyModel:
        from dpmcore.loaders.xbrl.arelle_engine import ArelleEngine
        from dpmcore.loaders.xbrl.reader_eurofiling2006 import (
            read_entry_point,
        )

        entries = _resolve_entry_points(arch_root, entry_points)
        engine = ArelleEngine(offline=offline, cache_dir=cache_dir)
        models = []
        try:
            for entry in entries:
                model_xbrl = engine.load(entry)
                models.append(
                    read_entry_point(
                        model_xbrl,
                        framework_code=framework_code,
                        framework_name=framework_name,
                        entry_path=entry,
                        max_enumerated_columns=max_enumerated_columns,
                    )
                )
        finally:
            engine.close()
        merged = merge_models(models)
        duplicates = _duplicate_table_codes(models)
        if duplicates:
            merged = TaxonomyModel(
                **{
                    **merged.__dict__,
                    "warnings": (
                        *merged.warnings,
                        "Multiple entry points define tables "
                        f"{sorted(duplicates)}; only the first "
                        "occurrence of each was imported. Import "
                        "revised versions in a separate run under "
                        "their own release.",
                    ),
                }
            )
        if single_module:
            merged = _collapse_to_single_module(
                merged, framework_code, framework_name
            )
        return merged

    def _prepare_database(self, into_existing: bool) -> None:
        from dpmcore.orm.base import Base

        if not into_existing:
            Base.metadata.drop_all(self._engine)
            Base.metadata.create_all(self._engine)
            return

        from dpmcore.services.schema_validation import (
            SchemaValidationService,
        )

        result = SchemaValidationService(self._engine).validate()
        if not result.is_valid:
            raise XbrlImportError(
                "Target database is not a valid DPM database: "
                f"missing tables {result.missing_tables}, empty "
                f"required tables {result.empty_required_tables}."
            )

    def _map(
        self,
        model: TaxonomyModel,
        *,
        owner_name: str,
        owner_acronym: str,
        release_code: str,
        release_date: Optional[date],
        fresh: bool,
        generate_variables: bool,
    ) -> MappingOutcome:
        session = sessionmaker(bind=self._engine)()
        try:
            mapper = TaxonomyMapper(
                session,
                owner_name=owner_name,
                owner_acronym=owner_acronym,
                release_code=release_code,
                release_date=release_date,
                fresh=fresh,
                defer_variables=generate_variables,
            )
            outcome = mapper.map_model(model)
            if generate_variables:
                self._generate_variables(
                    session, mapper, release_code
                )
            session.commit()
            return outcome
        except Exception as exc:
            session.rollback()
            if isinstance(exc, XbrlImportError):
                raise
            raise XbrlImportError(
                f"Failed to import taxonomy: {exc}"
            ) from exc
        finally:
            session.close()

    def _generate_variables(
        self,
        session: "Session",
        mapper: TaxonomyMapper,
        release_code: str,
    ) -> None:
        """Run the generation service and persist its plan.

        The mapper laid down the model with variables deferred (cells
        carry no ``variable_vid``). Here the official EBA generation
        (``variable_generation_tidy`` port) computes the plan over the
        just-mapped model and the persister writes it. The model-
        validation gate is skipped: an import materialises the model
        as published, and the 119 modelling rules would otherwise
        block generation on findings the importer cannot fix.
        """
        from dpmcore.loaders.xbrl.variable_persister import (
            VariablePlanPersister,
        )
        from dpmcore.services.variable_generation.service import (
            VariableGenerationService,
        )
        from dpmcore.services.variable_generation.types import (
            GenerationStatus,
        )

        session.flush()
        result = VariableGenerationService(session).generate(
            release_code=release_code, validate_first=False
        )
        if result.status != GenerationStatus.COMPLETED:
            details = "; ".join(
                v.message for v in result.consistency_violations[:5]
            )
            raise XbrlImportError(
                "Variable generation did not complete "
                f"({result.status.value})"
                + (f": {details}" if details else ".")
            )
        VariablePlanPersister(mapper).persist(result)


# ------------------------------------------------------------------ #
# Source handling
# ------------------------------------------------------------------ #


def _materialise_source(source: Path, workdir: Path) -> Path:
    """Return a directory for *source*, extracting zips."""
    if source.is_dir():
        return source
    if source.suffix.lower() == ".zip":
        target = workdir / "taxonomy"
        target.mkdir()
        try:
            with zipfile.ZipFile(source) as archive:
                archive.extractall(target)  # noqa: S202
        except zipfile.BadZipFile as exc:
            raise XbrlImportError(
                f"'{source}' is not a valid zip archive."
            ) from exc
        return target
    raise XbrlImportError(
        f"Taxonomy source '{source}' must be a directory or a "
        ".zip archive."
    )


def _resolve_architecture(
    root: Path, requested: str
) -> Tuple[str, Path]:
    """Detect the taxonomy architecture and its root directory."""
    if requested not in (
        ARCHITECTURE_AUTO,
        ARCHITECTURE_DPM1,
        ARCHITECTURE_EUROFILING_2006,
    ):
        raise XbrlImportError(
            f"Unknown architecture '{requested}'. Expected one of: "
            "auto, eurofiling2006, dpm1."
        )
    dpm1_root = _find_dpm1_root(root)
    if requested == ARCHITECTURE_DPM1:
        if dpm1_root is None:
            raise XbrlImportError(
                f"'{root}' does not contain a dpm1 taxonomy "
                "(no dict/ + fws/ tree found)."
            )
        return ARCHITECTURE_DPM1, dpm1_root
    has_2006 = any(root.rglob("t-*.xsd"))
    if requested == ARCHITECTURE_EUROFILING_2006:
        if not has_2006:
            raise XbrlImportError(
                f"'{root}' does not contain a 2006-architecture "
                "taxonomy (no t-*.xsd entry points found)."
            )
        return ARCHITECTURE_EUROFILING_2006, root
    if dpm1_root is not None:
        return ARCHITECTURE_DPM1, dpm1_root
    if has_2006:
        return ARCHITECTURE_EUROFILING_2006, root
    raise XbrlImportError(
        f"Could not detect the taxonomy architecture of '{root}': "
        "expected a dict/ + fws/ tree (dpm1) or t-*.xsd entry "
        "points (eurofiling2006)."
    )


def _find_dpm1_root(root: Path) -> Optional[Path]:
    candidates = [root] + sorted(
        path for path in root.rglob("*") if path.is_dir()
    )
    for candidate in candidates:
        if (candidate / "dict").is_dir() and (
            candidate / "fws"
        ).is_dir():
            return candidate
    return None


def _resolve_entry_points(
    arch_root: Path,
    entry_points: Optional[Sequence[str]],
) -> List[Path]:
    """Resolve entry-point names to files under *arch_root*."""
    if not entry_points:
        discovered = sorted(arch_root.rglob("t-*.xsd"))
        if not discovered:
            raise XbrlImportError(
                f"No t-*.xsd entry points found under '{arch_root}'."
            )
        return discovered
    resolved: List[Path] = []
    for entry in entry_points:
        direct = arch_root / entry
        if direct.is_file():
            resolved.append(direct)
            continue
        matches = sorted(arch_root.rglob(entry))
        if not matches:
            raise XbrlImportError(
                f"Entry point '{entry}' not found under "
                f"'{arch_root}'."
            )
        resolved.extend(matches)
    return resolved


def _duplicate_table_codes(
    models: Sequence[TaxonomyModel],
) -> Set[str]:
    """Table codes defined by more than one entry point."""
    seen: Set[str] = set()
    duplicates: Set[str] = set()
    for model in models:
        for table in model.tables:
            if table.code in seen:
                duplicates.add(table.code)
            seen.add(table.code)
    return duplicates


def _collapse_to_single_module(
    model: TaxonomyModel,
    framework_code: str,
    framework_name: str,
) -> TaxonomyModel:
    """Replace per-table modules with one framework-wide module.

    The 2006 reader synthesises one module per ``t-*.xsd`` entry
    point (the architecture has no native module concept). When the
    caller asks for a single module, those are collapsed into one
    module — coded/named after the framework — that comprises every
    table in discovery order. The earliest per-table validity date is
    kept as the module's ``from_date``.
    """
    from_dates = [
        mod.from_date for mod in model.modules if mod.from_date is not None
    ]
    single = XModule(
        code=framework_code,
        name=framework_name,
        entry_point="",
        table_codes=tuple(table.code for table in model.tables),
        from_date=min(from_dates) if from_dates else None,
    )
    return TaxonomyModel(**{**model.__dict__, "modules": (single,)})
