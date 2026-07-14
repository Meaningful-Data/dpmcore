Meilisearch pipeline
====================

Build a Meilisearch-ready JSON document containing all DPM operation
versions with their scopes, module assignments, operand references, and
version history. The end-to-end pipeline
(:class:`~dpmcore.services.meili_build.MeiliBuildService`) runs
*Access → CSV → in-memory SQLite → JSON*, delegating JSON generation to
:class:`~dpmcore.services.meili_json.MeiliJsonService`.

.. note::

   Requires the ``migration`` extra: ``pip install dpmcore[migration]``.

``dpmcore.services.meili_build``
--------------------------------

.. module:: dpmcore.services.meili_build

.. autoclass:: MeiliBuildService
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: MeiliBuildResult
   :members:
   :undoc-members:

.. autoexception:: MeiliBuildError
   :show-inheritance:

``dpmcore.services.meili_json``
-------------------------------

.. module:: dpmcore.services.meili_json

.. autoclass:: MeiliJsonService
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: MeiliJsonResult
   :members:
   :undoc-members:

.. autoexception:: MeiliJsonError
   :show-inheritance:
