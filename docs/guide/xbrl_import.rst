Importing XBRL taxonomies
=========================

dpmcore can import XBRL taxonomies directly into a DPM 2.0 Refit
database — dimensions, domains, members, hierarchies, metrics,
tables, datapoints, frameworks and modules. This covers taxonomies
for which no DPM database is published, such as the National Bank of
Belgium (NBB) national taxonomies.

Two taxonomy architectures are supported:

.. list-table::
   :header-rows: 1
   :widths: 22 38 40

   * - Architecture
     - Layout
     - Examples
   * - ``eurofiling2006``
     - Flat directory of ``d-*`` (dimensions/domains), ``p-*``
       (primary items) and ``t-*`` (table/hypercube) schemas and
       linkbases
     - NBB B2P2 (Basel II Pillar 2, tables 9030–9034), FIB
       (fib2008), SEG (seg2008)
   * - ``dpm1``
     - EBA-DPM-1.0-style ``dict``/``fws`` tree with PWD-2013 table
       linkbases (``*-rend.xml``)
     - NBB TREP 1.0.2

The architecture is detected automatically; pass ``--architecture``
to force one.

Prerequisites
-------------

.. code-block:: bash

   pip install dpmcore[xbrl]

This installs `Arelle <https://arelle.org>`_ (used to resolve the
2006-architecture DTSes) and lxml. ``dpm1`` taxonomies are parsed
directly with lxml and need no network access at all.

Building a new database
-----------------------

.. code-block:: bash

   dpmcore import-xbrl \
       --source ./b2p2_taxonomy \
       --framework-code B2P2 \
       --framework-name "Basel II Pillar 2" \
       --release-code 2008-01-01 --release-date 2008-01-01 \
       --database sqlite:///b2p2.db

``--source`` accepts a directory or a ``.zip`` archive. The target
schema is dropped, recreated, seeded with the DPM reference data
(data types, operators, DPM classes, languages) and populated; for
SQLite targets the file is renamed to
``<stem>_<release>_<YYYYMMDD>.db`` unless ``--output`` is given.

Importing into an existing database
-----------------------------------

.. code-block:: bash

   dpmcore import-xbrl \
       --source ./b2p2_taxonomy \
       --framework-code B2P2 \
       --release-code B2P2-2008-01-01 \
       --into sqlite:///dpm_4.2.1.db

Existing-database mode adds the taxonomy under a new ``Release``
row inside a single transaction:

- dictionary content is **reused** where possible — members match
  by their qname signature (``eba_MC:x156``), previously imported
  entities by their deterministic GUID;
- identifiers are allocated inside the owner's numeric range so
  they stay clear of future EBA release imports;
- re-importing the same taxonomy is a no-op (all ``created``
  counters zero, ``reused`` populated);
- importing a revised taxonomy version under a **new** release
  closes the previous table/module versions (their ``EndRelease``
  is set) and creates new ones.

Taxonomy revisions
------------------

Some taxonomies ship several versions of a table in one download
(B2P2 contains 2008 and 2019 versions of ``t-IntRRisk``). Only the
first occurrence of each table code is imported per run; import
revisions in a second run under their own release, restricting the
entry points:

.. code-block:: bash

   dpmcore import-xbrl --source ./b2p2_taxonomy \
       --framework-code B2P2 --release-code 2008-01-01 \
       --entry "t-*-2008-01-01.xsd" --database sqlite:///b2p2.db

   dpmcore import-xbrl --source ./b2p2_taxonomy \
       --framework-code B2P2 --release-code 2019-10-01 \
       --entry "t-IntRRisk-2019-10-01.xsd" \
       --into sqlite:///b2p2_2008-01-01_<date>.db

Offline use and web caching
---------------------------

The 2006-architecture taxonomies reference only the xbrl.org core
schemas remotely, and Arelle ships those in its bundled resource
cache — imports work offline out of the box. Pass ``--offline`` to
guarantee no network access, and ``--cache-dir`` to point Arelle at
a pre-seeded web cache for any additional remote references.

.. note::

   TREP's dictionary schemas import the retired EBA CRR dictionary
   URLs (``http://www.eba.europa.eu/xbrl/crr/dict/...``), which the
   EBA no longer serves. The ``dpm1`` reader therefore does not
   resolve the DTS at all: EBA concepts referenced by TREP tables
   are carried as opaque qnames, reused by signature when importing
   into a database that already contains the EBA dictionary, and
   created as NBB-owned shadow rows otherwise (with a warning).

Open dimensions and large domains
---------------------------------

Open dimensions (typed dimensions, or explicit dimensions without
usable members — e.g. currency) become *key headers* on the sheet
(Z) axis rather than enumerated columns. Closed dimensions whose
member product would exceed ``--max-columns`` (default 512) are
demoted to key dimensions with a warning, keeping the imported
cell grid bounded.

Using the service API
---------------------

.. code-block:: python

   from pathlib import Path
   from sqlalchemy import create_engine
   from dpmcore.loaders.xbrl import XbrlTaxonomyImportService

   engine = create_engine("sqlite:///b2p2.db")
   service = XbrlTaxonomyImportService(engine)
   result = service.import_taxonomy(
       Path("./b2p2_taxonomy"),
       framework_code="B2P2",
       release_code="2008-01-01",
   )
   print(result.created)        # {"Framework": 1, "Table": 5, ...}
   print(result.warnings)
   print(result.database_path)  # final SQLite path

Source taxonomies
-----------------

The NBB national taxonomies are published at
``https://www.nbb.be/doc/dd/onegate/data/``:

- ``2019-10-01_tables_9030-9034_basel_ii_pillar_ii_taxonomy.zip``
  (B2P2)
- ``fib2008-taxonomy.zip`` (FIB)
- ``seg2008-taxonomy.zip`` (SEG)
- ``www-nbb-be_trep_102.zip`` (TREP — extract and point
  ``--source`` at the directory containing ``dict/`` and ``fws/``,
  or at the zip itself; the root is located automatically)

COREP/FINREP and the other EBA frameworks that Belgian banks report
under are standard EBA taxonomies; import those from the
EBA-published DPM database with :doc:`migration` instead.
