dpmcore
=======

A Python library that implements the DPM (Data Point Model) 2.0 Refit standard
for regulatory reporting.  It provides an ORM, services layer, and REST API that
can be used independently or together in three deployment modes.

Installation
------------

.. code-block:: bash

   pip install dpmcore

Optional extras:

.. code-block:: bash

   pip install dpmcore[data]        # Pandas support (semantic validation, scope calculation)
   pip install dpmcore[server]      # FastAPI REST server
   pip install dpmcore[django]      # Django integration
   pip install dpmcore[postgres]    # PostgreSQL backend
   pip install dpmcore[sqlserver]   # SQL Server backend
   pip install dpmcore[cli]         # Command-line interface
   pip install dpmcore[all]         # Everything

Quick Start
-----------

Mode 1 --- Standalone Library
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Use dpmcore as a plain Python library.  No web framework or HTTP server
required.

**Connect to a database:**

.. code-block:: python

   from dpmcore import connect

   # SQLite
   db = connect("sqlite:///path/to/dpm.db")

   # PostgreSQL
   db = connect("postgresql://user:pass@host:5432/dpm_db")

   # With connection pool options
   db = connect(
       "postgresql://user:pass@host:5432/dpm_db",
       pool_config={"pool_size": 20, "max_overflow": 10},
   )

**Syntax validation** (no database needed):

.. code-block:: python

   from dpmcore.services import SyntaxService

   syntax = SyntaxService()

   result = syntax.validate("{tC_01.00, r0100, c0010} + {tC_01.00, r0200, c0010}")
   print(result.is_valid)       # True
   print(result.error_message)  # None

   result = syntax.validate("invalid {{{{")
   print(result.is_valid)       # False
   print(result.error_message)  # "offendingSymbol: ..."

**Semantic validation** (requires database):

.. code-block:: python

   from dpmcore import connect

   with connect("sqlite:///dpm.db") as db:
       result = db.services.semantic.validate(
           "{tC_01.00, r0100, c0010} + {tC_01.00, r0200, c0010}",
           release_id=5,
       )
       print(result.is_valid)
       print(result.warning)

**AST generation** (three levels):

.. code-block:: python

   from dpmcore import connect

   with connect("sqlite:///dpm.db") as db:
       ast_svc = db.services.ast_generator

       # Level 1 --- Syntax AST (no database needed)
       basic = ast_svc.parse("{tC_01.00, r0100, c0010}")
       print(basic["success"])  # True
       print(basic["ast"])      # AST dict

       # Level 2 --- Semantically enriched AST
       complete = ast_svc.complete(
           "{tC_01.00, r0100, c0010}",
           release_id=5,
       )

       # Level 3 --- Engine-ready validations script
       script = ast_svc.script(
           "{tC_01.00, r0100, c0010} = {tC_01.00, r0200, c0010}",
           release_id=5,
           module_code="F_01.01",
       )

**Data dictionary queries:**

.. code-block:: python

   from dpmcore import connect

   with connect("sqlite:///dpm.db") as db:
       dd = db.services.data_dictionary

       releases = dd.get_releases()
       tables   = dd.get_tables(release_id=5)
       items    = dd.get_all_item_signatures(release_id=5)

**Operation scope calculation:**

.. code-block:: python

   from dpmcore import connect

   with connect("sqlite:///dpm.db") as db:
       result = db.services.scope_calculator.calculate_from_expression(
           expression="{tC_01.00, r0100, c0010} = {tC_01.00, r0200, c0010}",
           operation_version_id=42,
           release_id=5,
       )
       print(result.total_scopes)
       print(result.module_versions)

**Explorer --- reverse lookups:**

.. code-block:: python

   from dpmcore import connect

   with connect("sqlite:///dpm.db") as db:
       explorer = db.services.explorer

       var = explorer.get_variable_by_code("mi123", release_id=5)
       usage = explorer.get_variable_usage(variable_vid=99)
       tables = explorer.search_table("C_01")

**Hierarchy --- framework / module / table tree:**

.. code-block:: python

   from dpmcore import connect

   with connect("sqlite:///dpm.db") as db:
       hierarchy = db.services.hierarchy

       frameworks = hierarchy.get_all_frameworks(release_id=5)
       module     = hierarchy.get_module_version("F_01.01", release_id=5)
       tables     = hierarchy.get_tables_for_module("F_01.01", release_id=5)
       details    = hierarchy.get_table_details("tC_01.00", release_id=5)

**Unified facade:**

