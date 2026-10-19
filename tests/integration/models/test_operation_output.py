"""``OperationOutput``: the link from an operation to what it writes.

A calculation operation names the module version it outputs to through
this table. It is the join the calculations export walks. It exists in
the EBA SQL Server DPM databases, and in the Access distribution only
from release 4.4 onwards (still empty there as of 4.4).
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from dpmcore.orm.infrastructure import Organisation
from dpmcore.orm.operations import (
    Operation,
    OperationOutput,
    OperationVersion,
)
from dpmcore.orm.packaging import Framework, Module, ModuleVersion


@pytest.fixture
def linked_session(memory_session):
    """One operation version writing into one module version."""
    session = memory_session
    session.add(Framework(framework_id=1, code="FW"))
    session.add(Module(module_id=1, framework_id=1))
    session.add(ModuleVersion(module_vid=10, module_id=1, code="M"))
    session.add(Operation(operation_id=100, code="c_0001", type="calculation"))
    session.add(
        OperationVersion(
            operation_vid=100, operation_id=100, expression="x := 1"
        )
    )
    session.add(OperationOutput(operation_vid=100, module_vid=10))
    session.commit()
    return session


def test_the_operation_version_reaches_its_output_module(linked_session):
    version = linked_session.get(OperationVersion, 100)

    (output,) = version.operation_outputs
    assert output.module_version.code == "M"


def test_the_module_version_reaches_the_operations_writing_to_it(
    linked_session,
):
    module_version = linked_session.get(ModuleVersion, 10)

    (output,) = module_version.operation_outputs
    assert output.operation_version.expression == "x := 1"


def test_the_pair_is_the_primary_key(linked_session):
    linked_session.add(OperationOutput(operation_vid=100, module_vid=10))

    with pytest.raises(IntegrityError):
        linked_session.commit()
    # Leave the session usable so the fixture's rollback is a no-op.
    linked_session.rollback()


def test_one_operation_may_write_to_several_modules(linked_session):
    linked_session.add(ModuleVersion(module_vid=11, module_id=1, code="M2"))
    linked_session.add(OperationOutput(operation_vid=100, module_vid=11))
    linked_session.commit()

    version = linked_session.get(OperationVersion, 100)
    assert sorted(o.module_vid for o in version.operation_outputs) == [10, 11]


def test_the_owner_added_in_the_4_4_access_release_is_reachable(
    linked_session,
):
    linked_session.add(Organisation(org_id=1012, name="EBA"))
    output = linked_session.get(OperationOutput, (100, 10))
    output.owner_id = 1012
    linked_session.commit()

    assert linked_session.get(OperationOutput, (100, 10)).owner.name == "EBA"
