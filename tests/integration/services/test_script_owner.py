"""Integration tests for the owner of a validations script.

Script Format 2.0: one document per owner, the organisation
that defined the validations, read from ``Operation.OwnerID``.
"""

from __future__ import annotations

from sqlalchemy import event

from dpmcore.orm.infrastructure import Organisation
from dpmcore.orm.operations import Operation, OperationVersion
from dpmcore.services.ast_generator import ASTGeneratorService


def _seed(session):
    session.add_all(
        [
            Organisation(
                org_id=1, name="European Banking Authority", acronym="EBA"
            ),
            Organisation(
                org_id=2, name="European Central Bank", acronym="ECB"
            ),
            Operation(operation_id=10, code="v1", owner_id=2),
            Operation(operation_id=11, code="v2", owner_id=1),
            Operation(operation_id=12, code="v3", owner_id=None),
            OperationVersion(operation_vid=100, operation_id=10),
            OperationVersion(operation_vid=101, operation_id=10),
            OperationVersion(operation_vid=110, operation_id=11),
            OperationVersion(operation_vid=120, operation_id=12),
        ]
    )
    session.flush()


def test_operation_owners_by_operation_version(memory_session):
    _seed(memory_session)
    svc = ASTGeneratorService(memory_session)

    owners = svc._operation_owners([100, 101, 110, 120])

    assert owners == {100: "ECB", 101: "ECB", 110: "EBA", 120: None}


def test_operation_owners_ignores_other_versions(memory_session):
    _seed(memory_session)
    svc = ASTGeneratorService(memory_session)

    assert svc._operation_owners([110]) == {110: "EBA"}


def test_operation_owners_of_a_large_module_stay_under_the_bound_limit(
    memory_session,
):
    """More than 2,100 validations, the parameters SQL Server binds
    per statement, do not fail the lookup.
    """
    _seed(memory_session)
    svc = ASTGeneratorService(memory_session)
    vids = [100, 110, 120, *range(10_000, 12_500)]
    bound: list[int] = []

    def _count(conn, cursor, statement, parameters, context, many):
        bound.append(len(parameters))

    engine = memory_session.get_bind()
    event.listen(engine, "before_cursor_execute", _count)
    try:
        owners = svc._operation_owners(vids)
    finally:
        event.remove(engine, "before_cursor_execute", _count)

    assert owners == {100: "ECB", 110: "EBA", 120: None}
    assert bound
    assert max(bound) <= 2100


def test_module_owner_reads_only_the_acronym(memory_session):
    from dpmcore.orm.packaging import Module

    _seed(memory_session)
    memory_session.add_all(
        [
            Module(module_id=5, owner_id=1),
            Module(module_id=6, owner_id=None),
        ]
    )
    memory_session.flush()
    svc = ASTGeneratorService(memory_session)

    assert svc._module_owner(module_id=5) == "EBA"
    assert svc._module_owner(module_id=6) is None
    assert svc._module_owner(module_id=999) is None
