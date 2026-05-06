``dpmcore.services.hierarchy``
==============================

.. module:: dpmcore.services.hierarchy

Framework / module / table tree queries on the DPM structure.

Use this service to walk the hierarchy from frameworks down to
individual tables, fetch a table's headers and cells, or resolve the
modelling metadata (main property + context property/item) for each
header.

Filtering
---------

The supported filter set varies by method:

* :meth:`HierarchyService.get_all_frameworks`,
  :meth:`HierarchyService.get_table_details` and
  :meth:`HierarchyService.get_table_modelling` accept
  ``release_id`` / ``release_code`` / ``date`` (at most one).
* :meth:`HierarchyService.get_module_version` and
  :meth:`HierarchyService.get_tables_for_module` accept
  ``release_id`` / ``release_code`` only — there is no ``date``
  parameter on these.

``release_id`` (``int``)
    Restrict to entities valid at the given DPM release.

``release_code`` (``str``)
    Restrict by release code (e.g. ``"3.4"``, ``"4.2.1"``). Resolved
    against :class:`Release.code` to its numeric ``ReleaseID``.
    Raises :class:`ValueError` if the code does not match any release.
    Preferred for user-facing input — ``"4.2.1"`` is more readable
    than the opaque ``ReleaseID = 1010000003`` EBA assigns.

``date`` (``str``, ``YYYY-MM-DD``)
    Restrict via ``ModuleVersion.from_reference_date`` /
    ``to_reference_date``. Useful when the calling system knows the
    business date but not the corresponding release.

When none is supplied, the active (non-ended) module versions are
returned. Passing more than one raises :class:`ValueError`.

How range comparison works
~~~~~~~~~~~~~~~~~~~~~~~~~~

DPM ``ReleaseID`` values are no longer monotonic — from 4.2.1 onwards
EBA assigns opaque IDs like ``1010000003``. ``Release`` therefore
carries a synthetic ``sort_order`` column derived from the parsed
semver ``code`` (``"4.2.1" → (4, 2, 1)``), populated automatically by
the :mod:`dpmcore.orm.release_sort_order` insert/update listeners and
backfilled by :class:`MigrationService` after bulk loads.

All range comparisons (``filter_by_release``, ``filter_item_version``,
the inline ``Release.release_id >= …`` patterns in
:class:`ASTGeneratorService` and the ECB-validations importer) compare
``sort_order`` values, not the raw ``ReleaseID``. Two consequences
worth being aware of:

* A backport published chronologically after a higher-numbered
  release — e.g. a future ``4.0.1`` shipped after ``4.2.1`` — is
  correctly placed inside the ``4.0`` lineage. A module version
  declared "valid from 4.0 to 4.2" includes the ``4.0.1`` backport.
* If a ``Release.code`` cannot be parsed as ``MAJOR.MINOR[.PATCH]``,
  ``sort_order`` is left ``NULL`` and any range filter passing that
  release as the target raises a clear :class:`ValueError` rather
  than silently returning wrong rows. Releases with unparseable codes
  simply do not participate in range filters.

HierarchyService
----------------

.. autoclass:: HierarchyService
   :members:
   :member-order: bysource
   :show-inheritance:

Examples
--------

Fetch the framework tree consumed by a DPM browser UI:

.. code-block:: python

   from dpmcore import connect

   with connect("postgresql://user:pass@host/dpm") as db:
       tree = db.services.hierarchy.get_all_frameworks(deep=True)
       for fw in tree:
           print(fw["code"], len(fw["module_versions"]))

Resolve a table at a given business date:

.. code-block:: python

   details = db.services.hierarchy.get_table_details(
       table_code="C_01.00",
       date="2024-06-30",
   )

Read the header-level modelling metadata for a table:

.. code-block:: python

   modelling = db.services.hierarchy.get_table_modelling(
       table_code="C_01.00",
       release_code="4.2.1",
   )
   for header_id, entries in modelling.items():
       for entry in entries:
           # entry is either {main_property_code, main_property_name}
           # or {context_property_code, context_property_name,
           #     context_item_code, context_item_name}
           ...
