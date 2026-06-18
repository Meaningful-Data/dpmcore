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

``dpmcore validate``
--------------------

Run a shallow shape + data-sanity check on a database. Reports missing
tables, missing columns, and required seed tables that exist but are
empty. Designed to be cheap (tens of milliseconds on a real DPM
database) — not a deep audit. Comparisons are case-insensitive so the
same check works across SQLite, PostgreSQL, and SQL Server.

.. code-block:: text

   dpmcore validate --database <url> [--json]

**Options:**

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Option
     - Description
   * - ``--database TEXT``
     - SQLAlchemy database URL. **(Required)**
   * - ``--json``
     - Emit the result as a JSON document instead of a rich table.
       Useful for CI/healthcheck scripts.

**Exit codes:**

* ``0`` — schema is valid (all expected tables and columns present and
  all required seed tables non-empty).
* ``1`` — at least one of: missing table, missing column, empty
  required seed table.

**Examples:**

.. code-block:: bash

   # Human-readable output
   dpmcore validate --database sqlite:///dpm.db

   # JSON output (e.g. for CI)
   dpmcore validate --database sqlite:///dpm.db --json

   # Use as a healthcheck (in scripts)
   dpmcore validate --database "$DB_URL" --json > /dev/null \
       && echo "ok" || echo "schema check failed"

``dpmcore update-db``
---------------------

Safely update a DPM database from CSV files or an Access file.

The command loads data into a temporary staging area, validates it, and only
then atomically replaces the active database. If any step fails the active
database is left untouched.

- **SQLite** — data is loaded into a hidden temp file; the target ``.db`` file
  is replaced only after validation passes.
- **PostgreSQL / SQL Server** — data is loaded into a temporary staging schema;
  after validation the staging schema is swapped atomically into the active
  position.

.. code-block:: text

   dpmcore update-db --target <url_or_path> [options]

