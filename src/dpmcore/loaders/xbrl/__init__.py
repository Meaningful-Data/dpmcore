"""XBRL taxonomy importer for dpmcore.

Imports XBRL taxonomies (dimensions, domains, members, hierarchies,
metrics, tables and datapoints) into a DPM 2.0 Refit database. Two
taxonomy architectures are supported:

- ``eurofiling2006`` — the 2006 Eurofiling architecture used by the
  National Bank of Belgium national taxonomies B2P2, FIB and SEG
  (flat directories of ``d-*``/``p-*``/``t-*`` schemas and
  linkbases).
- ``dpm1`` — the EBA DPM-1.0-style architecture used by TREP
  (``dict``/``fws``/``tab`` trees with table linkbases).

Parsing is delegated to Arelle (optional extra ``dpmcore[xbrl]``);
everything downstream of the neutral intermediate model in
:mod:`dpmcore.loaders.xbrl.model` is dependency-free.
"""

from dpmcore.loaders.xbrl.model import (
    ARCHITECTURE_AUTO,
    ARCHITECTURE_DPM1,
    ARCHITECTURE_EUROFILING_2006,
    TaxonomyModel,
    XbrlImportError,
)
from dpmcore.loaders.xbrl.service import (
    XbrlImportResult,
    XbrlTaxonomyImportService,
)

__all__ = [
    "ARCHITECTURE_AUTO",
    "ARCHITECTURE_DPM1",
    "ARCHITECTURE_EUROFILING_2006",
    "TaxonomyModel",
    "XbrlImportError",
    "XbrlImportResult",
    "XbrlTaxonomyImportService",
]
