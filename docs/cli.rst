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
