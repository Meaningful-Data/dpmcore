Installation
============

Install dpmcore from PyPI:

.. code-block:: bash

   pip install dpmcore

Optional extras
---------------

Install additional dependencies for specific features:

.. code-block:: bash

   pip install dpmcore[cli]         # Command-line interface (click, rich)
   pip install dpmcore[migration]   # Access database migration (pandas)
   pip install dpmcore[data]        # Pandas support for services
   pip install dpmcore[server]      # FastAPI REST server
   pip install dpmcore[django]      # Django integration
   pip install dpmcore[postgres]    # PostgreSQL backend
   pip install dpmcore[sqlserver]   # SQL Server backend
   pip install dpmcore[all]         # Everything

For migration from Access databases, you also need one of:

- **Linux**: ``mdb-tools`` (``apt install mdbtools`` on Debian/Ubuntu)
- **Windows/macOS**: Microsoft Access ODBC driver + ``pyodbc``
