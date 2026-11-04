"""Pieces of the Script Format 2.0 document shared by its producers.

The format version and how the file is named.
"""

from __future__ import annotations

FORMAT_VERSION = "2.0"
"""Script Format version of the documents dpmcore produces."""


def script_file_name(owner: str, module_code: str, module_version: str) -> str:
    """Return ``<owner>-<module_code>-<module_version>.json``.

    Raises:
        ValueError: If a part is blank: the file name would not
            identify the document.
    """
    if not (owner and module_code and module_version):
        raise ValueError(
            "A script file name needs an owner, a module code and a "
            f"module version; got {owner!r}, {module_code!r}, "
            f"{module_version!r}."
        )
    return f"{owner}-{module_code}-{module_version}.json"
