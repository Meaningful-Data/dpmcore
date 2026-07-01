``dpmcore.services.database_update``
====================================

.. module:: dpmcore.services.database_update

Safely replace an existing DPM database with fresh data. Data is loaded
into a temporary staging area and validated before the active database
is touched; if anything fails the original is left intact.

.. note::

   Requires the ``migration`` extra: ``pip install dpmcore[migration]``.

DatabaseUpdateService
---------------------

.. autoclass:: DatabaseUpdateService
   :members:
   :undoc-members:
   :show-inheritance:

DatabaseUpdateResult
--------------------

.. autoclass:: DatabaseUpdateResult
   :members:
   :undoc-members:

DatabaseUpdateError
-------------------

.. autoexception:: DatabaseUpdateError
   :show-inheritance:
