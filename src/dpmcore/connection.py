"""Connection management for standalone library usage (Mode 1).

Usage::

    from dpmcore import connect

    db = connect("sqlite:///path/to/dpm.db")
    result = db.services.dpm_xl.validate_syntax("v1 = v2")
    db.close()

Or as a context manager::

    with connect("sqlite:///path/to/dpm.db") as db:
        result = db.services.dpm_xl.validate_syntax("v1 = v2")
"""

from __future__ import annotations

from types import TracebackType
from typing import TYPE_CHECKING, Any, Dict, Optional

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

# Ensure all ORM modules are imported so relationships resolve.
import dpmcore.orm  # noqa: F401

if TYPE_CHECKING:
    from dpmcore.loaders.migration import MigrationService
    from dpmcore.services.ast_generator import ASTGeneratorService
    from dpmcore.services.data_dictionary import DataDictionaryService
    from dpmcore.services.dpm_xl import DpmXlService
    from dpmcore.services.explorer import ExplorerService
    from dpmcore.services.hierarchy import HierarchyService
    from dpmcore.services.layout_exporter import LayoutExporterService
    from dpmcore.services.meili_json import MeiliJsonService
    from dpmcore.services.scope_calculator import ScopeCalculatorService
    from dpmcore.services.semantic import SemanticService
    from dpmcore.services.structure import StructureService
    from dpmcore.services.syntax import SyntaxService


class _ServiceAccessor:
    """Lazy container that instantiates services on first access."""

    def __init__(self, session: Session, engine: Engine) -> None:
        self._session = session
        self._engine = engine
        self._cache: Dict[str, Any] = {}

    # ------------------------------------------------------------------ #
    # DPM-XL services
    # ------------------------------------------------------------------ #

    @property
    def dpm_xl(self) -> DpmXlService:
        from dpmcore.services.dpm_xl import DpmXlService

        if "dpm_xl" not in self._cache:
            self._cache["dpm_xl"] = DpmXlService(self._session)
        service: DpmXlService = self._cache["dpm_xl"]
        return service

    @property
    def syntax(self) -> SyntaxService:
        from dpmcore.services.syntax import SyntaxService

        if "syntax" not in self._cache:
            self._cache["syntax"] = SyntaxService()
        service: SyntaxService = self._cache["syntax"]
        return service

    @property
    def semantic(self) -> SemanticService:
        from dpmcore.services.semantic import SemanticService

        if "semantic" not in self._cache:
            self._cache["semantic"] = SemanticService(self._session)
        service: SemanticService = self._cache["semantic"]
        return service

    @property
    def ast_generator(self) -> ASTGeneratorService:
        from dpmcore.services.ast_generator import ASTGeneratorService

        if "ast_generator" not in self._cache:
            self._cache["ast_generator"] = ASTGeneratorService(self._session)
        service: ASTGeneratorService = self._cache["ast_generator"]
        return service

    @property
    def scope_calculator(self) -> ScopeCalculatorService:
        from dpmcore.services.scope_calculator import ScopeCalculatorService

        if "scope_calculator" not in self._cache:
            self._cache["scope_calculator"] = ScopeCalculatorService(
                self._session,
            )
        service: ScopeCalculatorService = self._cache["scope_calculator"]
        return service

    # ------------------------------------------------------------------ #
    # Data dictionary / explorer / hierarchy
    # ------------------------------------------------------------------ #

    @property
    def data_dictionary(self) -> DataDictionaryService:
        from dpmcore.services.data_dictionary import DataDictionaryService

        if "data_dictionary" not in self._cache:
            self._cache["data_dictionary"] = DataDictionaryService(
                self._session,
            )
        service: DataDictionaryService = self._cache["data_dictionary"]
        return service

    @property
    def explorer(self) -> ExplorerService:
        from dpmcore.services.explorer import ExplorerService

        if "explorer" not in self._cache:
            self._cache["explorer"] = ExplorerService(self._session)
        service: ExplorerService = self._cache["explorer"]
        return service

    @property
    def hierarchy(self) -> HierarchyService:
        from dpmcore.services.hierarchy import HierarchyService

        if "hierarchy" not in self._cache:
            self._cache["hierarchy"] = HierarchyService(self._session)
        service: HierarchyService = self._cache["hierarchy"]
        return service

    # ------------------------------------------------------------------ #
    # Structure service
    # ------------------------------------------------------------------ #

    @property
    def structure(self) -> StructureService:
        from dpmcore.services.structure import StructureService

        if "structure" not in self._cache:
            self._cache["structure"] = StructureService(self._session)
        service: StructureService = self._cache["structure"]
        return service

    # ------------------------------------------------------------------ #
    # Layout exporter
    # ------------------------------------------------------------------ #

    @property
    def layout_exporter(self) -> "LayoutExporterService":
        from dpmcore.services.layout_exporter import LayoutExporterService

        if "layout_exporter" not in self._cache:
            self._cache["layout_exporter"] = LayoutExporterService(
                self._session,
            )
        service: LayoutExporterService = self._cache["layout_exporter"]
        return service

    # ------------------------------------------------------------------ #
    # Migration / loader (requires Engine, not Session)
    # ------------------------------------------------------------------ #

    @property
    def migration(self) -> MigrationService:
        """Return the data-loading service.

        The canonical home for :class:`MigrationService` is
        :mod:`dpmcore.loaders.migration`; this accessor is retained
        for back-compat.
        """
        from dpmcore.loaders.migration import MigrationService

        if "migration" not in self._cache:
            self._cache["migration"] = MigrationService(self._engine)
        service: MigrationService = self._cache["migration"]
        return service

    @property
    def meili_json(self) -> MeiliJsonService:
        from dpmcore.services.meili_json import MeiliJsonService

        if "meili_json" not in self._cache:
            self._cache["meili_json"] = MeiliJsonService(self._session)
        service: MeiliJsonService = self._cache["meili_json"]
        return service


