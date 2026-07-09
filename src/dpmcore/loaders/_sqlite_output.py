"""Shared SQLite output-file conventions for loaders.

Loaders that build a fresh SQLite database (Access migration, XBRL
taxonomy import) finish by moving the file to its final location and
applying the conventional ``<stem>_<release>_<YYYYMMDD>.db`` name.
This module hosts that logic so every loader names its output the
same way.
"""

from __future__ import annotations

import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from sqlalchemy import case, select
from sqlalchemy.engine import Engine

from dpmcore.orm.infrastructure import Release


def relocate_database(
    engine: Engine,
    output_path: Optional[Path],
    *,
    name_builder: Optional[Callable[[Path], str]] = None,
) -> Optional[Path]:
    """Move the SQLite file behind *engine* to its final location.

    When *output_path* is given, the file is moved there verbatim;
    otherwise the conventional ``<stem>_<release>_<YYYYMMDD>.db``
    name is applied next to the original location. Returns ``None``
    when the engine is not a SQLite file engine (``:memory:``,
    PostgreSQL, etc.). The engine is disposed before the move, so
    callers that need to reuse the database must build a new engine
    from the returned path.

    Args:
        engine: Engine whose SQLite file should be relocated.
        output_path: Optional explicit destination path.
        name_builder: Optional override that maps the current file
            path to the conventional file name; defaults to
            :func:`conventional_name`.

    Returns:
        The final file path, or ``None`` for non-file engines.
    """
    current = sqlite_file_path(engine)
    if current is None:
        return None

    if output_path is not None:
        new_path = Path(output_path)
    elif name_builder is not None:
        new_path = current.with_name(name_builder(current))
    else:
        new_path = current.with_name(conventional_name(engine, current))

    if new_path == current:
        return current

    new_path.parent.mkdir(parents=True, exist_ok=True)
    engine.dispose()
    shutil.move(str(current), str(new_path))
    return new_path


def conventional_name(
    engine: Engine,
    current: Path,
    *,
    today: Optional[str] = None,
) -> str:
    """Build the ``<stem>_<release>_<YYYYMMDD><suffix>`` filename.

    Args:
        engine: Engine used to look up the current release code.
        current: Current SQLite file path.
        today: Optional pre-computed ``YYYYMMDD`` token; defaults
            to :func:`today_token`.

    Returns:
        The conventional file name (without directory).
    """
    tokens = [current.stem]
    release_code = current_release_code(engine)
    if release_code:
        tokens.append(release_code)
    tokens.append(today if today is not None else today_token())
    return "_".join(tokens) + current.suffix


def today_token() -> str:
    """Return today's UTC date as ``YYYYMMDD``."""
    return datetime.now(tz=timezone.utc).strftime("%Y%m%d")


def sqlite_file_path(engine: Engine) -> Optional[Path]:
    """Return the engine's SQLite file path, if applicable.

    Args:
        engine: Engine to inspect.

    Returns:
        The file path, or ``None`` for non-SQLite engines,
        in-memory databases and missing files.
    """
    url = engine.url
    if url.get_backend_name() != "sqlite":
        return None
    database = url.database
    if not database or database == ":memory:":
        return None
    path = Path(database)
    if not path.is_file():
        return None
    return path


def current_release_code(engine: Engine) -> Optional[str]:
    """Return a filename-safe code for the current release.

    Args:
        engine: Engine pointing at a populated DPM database.

    Returns:
        The sanitised release code, or ``None`` when the database
        has no usable release rows.
    """
    from sqlalchemy.orm import Session

    # Latest first: an undated (unpublished) working release ranks as
    # the latest. The NULL-first CASE keeps this uniform across
    # backends (SQLite/SQL Server otherwise sort NULLs last in DESC).
    latest_first = (
        case((Release.date.is_(None), 1), else_=0).desc(),
        Release.date.desc(),
    )
    with Session(engine) as session:
        stmt = (
            select(Release.code)
            .where(Release.is_current.is_(True))
            .order_by(*latest_first)
        )
        code = session.scalars(stmt).first()
        if code is None:
            code = session.scalars(
                select(Release.code)
                .where(Release.code.is_not(None))
                .order_by(*latest_first)
            ).first()

    if not code:
        return None
    return re.sub(r"[^A-Za-z0-9.+-]+", "-", code).strip("-") or None