**Options:**

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Option
     - Description
   * - ``--target TEXT``
     - Target database. Accepts a SQLite path (``dpm.db``, ``dpm.sqlite``,
       ``dpm.sqlite3``), a SQLite URL (``sqlite:///path/to/dpm.db``), a
       PostgreSQL URL (``postgresql://user:pass@host/db``), or a SQL Server
       URL (``mssql+pyodbc://user:pass@server/db?driver=...``).
       **(Required)**
   * - ``--access-file PATH``
     - Path to an Access ``.accdb`` or ``.mdb`` file. When provided, the
       Access file is exported to CSV automatically before loading.
       If omitted, CSV files are read directly from ``data/DPM/``.
   * - ``--ecb-validations-file PATH``
     - Path to an ECB validations CSV file. When provided, the file is
       imported after the main migration and before final validation.
   * - ``--dry-run``
     - Load and validate data without replacing the active database.
       Useful to check whether new data is valid before committing the
       update.
   * - ``--keep-staging``
     - Keep the temporary SQLite file or the staging/backup schemas after
       the command finishes. Useful for debugging failed updates.

**Examples:**

.. code-block:: bash

   # Update a SQLite database from the default CSV directory (data/DPM/)
   dpmcore update-db --target dpm.db

   # Update using a SQLite URL
   dpmcore update-db --target sqlite:///path/to/dpm.db

   # Update from an Access file
   dpmcore update-db \
       --target dpm.db \
       --access-file /path/to/DPM_v4_2_1.accdb

   # Include ECB validations
   dpmcore update-db \
       --target dpm.db \
       --ecb-validations-file ecb_validations.csv

   # Dry run — validate only, do not replace active database
   dpmcore update-db --target dpm.db --dry-run

   # Dry run keeping the staging file for inspection
   dpmcore update-db --target dpm.db --dry-run --keep-staging

   # Update a PostgreSQL database
   dpmcore update-db \
       --target postgresql://user:pass@localhost:5432/dpm \
       --ecb-validations-file ecb_validations.csv

   # Update a SQL Server database
   dpmcore update-db \
       --target "mssql+pyodbc://user:pass@server/dpm?driver=ODBC+Driver+17+for+SQL+Server"

**Exit codes:**

- ``0`` — update completed successfully (or dry run validated successfully).
- ``1`` — update failed; the active database was not modified.

``dpmcore export-csv``
----------------------

Export all user tables from a Microsoft Access database to CSV files.

Requires **mdb-tools** (``mdb-tables`` + ``mdb-export``) to be installed and
available in ``PATH``.  Tables are exported in parallel (up to 8 workers).

.. code-block:: text

   dpmcore export-csv SOURCE [--output-dir PATH]

**Arguments / Options:**

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Argument / Option
     - Description
   * - ``SOURCE``
     - Path to the Access ``.accdb`` or ``.mdb`` file. **(Required)**
   * - ``--output-dir PATH``
     - Directory where ``<TableName>.csv`` files are written.
       Created (including parents) if it does not exist.
       Defaults to ``data/DPM``.

**Examples:**

.. code-block:: bash

   # Export to the default directory (data/DPM/)
   dpmcore export-csv /path/to/DPM_v4_2_1.accdb

   # Export to a custom directory
   dpmcore export-csv /path/to/DPM_v4_2_1.accdb --output-dir exports/csv

``dpmcore build-meili-json``
----------------------------

Build a Meilisearch-ready JSON file containing all DPM operation versions with
their scopes, module assignments, operand references, and version history.

The pipeline is: *Access → CSV → in-memory SQLite → JSON*. When
``--access-file`` is supplied the CSV export is handled transparently.
``--source-dir`` and ``--access-file`` are mutually exclusive; at least one
must be supplied.

.. code-block:: text

   dpmcore build-meili-json [--source-dir PATH | --access-file PATH]
                            [--ecb-validations-file PATH] [--output PATH]

**Options:**

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Option
     - Description
   * - ``--source-dir PATH``
     - Directory containing pre-exported CSV tables (e.g. ``data/DPM``).
       Mutually exclusive with ``--access-file``.
   * - ``--access-file PATH``
     - Path to an Access ``.accdb`` or ``.mdb`` file. The file is exported
       to a temporary CSV directory automatically.
       Mutually exclusive with ``--source-dir``.
   * - ``--ecb-validations-file PATH``
     - Optional path to an ECB validations CSV file. When provided, ECB
       validation versions are imported before building the JSON.
   * - ``--output PATH``
     - Output JSON file path. Defaults to ``operations.json``.

**Examples:**

.. code-block:: bash

   # From a pre-exported CSV directory
   dpmcore build-meili-json --source-dir data/DPM --output operations.json

   # Directly from an Access file (CSV export handled transparently)
   dpmcore build-meili-json \
       --access-file /path/to/DPM_v4_2_1.accdb \
       --output operations.json

   # With optional ECB validations
   dpmcore build-meili-json \
       --access-file /path/to/DPM_v4_2_1.accdb \
       --ecb-validations-file ecb_validations.csv \
       --output operations.json

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


``dpmcore generate-graph``
--------------------------

Build a portable, self-contained HTML **dependency graph** from a DPM-XL
calculations script. The graph shows the execution order of the operations:
one node per operation, one arrow per dependency. The output is a single
``.html`` file with its rendering libraries (Cytoscape.js + the dagre layout)
embedded inline, so it opens offline and can be attached to a ticket or sent
to another person as a single file.

Provide exactly **one** input source:

#. a ``Code,Expression`` **CSV file** (the ``CSV`` argument);
#. one or more inline **``-e CODE=EXPRESSION``** operations (handy for a
   quick, ad-hoc graph without authoring a file); or
#. **``--database URL``** to read the DPM dictionary directly (the *engine
   mode*; see below).

The CSV and inline modes need no database — dependencies are derived from the
DPM-XL AST. The engine mode reads the dictionary's pre-resolved operands.

.. code-block:: text

   dpmcore generate-graph CSV [-o OUTPUT] [-t TITLE]
   dpmcore generate-graph -e CODE=EXPRESSION [-e ...] [-o OUTPUT] [-t TITLE]
   dpmcore generate-graph --database URL [--module C] [--table T]
                          [--release R] [-o OUTPUT] [-t TITLE]

**Arguments / Options:**

.. list-table::
   :header-rows: 1
   :widths: 32 68

   * - Argument / Option
     - Description
   * - ``CSV``
     - Path to the calculations-script CSV.
   * - ``-e, --expression CODE=EXPRESSION``
     - An inline operation, given as a ``Code`` and its DPM-XL expression
       separated by ``=`` (split on the first ``=``). Repeatable.
   * - ``--database TEXT``
     - SQLAlchemy database URL. Engine mode: builds the graph from the DPM
       dictionary using the engine's resolved operand cells.
   * - ``--module TEXT``
     - Engine mode only: restrict to operations in this module version code.
   * - ``--table TEXT``
     - Engine mode only: restrict to operations referencing this table code.
   * - ``--release TEXT``
     - Engine mode only: restrict to operations active in this release code
       (e.g. ``4.2``).
   * - ``-o, --output PATH``
     - Output HTML path. Defaults to ``calculations_graph.html``.
   * - ``-t, --title TEXT``
     - Graph title. Defaults to a title derived from the input.

**Engine mode (``--database``):**

Real DPM dictionaries store each operation as a validation/equality
(``with {scope}: {LHS} = {RHS}``), not a ``<-`` assignment, so the text modes
above find no dependencies in them. Engine mode instead reads the engine's
already-resolved operand tree: for an ``=`` operation the ``left`` side is the
**output** cell and the ``right`` side the **inputs**, and operations are
linked when one writes a variable another reads (exact ``VariableID`` match,
with ranges/wildcards/sheets already expanded by the engine). The full
dictionary has thousands of operations, so a ``--module`` / ``--table`` /
``--release`` filter is recommended to keep the graph readable.

**Input format:**

A CSV with a ``Code,Expression`` header. Each row is one operation:

- ``Code`` is the bare operation code. It must **not** start with ``o`` —
  explicit references use that prefix (see below).
- ``Expression`` is a DPM-XL assignment of the form
  ``<lhs selection> <- with {default:..., interval:...}: (<rhs expression>)``.
  The left-hand side selection is the operation's output; the right-hand side
  reads its inputs through selection operators ``{...}``. Because expressions
  contain commas, quote the ``Expression`` field.

**Dependencies:**

An arrow ``A -> B`` is drawn when operation ``B`` depends on ``A``:

- **Implicit** — ``B`` reads a cell that ``A`` writes (matched on
  table/row/column/sheet).
- **Explicit** — ``B`` references ``A`` directly via ``{o<A-code>}``.

Operations with no incoming arrow are **roots** and are shown in a distinct
colour. Click a node to see its output cell and full expression; the panel
also offers search/filter and ``Fit`` / ``Re-layout`` controls.

.. note::

   In the CSV / inline modes dependency detection runs without a database, so
   concrete cell-range expansion (the exact row codes a ``0010-0050`` range
   covers) is approximated by numeric range *overlap*. Wildcards, the sheet
   dimension and operation references are handled exactly. Engine mode
   (``--database``) avoids the approximation by using the dictionary's
   pre-resolved cells.

**Examples:**

.. code-block:: bash

   # Default output (calculations_graph.html)
   dpmcore generate-graph calculations_script.csv

   # Custom output path and title
   dpmcore generate-graph calculations_script.csv \
       -o output/graph.html \
       -t "COREP calculations"

   # Inline expressions, no CSV file needed
   dpmcore generate-graph \
       -e "calc1={tK_1.00, r0010, c0010} <- {tK_2.00, r0010, c0010}" \
       -e "calc2={tK_3.00, r0010, c0010} <- {tK_1.00, r0010, c0010} + 1" \
       -o graph.html

   # Engine mode: read the DPM dictionary directly (filter to one table)
   dpmcore generate-graph \
       --database sqlite:///dpm.db \
       --table C_01.00 \
       -o graph.html

**Vendored libraries:**

The embedded JavaScript (Cytoscape.js, dagre, cytoscape-dagre — all MIT) is
vendored under ``dpmcore/services/calculations_graph/assets/``. Their pinned
versions, source URLs and update steps are recorded in ``assets/VENDOR.md``.
