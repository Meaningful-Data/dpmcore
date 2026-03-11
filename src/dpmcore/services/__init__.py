"""Service layer for dpmcore.

All services accept a SQLAlchemy ``Session`` as their first
constructor argument, except :class:`MigrationService` which accepts
an ``Engine`` (it needs ``Base.metadata.create_all`` and
``DataFrame.to_sql``).  Services never create engines, sessions or
connections themselves — that responsibility belongs to the
connection layer (``dpmcore.connection``).
"""

from dpmcore.services.ast_generator import ASTGeneratorService
from dpmcore.services.data_dictionary import DataDictionaryService
from dpmcore.services.dpm_xl import DpmXlService
from dpmcore.services.explorer import ExplorerService
from dpmcore.services.hierarchy import HierarchyService
from dpmcore.services.migration import MigrationService
from dpmcore.services.scope_calculator import ScopeCalculatorService
from dpmcore.services.semantic import SemanticService
from dpmcore.services.structure import StructureService
from dpmcore.services.syntax import SyntaxService

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
]
