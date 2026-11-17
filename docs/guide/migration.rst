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
   from dpmcore.loaders.migration import MigrationService

   engine = create_engine("sqlite:///dpm.db")
   service = MigrationService(engine)
   result = service.migrate_from_access("/path/to/dpm.accdb")

MigrationResult
~~~~~~~~~~~~~~~

The :class:`~dpmcore.loaders.migration.MigrationResult` dataclass contains:

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
     - ``"mdbtools"`` or ``"pyodbc"``; the source dialect (e.g.
       ``"mssql"``) for :ref:`database copies <copy-from-database>`

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

.. _copy-from-database:

Copying from another DPM database
---------------------------------

An existing DPM database can be used as the source instead of an Access
file. Any pair of supported backends works (SQLite, PostgreSQL, SQL
Server); the typical case is handing out a dictionary that lives in SQL
Server as a SQLite file.

.. code-block:: bash

   dpmcore migrate \
       --source-db "mssql+pyodbc://user:pass@host/DPM?driver=ODBC+Driver+18+for+SQL+Server" \
       --source-schema dbo \
       --database sqlite:///dpm.db --output dpm_draft.db

.. code-block:: python

   from sqlalchemy import create_engine
   from dpmcore.loaders.migration import MigrationService

   source = create_engine(
       "mssql+pyodbc://user:pass@host/DPM"
       "?driver=ODBC+Driver+18+for+SQL+Server"
   )
   target = create_engine("sqlite:///dpm.db")

   result = MigrationService(target).migrate_from_database(
       source,
       source_schema=None,  # the source's default schema when omitted
       output_path=None,    # same naming rules as migrate_from_access
   )
   result.table_details  # rows copied per table
   result.backend_used   # source dialect, e.g. "mssql"

What is copied
   Only the tables defined in the dpmcore ORM, with the whole release
   history (published and draft releases). Any other table in the
   source (application, auth or audit tables) is ignored.

Types
   Values keep the types the source database returns, so booleans,
   dates and zero-padded codes such as ``"0010"`` are copied as they
   are. The numeric guessing applied to CSV input does not run.

Consistency
   All tables are read inside a single source transaction, so a source
   that is edited during the copy cannot leave dangling references in
   the target:

   - **SQL Server** — ``SNAPSHOT`` isolation, when the database has
     ``ALLOW_SNAPSHOT_ISOLATION ON``. When it is off the copy still
     runs, under the connection's default isolation level, and a
     warning is added to ``result.warnings``; run it while nobody is
     editing the source, or enable snapshot isolation.
   - **PostgreSQL** — ``REPEATABLE READ``.
   - **SQLite** — one read transaction.

Memory
   Tables are read and written in chunks of 10 000 rows.

Different dpmcore versions
   The source may have been created by another dpmcore version. An ORM
   table missing in the source, a missing column, or a column the ORM
   does not know is reported in ``result.warnings``; missing data is
   left empty in the target.

Same-database guard
   The target's ORM tables are dropped and recreated before loading,
   so the copy is refused when the source and the target are the same
   database (same SQLite file, or same server, database and schema).
   The comparison is made on the connection URLs.

Error handling
~~~~~~~~~~~~~~

- If neither mdb-tools nor pyodbc can read the file, a
  :class:`~dpmcore.loaders.migration.MigrationError` is raised.
- If individual tables fail to load, a warning is recorded in
  ``result.warnings`` but the migration continues.
