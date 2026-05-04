CLI Reference
=============

dpmcore provides a command-line interface for common tasks.

.. code-block:: bash

   pip install dpmcore[cli]

Global options
--------------

.. code-block:: text

   dpmcore --version    Show the version and exit.
   dpmcore --help       Show available commands.

``dpmcore migrate``
-------------------

Migrate an Access database into a SQL database.

.. code-block:: text

   dpmcore migrate --source <path> --database <url>

**Options:**

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Option
     - Description
   * - ``--source PATH``
     - Path to the Access ``.accdb`` or ``.mdb`` file. **(Required)**
   * - ``--database TEXT``
     - SQLAlchemy database URL, e.g. ``sqlite:///dpm.db`` or
       ``postgresql://user:pass@host/db``. **(Required)**

**Examples:**

.. code-block:: bash

   # SQLite
   dpmcore migrate --source dpm.accdb --database sqlite:///dpm.db

   # PostgreSQL
   dpmcore migrate \
       --source /data/dpm.accdb \
       --database postgresql://user:pass@localhost:5432/dpm

   # SQL Server
   dpmcore migrate \
       --source dpm.accdb \
       --database mssql+pyodbc://user:pass@server/db?driver=ODBC+Driver+17

``dpmcore serve``
-----------------

Start the dpmcore REST API server.

.. note::

   Requires the ``server`` extra: ``pip install dpmcore[server]``

.. code-block:: text

   dpmcore serve --database <url> [--host HOST] [--port PORT]

**Options:**

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Option
     - Description
   * - ``--database TEXT``
     - SQLAlchemy database URL. **(Required)**
   * - ``--host TEXT``
     - Bind host (default: ``127.0.0.1``).
   * - ``--port INTEGER``
     - Bind port (default: ``8000``).

**Example:**

.. code-block:: bash

   dpmcore serve --database sqlite:///dpm.db --host 0.0.0.0 --port 8000


``dpmcore export-layout``
-------------------------

Export annotated table layouts to Excel workbooks. Generates formatted
``.xlsx`` files with hierarchical headers, data-point cells, dimensional
annotations, and categorisation tooltips.

.. note::

   Requires the ``export`` extra: ``pip install dpmcore[export]``

.. code-block:: text

   dpmcore export-layout --database <url> (--module <code> | --tables <codes>) [options]

**Options:**

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Option
     - Description
   * - ``--database TEXT``
     - SQLAlchemy database URL. **(Required)**
   * - ``--module TEXT``
     - Module version code to export (e.g. ``FINREP9``, ``AE``, ``DORA``).
       Exports all tables in the module.
   * - ``--tables TEXT``
     - Comma-separated table codes (e.g. ``F_01.01,F_05.01``).
   * - ``--release TEXT``
     - Release code filter (e.g. ``4.2``). Defaults to the current
       (active) release.
   * - ``--output PATH``
     - Output file path. Defaults to ``<module>.xlsx`` or ``tables.xlsx``.
   * - ``--no-annotate``
     - Disable dimensional annotations below and to the right of the grid.
   * - ``--no-comments``
     - Disable Excel comments (tooltips) on headers and data cells.

**Examples:**

.. code-block:: bash

   # Export all tables in FINREP
   dpmcore export-layout \
       --database sqlite:///dpm.db \
       --module FINREP9 \
       --output finrep.xlsx

   # Export specific tables
   dpmcore export-layout \
       --database sqlite:///dpm.db \
       --tables F_01.01,F_01.02,F_05.01 \
       --output selected.xlsx

   # Export for a specific release, no comments (faster)
   dpmcore export-layout \
       --database sqlite:///dpm.db \
       --module AE \
       --release 4.2 \
       --no-comments \
       --output ae.xlsx

**Output format:**

Each generated workbook contains:

- An **Index** sheet with a hyperlinked table of contents
- One sheet per table (alphabetically sorted), each with:

  - Table title and optional sheet (Z-axis) header
  - Hierarchical column headers with merged cells
  - Row headers with indentation reflecting the hierarchy
  - Data cells showing the ``variable_vid`` (data point ID);
    excluded cells are greyed out
  - Dimensional annotations below the grid (for column dimensions)
    and to the right (for row dimensions), colour-coded per dimension
  - Excel comments on headers and cells showing dimensional
    categorisations (``Dimension = Member``)
  - Outline groups for expanding/collapsing hierarchical rows and columns
  - Frozen panes at the data-area origin
