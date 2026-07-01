API Reference
=============

Services
--------

All services are accessible through :attr:`DpmConnection.services`:

.. code-block:: python

   from dpmcore import connect

   with connect("sqlite:///dpm.db") as db:
       db.services.syntax           # SyntaxService
       db.services.semantic         # SemanticService
       db.services.ast_generator    # ASTGeneratorService
       db.services.scope_calculator # ScopeCalculatorService
       db.services.data_dictionary  # DataDictionaryService
       db.services.explorer         # ExplorerService
       db.services.hierarchy        # HierarchyService
       db.services.dpm_xl           # DpmXlService (facade)
       db.services.layout_exporter  # LayoutExporterService
       db.services.migration        # MigrationService (Engine-based)

.. note::

   The read-only dictionary services accept a SQLAlchemy ``Session``.
   :class:`~dpmcore.loaders.migration.MigrationService` is the exception —
   it accepts an ``Engine`` because it needs ``Base.metadata.create_all()``
   and ``DataFrame.to_sql()``.

Pipeline and loader services
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

These mutate data or run end-to-end pipelines, so they live outside the
read-only ``db.services`` facade and are used standalone:

.. code-block:: python

   from dpmcore.loaders.migration import MigrationService
   from dpmcore.services.database_update import DatabaseUpdateService
   from dpmcore.services.export_csv import ExportCsvService
   from dpmcore.services.meili_build import MeiliBuildService

Read-only service references
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. toctree::
   :maxdepth: 1

   syntax
   semantic
   ast_generator
   scope_calculator
   data_dictionary
   explorer
   hierarchy
   dpm_xl
   layout_exporter
   connection

Pipeline and loader references
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. toctree::
   :maxdepth: 1

   migration
   database_update
   export_csv
   meili
