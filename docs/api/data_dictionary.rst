``dpmcore.services.data_dictionary``
====================================

.. module:: dpmcore.services.data_dictionary

Read-only queries over the DPM dictionary: releases, tables, item
signatures, table versions, item categories, and cell coordinate
to variable resolution. Release-aware methods accept ``release_id`` or
``release_code`` (at most one).

:meth:`DataDictionaryService.resolve_cell_variables` takes either a
module version (``module_code`` + ``module_version``) or a release, not
both. A module version resolves to the same release
:meth:`~dpmcore.services.ast_generator.ASTGeneratorService.script` uses,
so the variable ids match the ones in the scripts it generates, and only
the tables of that module version resolve.

DataDictionaryService
---------------------

.. autoclass:: DataDictionaryService
   :members:
   :undoc-members:
   :show-inheritance:
