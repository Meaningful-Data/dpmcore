"""Rule modules for model validation.

Importing this package registers every rule with the registry. Each
module covers one rule family of the original SQL procedure:

- ``lifecycle`` — family 1_x (module/table/tablegroup versioning)
- ``axes`` — family 2_x (table axis structure)
- ``headers`` — family 3_x (header-level rules)
- ``assignments`` — family 4_x (property/context/item assignment)
- ``glossary`` — family 6_x (code hygiene and catalog integrity)
"""

from dpmcore.services.model_validation.rules import (  # noqa: F401
    assignments,
    axes,
    glossary,
    headers,
    lifecycle,
)
