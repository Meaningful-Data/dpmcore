Migrating from Access
=====================

dpmcore can import data from Microsoft Access ``.accdb`` / ``.mdb`` files
into any SQLAlchemy-supported database (SQLite, PostgreSQL, SQL Server).

Prerequisites
-------------

You need **one** of the following backends to read Access files:

.. list-table::
   :header-rows: 1
   :widths: 20 30 50

   * - Backend
     - Platform
     - Install
   * - mdb-tools
     - Linux
     - ``apt install mdbtools`` (Debian/Ubuntu)
   * - pyodbc + Access ODBC driver
     - Windows / macOS
     - ``pip install pyodbc`` + Microsoft Access driver

The service tries mdb-tools first, then falls back to pyodbc.

You also need pandas:

.. code-block:: bash

   pip install dpmcore[migration]

Using the CLI
-------------

The simplest way to run a migration:

.. code-block:: bash

   dpmcore migrate --source /path/to/dpm.accdb --database sqlite:///dpm.db

This will:

1. Read all user tables from the Access file (system tables are skipped).
2. Create the ORM schema in the target database.
3. Load the data using ``INSERT`` (preserving ORM column types).
4. Display a summary table with row counts per table.

**Example output**:

.. code-block:: text

              Migration Results
   ┌──────────────────────┬───────┐
   │ Table                │  Rows │
   ├──────────────────────┼───────┤
   │ Release              │     8 │
   │ Framework            │     3 │
   │ Module               │    42 │
   │ Table                │   312 │
   │ ...                  │   ... │
   └──────────────────────┴───────┘

   Total: 58 tables, 145230 rows (backend: mdbtools)

Using the Python API
--------------------

Via ``DpmConnection``
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from dpmcore import connect

   with connect("postgresql://user:pass@host/dpm_db") as db:
       result = db.services.migration.migrate_from_access(
           "/path/to/dpm.accdb"
       )
       print(f"Tables: {result.tables_migrated}")
       print(f"Rows:   {result.total_rows}")
       print(f"Backend: {result.backend_used}")

       for name, count in result.table_details.items():
           print(f"  {name}: {count} rows")

       if result.warnings:
           for w in result.warnings:
               print(f"  WARNING: {w}")

Standalone (without ``DpmConnection``)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from sqlalchemy import create_engine
   from dpmcore.services.migration import MigrationService

   engine = create_engine("sqlite:///dpm.db")
   service = MigrationService(engine)
   result = service.migrate_from_access("/path/to/dpm.accdb")

MigrationResult
~~~~~~~~~~~~~~~

The :class:`~dpmcore.services.migration.MigrationResult` dataclass contains:

.. list-table::
   :header-rows: 1

   * - Field
     - Type
     - Description
   * - ``tables_migrated``
     - ``int``
     - Number of tables loaded
   * - ``total_rows``
     - ``int``
     - Total row count across all tables
   * - ``table_details``
     - ``Dict[str, int]``
     - Table name to row count mapping
   * - ``warnings``
     - ``List[str]``
     - Any non-fatal issues encountered
   * - ``backend_used``
     - ``str``
     - ``"mdbtools"`` or ``"pyodbc"``

How it works
------------

1. **Extract** — Tables are read from the Access file using mdb-tools
   (``mdb-tables`` + ``mdb-export``) or pyodbc.  Access system tables
   (``MSys*``, ``~*``) are automatically filtered out.

2. **Create schema** — ``Base.metadata.create_all(engine)`` creates all
   ORM tables if they don't exist yet.

3. **Load data** — Each table's DataFrame is written with
   ``df.to_sql(..., if_exists="append")``.  The ``append`` mode preserves
   ORM-created column types and constraints.

Type handling
~~~~~~~~~~~~~

- **mdb-tools backend**: CSV data is read as strings, then numeric
  columns are auto-detected via ``pd.to_numeric``.
- **pyodbc backend**: Column types from the Access schema metadata
  (``cursor.description``) are used to enforce types.  Text columns
  that contain numeric-looking values (e.g. postal codes ``"01234"``)
  are preserved as strings.

Error handling
~~~~~~~~~~~~~~

- If neither mdb-tools nor pyodbc can read the file, a
  :class:`~dpmcore.services.migration.MigrationError` is raised.
- If individual tables fail to load, a warning is recorded in
  ``result.warnings`` but the migration continues.
