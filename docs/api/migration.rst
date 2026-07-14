``dpmcore.loaders.migration``
==============================

.. module:: dpmcore.loaders.migration

Migration service for importing Access databases into any
SQLAlchemy-supported database.

.. note::

   ``MigrationService`` lives in :mod:`dpmcore.loaders` (it *mutates*
   the database), not in :mod:`dpmcore.services` (which are read-only).
   It is still re-exported from ``dpmcore.services`` for backward
   compatibility, but the canonical import is
   ``from dpmcore.loaders.migration import MigrationService``.

MigrationService
----------------

.. autoclass:: MigrationService
   :members:
   :undoc-members:
   :show-inheritance:

MigrationResult
---------------

.. autoclass:: MigrationResult
   :members:
   :undoc-members:

MigrationError
--------------

.. autoexception:: MigrationError
   :show-inheritance:
