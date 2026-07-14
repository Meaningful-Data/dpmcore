``dpmcore.services.export_csv``
===============================

.. module:: dpmcore.services.export_csv

Export every user table from a Microsoft Access ``.accdb`` / ``.mdb``
file to individual CSV files. Tables are exported in parallel.

.. note::

   Requires the ``migration`` extra and `mdb-tools
   <https://github.com/mdbtools/mdbtools>`_ on ``PATH``.

ExportCsvService
----------------

.. autoclass:: ExportCsvService
   :members:
   :undoc-members:
   :show-inheritance:

ExportCsvResult
---------------

.. autoclass:: ExportCsvResult
   :members:
   :undoc-members:

ExportCsvError
--------------

.. autoexception:: ExportCsvError
   :show-inheritance:
