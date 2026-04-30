"""Data loaders for dpmcore.

Loaders populate a DPM dictionary database from external sources.
They mutate the database; everything in :mod:`dpmcore.services` is
read-only.
"""

from dpmcore.loaders.migration import (
    MigrationError,
    MigrationResult,
    MigrationService,
)

__all__ = [
    "MigrationError",
    "MigrationResult",
    "MigrationService",
]
