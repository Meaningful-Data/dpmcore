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
       db.services.migration        # MigrationService (Engine-based)

.. note::

   Most services accept a SQLAlchemy ``Session``.
   :class:`~dpmcore.services.migration.MigrationService` is the exception —
   it accepts an ``Engine`` because it needs ``Base.metadata.create_all()``
   and ``DataFrame.to_sql()``.

Service references
~~~~~~~~~~~~~~~~~~

.. toctree::
   :maxdepth: 1

   hierarchy
   migration
   connection