.. code-block:: python

   from dpmcore import connect

   with connect("sqlite:///dpm.db") as db:
       dpm_xl = db.services.dpm_xl

       dpm_xl.validate_syntax("{tC_01.00, r0100, c0010}")
       dpm_xl.validate_semantic("{tC_01.00, r0100, c0010}", release_id=5)

**Direct ORM access:**

.. code-block:: python

   from dpmcore import connect
   from dpmcore.orm.infrastructure import Release

   with connect("sqlite:///dpm.db") as db:
       session = db.orm
       releases = session.query(Release).all()

Mode 2 --- Web Application (REST API)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. note::

   Requires the ``server`` extra: ``pip install dpmcore[server]``

Start a ready-to-run FastAPI server exposing SDMX-inspired endpoints:

.. code-block:: bash

   dpmcore serve --database sqlite:///dpm.db --port 8000

Then browse the interactive API docs at ``http://localhost:8000/api/v1/docs``.

Mode 3 --- Django Integration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. note::

   Requires the ``django`` extra: ``pip install dpmcore[django]``

Add dpmcore to your Django project:

.. code-block:: python

   # settings.py
   INSTALLED_APPS = [
       "dpmcore.django",
       # ... your apps ...
   ]

This registers DPM models in Django admin, adds management commands, and
exposes REST endpoints mountable in your URL configuration.

Architecture
------------

::

   +---------------------------------------------------------------+
   |                   Consumer Applications                        |
   |  (Django apps, CLI tools, Jupyter notebooks, scripts, ...)     |
   +---------------------------------------------------------------+
   |                                                                |
   |  +-----------+  +----------------+  +-----------------------+  |
   |  | REST API  |  |    Services    |  |     Direct ORM        |  |
   |  | (FastAPI) |  |                |  |      access           |  |
   |  |           |  |  SyntaxService |  |                       |  |
   |  | SDMX-like |  |  SemanticSvc   |  |  session.query(...)   |  |
   |  | endpoints |  |  ASTGenerator  |  |  select(Model).where  |  |
   |  |           |  |  ScopeCalc     |  |                       |  |
   |  +-----------+  +----------------+  +-----------------------+  |
   |        |                |                     |                |
   |  +-----+----------------+---------------------+----------+    |
   |  |                     ORM Layer                          |    |
   |  |                                                        |    |
   |  |  Models . Relationships . Views . Session Management   |    |
   |  |  Multi-DB: SQLite / PostgreSQL / SQL Server            |    |
   |  +------------------------------+------------------------+    |
   |                                  |                             |
   +----------------------------------+-----------------------------+
                                      |
                              +-------+--------+
                              |    Database     |
                              +----------------+

Package Layout
--------------

::

   src/dpmcore/
   +-- __init__.py            connect(), __version__
   +-- connection.py          DpmConnection
   +-- errors.py              Exception hierarchy
   +-- orm/
   |   +-- base.py            DeclarativeBase, engine, session
   |   +-- infrastructure.py  Concept, Organisation, Release, ...
   |   +-- glossary.py        Category, Item, Property, Context, ...
   |   +-- rendering.py       Table, TableVersion, Header, Cell, ...
   |   +-- variables.py       Variable, VariableVersion, CompoundKey, ...
   |   +-- operations.py      Operation, OperationVersion, Scope, ...
   |   +-- packaging.py       Framework, Module, ModuleVersion, ...
   +-- services/
   |   +-- syntax.py          SyntaxService     (no DB)
   |   +-- semantic.py        SemanticService
   |   +-- ast_generator.py   ASTGeneratorService (3 levels)
   |   +-- scope_calculator.py ScopeCalculatorService
   |   +-- data_dictionary.py DataDictionaryService
   |   +-- explorer.py        ExplorerService
   |   +-- hierarchy.py       HierarchyService
   |   +-- dpm_xl.py          DpmXlService (facade)
   +-- dpm_xl/                DPM-XL engine internals
   |   +-- grammar/           ANTLR4 grammar + generated parser
   |   +-- ast/               AST nodes, visitor, operands
   |   +-- operators/         Arithmetic, comparison, boolean, ...
   |   +-- types/             Scalar, time, promotion
   |   +-- utils/             Serialization, scope calculator, ...
   |   +-- model_queries.py   Query compatibility layer

Development
-----------

.. code-block:: bash

   # Install all dependencies (including dev tools)
   poetry install --all-extras

   # Run tests
   poetry run pytest

   # Linting and formatting
   poetry run ruff check src/ tests/
   poetry run ruff format src/ tests/

   # Type checking
   poetry run mypy src/

License
-------

Apache-2.0 --- see `LICENSE <LICENSE>`_ for details.
