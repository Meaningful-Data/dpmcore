"""Base ORM infrastructure: declarative base, engine, and session helpers."""

from typing import TYPE_CHECKING, Any, Dict, Optional

from sqlalchemy import create_engine as sa_create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from dpmcore.orm._compat import SA2


class _ToDictMixin:
    """Mixin adding ``to_dict`` to the declarative base.

    Kept separate from the base class so it can be applied both by
    subclassing (SQLAlchemy 2.0 ``DeclarativeBase``) and via the
    ``cls=`` argument of 1.4's ``declarative_base()``.
    """

    def to_dict(self) -> Dict[str, Any]:
        """Serialise model instance to dictionary.

        Deferred columns are skipped so accessing ``to_dict()`` never
        triggers a lazy DB load for columns the caller did not ask for.

        Returns:
            Column-name → value mapping for every non-deferred column.
        """
        from sqlalchemy.orm import object_mapper

        return {
            c.key: getattr(self, c.key)
            for c in object_mapper(self).column_attrs
            if ("deferred", True) not in c.strategy_key
        }


# TYPE_CHECKING is True under mypy, so the type checker always sees the
# 2.0 ``DeclarativeBase`` subclass; at runtime the branch is chosen by
# the installed SQLAlchemy version.
if SA2 or TYPE_CHECKING:  # pragma: no cover
    from sqlalchemy.orm import DeclarativeBase

    class Base(_ToDictMixin, DeclarativeBase):
        """Base for all dpmcore ORM models."""

else:  # pragma: no cover
    from sqlalchemy.orm import declarative_base

    Base = declarative_base(cls=_ToDictMixin)


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

    # future=True is the default on SQLAlchemy 2.0 and opts 1.4 into the
    # same 2.0-style Engine/Connection semantics (Connection.commit(),
    # Result.scalar_one(), no legacy autocommit), so runtime behaviour is
    # identical across versions (see issue #104).
    kwargs: Dict[str, Any] = {"echo": echo, "future": True}

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
    return Session(bind=engine, future=True)


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
        self._maker = sessionmaker(bind=engine, future=True)

    def __call__(self) -> Session:
        """Create and return a new session.

        Returns:
            A new ``Session`` instance.
        """
        return self._maker()

    def create(self, *, expire_on_commit: Optional[bool] = None) -> Session:
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
