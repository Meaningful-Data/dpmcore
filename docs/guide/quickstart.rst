Quick Start
===========

Connect to a database
---------------------

.. code-block:: python

   from dpmcore import connect

   # SQLite
   db = connect("sqlite:///path/to/dpm.db")

   # PostgreSQL
   db = connect("postgresql://user:pass@host:5432/dpm_db")

   # With connection-pool options
   db = connect(
       "postgresql://user:pass@host:5432/dpm_db",
       pool_config={"pool_size": 20, "max_overflow": 10},
   )

   # As a context manager
   with connect("sqlite:///dpm.db") as db:
       result = db.services.dpm_xl.validate_syntax("v1 = v2")

Validate a database
-------------------

Run a shallow shape + seed-data sanity check:

.. code-block:: python

   with connect("sqlite:///dpm.db") as db:
       result = db.validate_schema()
       print(result.is_valid)                # True / False
       print(result.missing_tables)          # []
       print(result.empty_required_tables)   # []

The same check is available on the command line and exits non-zero on
failure (see :doc:`../cli`)::

   dpmcore validate --database sqlite:///dpm.db --json

Access services
---------------

Read-only DPM dictionary services are available through ``db.services``
(full reference: :doc:`../api/index`):

.. code-block:: python

   with connect("sqlite:///dpm.db") as db:
       # Syntax validation (no database needed on its own)
       db.services.syntax.validate("{tC_01.00, r0100, c0010}")

       # Semantic validation — release-aware
       db.services.semantic.validate(
           "{tC_01.00, r0100, c0010}",
           release_code="4.2.1",       # or release_id=<int>
       )

       # Data dictionary
       releases = db.services.data_dictionary.get_releases()
       tables   = db.services.data_dictionary.get_tables(release_code="4.2.1")

       # Operation scope calculation
       scope = db.services.scope_calculator.calculate_from_expression(
           expression="{tC_01.00, r0100, c0010} = {tC_01.00, r0200, c0010}",
           release_code="4.2.1",
       )

       # Explorer — reverse lookups
       var = db.services.explorer.get_variable_by_code(
           "mi123", release_code="4.2.1"
       )

       # Framework / module / table tree
       tree = db.services.hierarchy.get_all_frameworks(deep=True)
       details = db.services.hierarchy.get_table_details(
           "C_01.00", date="2024-06-30"
       )
       modelling = db.services.hierarchy.get_table_modelling("C_01.00")

Release-aware methods accept at most one of ``release_id`` /
``release_code`` / ``date``; passing more than one, or an unknown
``release_code``, raises :class:`ValueError`. Prefer ``release_code``
for human input — IDs became opaque from DPM 4.2.1 onward.

Generate an engine-ready validations script
-------------------------------------------

.. code-block:: python

   with connect("sqlite:///dpm.db") as db:
       script = db.services.ast_generator.script(
           expressions=[
               ("{tC_01.00, r0100, c0010} = {tC_01.00, r0200, c0010}", "v0001"),
               ("{tC_01.00, r0200, c0010} > 0", "v0002"),
           ],
           module_code="COREP_Con",
           module_version="2.0.1",
           severity="warning",              # global default
           severities={"v0002": "error"},   # per-validation override
           release="4.2",                   # optional; latest if omitted
       )
       # script["enriched_ast"] is keyed by the resolved module URI;
       # script["failed_operations"] lists expressions skipped due to
       # semantic errors (e.g. grey cells).

The same generation is exposed via ``dpmcore generate-script`` and the
``/api/v1/scripts`` REST endpoint.

Export table layouts to Excel
-----------------------------

.. code-block:: python

   from dpmcore.services.layout_exporter.models import ExportConfig

   with connect("sqlite:///dpm.db") as db:
       svc = db.services.layout_exporter
       svc.export_module(
           "FINREP9", release_code="4.2", output_path="finrep9.xlsx",
           config=ExportConfig(annotate=True, add_cell_comments=True),
       )

Standalone service usage
------------------------

Services that don't require a database can be used directly:

.. code-block:: python

   from dpmcore.services import SyntaxService

   syntax = SyntaxService()
   result = syntax.validate("{tC_01.00, r0100, c0010}")
   print(result.is_valid)

:class:`~dpmcore.loaders.migration.MigrationService` (which *mutates*
the database) can be used standalone with any SQLAlchemy engine:

.. code-block:: python

   from sqlalchemy import create_engine
   from dpmcore.loaders.migration import MigrationService

   engine = create_engine("sqlite:///new_dpm.db")
   service = MigrationService(engine)
   result = service.migrate_from_access("/path/to/dpm.accdb")

   print(f"Migrated {result.tables_migrated} tables, {result.total_rows} rows")

Direct ORM access
-----------------

For queries the services don't cover, use the session directly:

.. code-block:: python

   from dpmcore import connect
   from dpmcore.orm.infrastructure import Release

   with connect("sqlite:///dpm.db") as db:
       releases = db.orm.query(Release).all()
