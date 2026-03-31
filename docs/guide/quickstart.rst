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

   # As a context manager
   with connect("sqlite:///dpm.db") as db:
       result = db.services.dpm_xl.validate_syntax("v1 = v2")

Access services
---------------

All services are available through ``db.services``:

.. code-block:: python

   with connect("sqlite:///dpm.db") as db:
       # Syntax validation
       db.services.syntax.validate("{tC_01.00, r0100, c0010}")

       # Semantic validation
       db.services.semantic.validate(
           "{tC_01.00, r0100, c0010}",
           release_id=5,
       )

       # Data dictionary
       releases = db.services.data_dictionary.get_releases()

       # Migration (from Access)
       result = db.services.migration.migrate_from_access("/path/to/dpm.accdb")

       # Table layout export (to Excel)
       db.services.layout_exporter.export_module("FINREP9", output_path="finrep.xlsx")

Standalone service usage
------------------------

Services that don't require a database can be used directly:

.. code-block:: python

   from dpmcore.services import SyntaxService

   syntax = SyntaxService()
   result = syntax.validate("{tC_01.00, r0100, c0010}")
   print(result.is_valid)

The :class:`~dpmcore.services.migration.MigrationService` can be used
standalone with any SQLAlchemy engine:

.. code-block:: python

   from sqlalchemy import create_engine
   from dpmcore.services.migration import MigrationService

   engine = create_engine("sqlite:///new_dpm.db")
   service = MigrationService(engine)
   result = service.migrate_from_access("/path/to/dpm.accdb")

   print(f"Migrated {result.tables_migrated} tables, {result.total_rows} rows")
