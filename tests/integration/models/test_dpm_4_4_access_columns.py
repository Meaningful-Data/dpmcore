"""Columns the DPM 4.4 Access release added to existing tables.

``TableAssociation`` gained ``StartReleaseID``/``EndReleaseID`` and
``OperandReference`` gained ``OperationVID``. Until the ORM modelled
them, migrating the 4.4 Access file dropped them with a warning.
``OperationOutput.OwnerID`` is covered in ``test_operation_output.py``.
"""

from __future__ import annotations

import pytest

from dpmcore.orm.infrastructure import Release
from dpmcore.orm.operations import (
    OperandReference,
    Operation,
    OperationNode,
    OperationVersion,
)
from dpmcore.orm.rendering import TableAssociation


@pytest.fixture
def releases(memory_session):
    session = memory_session
    session.add(Release(release_id=1, code="4.3"))
    session.add(Release(release_id=2, code="4.4"))
    session.commit()
    return session


def test_a_table_association_reaches_its_start_and_end_releases(releases):
    releases.add(
        TableAssociation(
            association_id=1,
            name="R1",
            start_release_id=1,
            end_release_id=2,
        )
    )
    releases.commit()

    association = releases.get(TableAssociation, 1)
    assert association.start_release.code == "4.3"
    assert association.end_release.code == "4.4"


def test_an_open_table_association_has_no_end_release(releases):
    releases.add(
        TableAssociation(association_id=1, name="R1", start_release_id=2)
    )
    releases.commit()

    association = releases.get(TableAssociation, 1)
    assert association.start_release.code == "4.4"
    assert association.end_release is None


def test_an_operand_reference_reaches_its_operation_version(memory_session):
    session = memory_session
    session.add(Operation(operation_id=100, code="v_0001"))
    session.add(
        OperationVersion(
            operation_vid=100, operation_id=100, expression="{tA} > 0"
        )
    )
    session.add(OperationNode(node_id=1, operation_vid=100))
    session.add(
        OperandReference(
            operand_reference_id=1,
            node_id=1,
            operand_reference="tA",
            operation_vid=100,
        )
    )
    session.commit()

    reference = session.get(OperandReference, 1)
    assert reference.operation_version.expression == "{tA} > 0"
    # The new link does not replace the one through the node.
    assert reference.operation_node.operation_vid == 100


def test_the_operation_version_link_is_optional(memory_session):
    session = memory_session
    session.add(OperationNode(node_id=1))
    session.add(
        OperandReference(
            operand_reference_id=1, node_id=1, operand_reference="tA"
        )
    )
    session.commit()

    assert session.get(OperandReference, 1).operation_version is None
