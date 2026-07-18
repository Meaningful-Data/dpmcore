"""Service layer for dpmcore.

All services accept a SQLAlchemy ``Session`` as their first
constructor argument and are read-only: they query the pre-loaded DPM
dictionary but never mutate it.

Data loading (importing a DPM Access database) lives in
``dpmcore.loaders``, not here.

``MigrationService`` and ``XbrlTaxonomyImportService`` are
re-exported here for symmetry; their canonical imports are
``from dpmcore.loaders.migration import MigrationService`` and
``from dpmcore.loaders.xbrl import XbrlTaxonomyImportService``.
"""

from dpmcore.loaders.migration import MigrationService
from dpmcore.loaders.xbrl import XbrlTaxonomyImportService
from dpmcore.services.ast_generator import ASTGeneratorService
from dpmcore.services.data_dictionary import DataDictionaryService
from dpmcore.services.dpm_xl import DpmXlService
from dpmcore.services.ecb_validations_import import EcbValidationsImportService
from dpmcore.services.explorer import ExplorerService
from dpmcore.services.export_csv import ExportCsvService
from dpmcore.services.hierarchy import HierarchyService
from dpmcore.services.meili_build import MeiliBuildService
from dpmcore.services.meili_json import MeiliJsonService
from dpmcore.services.model_validation import ModelValidationService
from dpmcore.services.scope_calculator import ScopeCalculatorService
from dpmcore.services.semantic import SemanticService
from dpmcore.services.structure import StructureService
from dpmcore.services.syntax import SyntaxService
from dpmcore.services.variable_generation import (
    VariableGenerationService,
)

__all__ = [
    "SyntaxService",
    "SemanticService",
    "ASTGeneratorService",
    "ScopeCalculatorService",
    "DataDictionaryService",
    "ExplorerService",
    "HierarchyService",
    "DpmXlService",
    "MigrationService",
    "StructureService",
    "ExportCsvService",
    "MeiliJsonService",
    "MeiliBuildService",
    "EcbValidationsImportService",
    "XbrlTaxonomyImportService",
    "ModelValidationService",
    "VariableGenerationService",
]
