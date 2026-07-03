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
    Restrict by release code (e.g. ``"3.4"``, ``"4.2.1"``). Raises
    :class:`ValueError` if the code does not match any release.
    Preferred for user-facing input, since ``ReleaseID`` values are
    opaque from DPM 4.2.1 onwards. Any release code format is accepted.

``date`` (``str``, ``YYYY-MM-DD``)
    Restrict via ``ModuleVersion.from_reference_date`` /
    ``to_reference_date``. Useful when the calling system knows the
    business date but not the corresponding release.

When none is supplied, the active (non-ended) module versions are
returned. Passing more than one raises :class:`ValueError`.

Releases are ordered chronologically by publication date, so a release
filter returns the entities whose release-validity window contains the
target release.

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
