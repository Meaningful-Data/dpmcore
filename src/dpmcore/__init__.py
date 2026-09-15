"""Your opinionated Python DPM library."""

__version__ = "0.2.0"

from dpmcore.connection import DpmConnection, connect

__all__ = ["__version__", "connect", "DpmConnection"]
