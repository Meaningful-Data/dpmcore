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

from typing import Any, Dict, Optional

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

# Ensure all ORM modules are imported so relationships resolve.
import dpmcore.orm  # noqa: F401


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
    def dpm_xl(self):
        from dpmcore.services.dpm_xl import DpmXlService

        if "dpm_xl" not in self._cache:
            self._cache["dpm_xl"] = DpmXlService(self._session)
        return self._cache["dpm_xl"]

    @property
    def syntax(self):
        from dpmcore.services.syntax import SyntaxService

        if "syntax" not in self._cache:
            self._cache["syntax"] = SyntaxService()
        return self._cache["syntax"]

    @property
    def semantic(self):
        from dpmcore.services.semantic import SemanticService

        if "semantic" not in self._cache:
            self._cache["semantic"] = SemanticService(self._session)
        return self._cache["semantic"]

    @property
    def ast_generator(self):
        from dpmcore.services.ast_generator import ASTGeneratorService

        if "ast_generator" not in self._cache:
            self._cache["ast_generator"] = ASTGeneratorService(self._session)
        return self._cache["ast_generator"]

    @property
    def scope_calculator(self):
        from dpmcore.services.scope_calculator import ScopeCalculatorService

        if "scope_calculator" not in self._cache:
            self._cache["scope_calculator"] = ScopeCalculatorService(
                self._session,
            )
        return self._cache["scope_calculator"]

    # ------------------------------------------------------------------ #
    # Data dictionary / explorer / hierarchy
    # ------------------------------------------------------------------ #

    @property
    def data_dictionary(self):
        from dpmcore.services.data_dictionary import DataDictionaryService

        if "data_dictionary" not in self._cache:
            self._cache["data_dictionary"] = DataDictionaryService(
                self._session,
            )
        return self._cache["data_dictionary"]

    @property
    def explorer(self):
        from dpmcore.services.explorer import ExplorerService

        if "explorer" not in self._cache:
            self._cache["explorer"] = ExplorerService(self._session)
        return self._cache["explorer"]

    @property
    def hierarchy(self):
        from dpmcore.services.hierarchy import HierarchyService

        if "hierarchy" not in self._cache:
            self._cache["hierarchy"] = HierarchyService(self._session)
        return self._cache["hierarchy"]

    # ------------------------------------------------------------------ #
    # Structure service
    # ------------------------------------------------------------------ #

    @property
    def structure(self):
        from dpmcore.services.structure import StructureService

        if "structure" not in self._cache:
            self._cache["structure"] = StructureService(self._session)
        return self._cache["structure"]

    # ------------------------------------------------------------------ #
    # Migration (requires Engine, not Session)
    # ------------------------------------------------------------------ #

    @property
    def migration(self):
        from dpmcore.services.migration import MigrationService

        if "migration" not in self._cache:
            self._cache["migration"] = MigrationService(self._engine)
        return self._cache["migration"]


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
    def orm(self):
        """Direct access to the SQLAlchemy session for advanced ORM
        queries."""
        return self.session

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def close(self) -> None:
        """Close the session and dispose the engine."""
        self.session.close()
        self.engine.dispose()

    def __enter__(self) -> "DpmConnection":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def __repr__(self) -> str:
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
