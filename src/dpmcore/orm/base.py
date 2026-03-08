"""Base ORM infrastructure: DeclarativeBase, engine, and session helpers."""

from typing import Any, Dict, Optional

from sqlalchemy import Engine
from sqlalchemy import create_engine as sa_create_engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Session,
    sessionmaker,
)
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    """Base for all dpmcore ORM models.

    Provides a ``to_dict`` helper that serialises column attributes
    to a plain dictionary.
    """

    def to_dict(self) -> Dict[str, Any]:
        """Serialise model instance to dictionary.

        Returns:
            Column-name → value mapping for every mapped column.
        """
        from sqlalchemy.inspection import inspect

        return {
            c.key: getattr(self, c.key)
            for c in inspect(self).mapper.column_attrs
        }


def create_engine(
    url: str,
    *,
    pool_size: int = 20,
    max_overflow: int = 40,
    pool_timeout: int = 30,
    pool_recycle: int = 3600,
    pool_pre_ping: bool = True,
    echo: bool = False,
) -> Engine:
    """Create a SQLAlchemy engine with sensible defaults.

    For SQLite in-memory databases a ``StaticPool`` is used
    automatically.

    Args:
        url: Database connection URL.
        pool_size: Connection-pool size (ignored for SQLite).
        max_overflow: Extra connections above *pool_size*.
        pool_timeout: Seconds to wait for a connection.
        pool_recycle: Recycle connections after this many seconds.
        pool_pre_ping: Verify connections before checkout.
        echo: Log all SQL statements.

    Returns:
        A configured SQLAlchemy ``Engine``.
    """
    is_sqlite = url.startswith("sqlite")
    is_memory = ":memory:" in url or "mode=memory" in url

    kwargs: Dict[str, Any] = {"echo": echo}

    if is_sqlite and is_memory:
        kwargs["poolclass"] = StaticPool
        kwargs["connect_args"] = {"check_same_thread": False}
    elif not is_sqlite:
        kwargs.update(
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_timeout=pool_timeout,
            pool_recycle=pool_recycle,
            pool_pre_ping=pool_pre_ping,
        )

    return sa_create_engine(url, **kwargs)


def create_session(engine: Engine) -> Session:
    """Create a single session bound to *engine*.

    Args:
        engine: The SQLAlchemy engine to bind.

    Returns:
        A new ``Session`` instance.
    """
    return Session(bind=engine)


class SessionFactory:
    """Callable that produces scoped sessions.

    Designed for use as a FastAPI dependency or Django middleware.

    Attributes:
        engine: The underlying SQLAlchemy engine.
    """

    def __init__(self, engine: Engine) -> None:
        """Initialise a session factory.

        Args:
            engine: The SQLAlchemy engine to bind sessions to.
        """
        self.engine = engine
        self._maker = sessionmaker(bind=engine)

    def __call__(self) -> Session:
        """Create and return a new session.

        Returns:
            A new ``Session`` instance.
        """
        return self._maker()

    def create(
        self, *, expire_on_commit: Optional[bool] = None
    ) -> Session:
        """Create a session with optional overrides.

        Args:
            expire_on_commit: Override the default expire-on-commit
                behaviour when set.

        Returns:
            A new ``Session`` instance.
        """
        kwargs: Dict[str, Any] = {}
        if expire_on_commit is not None:
            kwargs["expire_on_commit"] = expire_on_commit
        return self._maker(**kwargs)
