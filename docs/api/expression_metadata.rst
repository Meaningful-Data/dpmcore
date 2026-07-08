``dpmcore.services.expression_metadata``
========================================

.. module:: dpmcore.services.expression_metadata

Resolve the DPM entities (tables, headers, frameworks) that a DPM-XL
expression references. Where
:class:`~dpmcore.services.scope_calculator.ScopeCalculatorService`
answers "which module versions does this expression touch?", this
service answers "given that expression, which concrete tables /
headers / frameworks do I need to persist alongside it?".

Callers get plain ``list[dict]`` back — no ORM instances leak — so
the results are safe to hand to a downstream ORM or serializer
without holding onto the SQLAlchemy session.

Usage
-----

.. code-block:: python

   from dpmcore import connect

   with connect("sqlite:///dpm.db") as db:
       svc = db.services.expression_metadata

       tables = svc.get_referenced_tables(
           expression="{tF_01.01, r0010, c0010} = 100",
           release_id=42,
       )
       headers = svc.get_referenced_headers(
           expression="{tF_01.01, r0010, c0010} = 100",
           release_id=42,
       )
       frameworks = svc.get_referenced_frameworks(
           expression="{tF_01.01, r0010, c0010} = 100",
           release_id=42,
       )

The ``header_type`` field on each header entry reflects the header's
*use* in the expression (``r*`` → ``"Row"``, ``c*`` → ``"Column"``,
``s*`` → ``"Sheet"``), not the catalog ``Header.direction`` — two
tables that share a code but are transposed relative to each other
both emit rows whose ``header_type`` matches the syntax the
expression used.

Any parser or semantic failure degrades to an empty list rather than
raising.

ExpressionMetadataService
-------------------------

.. autoclass:: ExpressionMetadataService
   :members:
   :undoc-members:
   :show-inheritance:
