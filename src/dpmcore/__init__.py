"""Your opinionated Python DPM library."""

__version__ = "0.1.0rc4"

from dpmcore.connection import DpmConnection, connect

__all__ = ["__version__", "connect", "DpmConnection"]
