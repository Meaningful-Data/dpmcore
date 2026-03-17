"""Your opinionated Python DPM library."""

from __future__ import annotations

__version__ = "0.0.1"


def __getattr__(name: str) -> object:
    """Lazy-load connection helpers on first access."""
    if name in ("connect", "DpmConnection"):
        from dpmcore.connection import DpmConnection, connect

        globals()["connect"] = connect
        globals()["DpmConnection"] = DpmConnection
        return globals()[name]
    raise AttributeError(
        f"module {__name__!r} has no attribute {name!r}"
    )


__all__ = ["__version__", "connect", "DpmConnection"]