class DpmConnection:
    """A connection to a DPM database.

    Holds a SQLAlchemy engine + session and exposes services through
    the :attr:`services` accessor.

    Args:
        url: SQLAlchemy connection URL.
        pool_config: Optional engine keyword arguments (pool_size,
            max_overflow, etc.).
    """

    def __init__(
        self,
        url: str,
        pool_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Build a connection for ``url`` with optional ``pool_config``."""
        engine_kwargs: Dict[str, Any] = {"pool_pre_ping": True}
        if pool_config:
            engine_kwargs.update(pool_config)

        self.engine = create_engine(url, **engine_kwargs)
        self._session_factory = sessionmaker(bind=self.engine)
        self.session: Session = self._session_factory()
        self.services = _ServiceAccessor(self.session, self.engine)

    # ------------------------------------------------------------------ #
    # ORM access
    # ------------------------------------------------------------------ #

    @property
    def orm(self) -> Session:
        """Direct access to the SQLAlchemy session.

        Use for advanced ORM queries that bypass the service layer.
        """
        return self.session

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def close(self) -> None:
        """Close the session and dispose the engine."""
        self.session.close()
        self.engine.dispose()

    def __enter__(self) -> "DpmConnection":
        """Enter the context manager."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Close the connection on context exit."""
        self.close()

    def __repr__(self) -> str:
        """Return a debug representation of the connection."""
        return f"<DpmConnection url={self.engine.url!r}>"


def connect(
    url: str,
    pool_config: Optional[Dict[str, Any]] = None,
) -> DpmConnection:
    """Open a connection to a DPM database.

    Args:
        url: A SQLAlchemy connection URL, e.g.
            ``"sqlite:///path/to/dpm.db"`` or
            ``"postgresql://user:pass@host:5432/db"``.
        pool_config: Optional engine keyword arguments.

    Returns:
        A :class:`DpmConnection` instance.
    """
    return DpmConnection(url, pool_config=pool_config)
