``dpmcore.services.script_fixups``
===================================

.. module:: dpmcore.services.script_fixups

Known EBA source-data errors ported from mdpm's
``mdm-fix-json-values.py``. These are not generation bugs: dpmcore and
mdpm both reproduce them faithfully because the underlying
``OperationNode``/``OperandReference`` data in the DPM database itself
is wrong for a fixed set of ~20 validations. EBA doesn't amend
already-published releases, so the values stay wrong indefinitely —
this module patches an already-generated script's ``ast`` in place, a
stopgap rather than a source-side fix.

Exposed through the ``dpmcore fix-script`` CLI command (see
:doc:`../cli`), which is expected to run after every
``export-script``/``generate-script`` generation, not just once.

fix_operation_ast
------------------

.. autofunction:: fix_operation_ast

fix_module_operations
-----------------------

.. autofunction:: fix_module_operations
