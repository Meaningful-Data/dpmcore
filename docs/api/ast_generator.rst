``dpmcore.services.ast_generator``
==================================

.. module:: dpmcore.services.ast_generator

Generate engine-ready validation scripts from DPM-XL expressions. The
resulting ``enriched_ast`` is a Script Format 2.0 document: it carries
the AST, resolved release, per-validation severity, preconditions,
the ``modules`` the validations read, and their dependency groups.

The same script generation is exposed through the ``generate-script``
CLI command and the ``/api/v1/scripts`` REST endpoint.

The service also exports a module's **calculations** set --
:meth:`~ASTGeneratorService.calculations_for_module` and its companion
:meth:`~ASTGeneratorService.calculations_datapoints` -- which is the
operations linked to the module version through ``OperationOutput``,
rather than the validations scoped to it. That export is exposed through
the ``export-calculations`` CLI command.

ASTGeneratorService
-------------------

.. autoclass:: ASTGeneratorService
   :members:
   :undoc-members:
   :show-inheritance:

Calculations export
-------------------

.. module:: dpmcore.services.calculations_export

.. autoclass:: CalculationsExport

.. autoclass:: CalculationsExporter
   :members:
   :undoc-members:
