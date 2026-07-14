``dpmcore.services.ast_generator``
==================================

.. module:: dpmcore.services.ast_generator

Generate engine-ready validation scripts from DPM-XL expressions. The
resulting ``enriched_ast`` is keyed by the resolved module URI and
carries the AST, resolved release, per-validation severity, operands,
tables, preconditions, and dependency information.

The same script generation is exposed through the ``generate-script``
CLI command and the ``/api/v1/scripts`` REST endpoint.

ASTGeneratorService
-------------------

.. autoclass:: ASTGeneratorService
   :members:
   :undoc-members:
   :show-inheritance:
