"""Static data files for DPM module URL mappings."""

import csv
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Optional


def _parse_date(date_str: str) -> Optional[datetime]:
    """Parse date string in DD-Mon-YY format."""
    if not date_str:
        return None
    try:
        return datetime.strptime(  # noqa: DTZ007
            date_str, "%d-%b-%y"
        )
    except ValueError:
        return None


@lru_cache(maxsize=1)
def _load_module_schema_mapping() -> list:
    """Load the module schema mapping CSV file."""
    csv_path = Path(__file__).parent / "module_schema_mapping.csv"
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [
            {
                "module_code": row["module_code"],
                "xbrl_schema_ref": row["xbrl_schema_ref"],
                "from_date": _parse_date(row["from_date"]),
                "to_date": _parse_date(row["to_date"]),
                "version": row["version"],
            }
            for row in reader
        ]


def get_module_schema_ref_by_version(
    module_code: str,
    version: str,
) -> Optional[str]:
    """Look up XBRL schema ref URL by module version.

    Args:
        module_code: e.g. ``"COREP_Con"``, ``"AE"``
        version: e.g. ``"1.2.0"``

    Returns:
        The XbrlSchemaRef URL if found, else ``None``.
    """
    mappings = _load_module_schema_mapping()
    upper = module_code.upper()
    for candidate in reversed(mappings):
        if (
            candidate["module_code"].upper() == upper
            and candidate["version"] == version
        ):
            return candidate["xbrl_schema_ref"]
    return None


def get_module_schema_ref(
    module_code: str,
    date: Optional[str] = None,
) -> Optional[str]:
    """Look up XBRL schema ref URL for a module.

    Args:
        module_code: e.g. ``"COREP_Con"``
        date: Optional ``YYYY-MM-DD`` reference date.

    Returns:
        The XbrlSchemaRef URL if found, else ``None``.
    """
    mappings = _load_module_schema_mapping()
    upper = module_code.upper()
    candidates = [m for m in mappings if m["module_code"].upper() == upper]
    if not candidates:
        return None

    if date is None:
        for c in reversed(candidates):
            if c["to_date"] is None:
                return c["xbrl_schema_ref"]
        return candidates[-1]["xbrl_schema_ref"]

    try:
        ref = datetime.strptime(  # noqa: DTZ007
            date, "%Y-%m-%d"
        )
    except ValueError:
        return None

    for c in reversed(candidates):
        from_d = c["from_date"]
        to_d = c["to_date"]
        if from_d and from_d <= ref and (to_d is None or ref <= to_d):
            return c["xbrl_schema_ref"]

    return None
