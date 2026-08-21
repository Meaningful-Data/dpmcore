from datetime import date

from dpmcore.dpm_xl.model_queries import ViewDatapointsQuery
from dpmcore.orm.infrastructure import Release
from dpmcore.orm.packaging import (
    Framework,
    Module,
    ModuleVersion,
    ModuleVersionComposition,
)
from dpmcore.orm.rendering import (
    Cell,
    Header,
    HeaderVersion,
    Table,
    TableVersion,
    TableVersionCell,
)
from dpmcore.orm.variables import VariableVersion

PLAYGROUND = 9999


def _seed_adopted_and_draft_table(session):
    """Adopted table version, plus a fresh unpopulated draft sharing row 0010."""
    session.add_all(
        [
            Release(release_id=1, code="1.0", date=date(2024, 1, 1)),
            Release(
                release_id=PLAYGROUND,
                code="Playground",
                date=date(1970, 1, 1),
                type="playground",
            ),
        ]
    )
    session.add(Framework(framework_id=1, code="FW"))
    session.add(Module(module_id=1, framework_id=1))
    session.add(
        ModuleVersion(
            module_vid=10,
            module_id=1,
            start_release_id=1,
            end_release_id=PLAYGROUND,
        )
    )
    session.add(
        ModuleVersion(
            module_vid=11,
            module_id=1,
            start_release_id=PLAYGROUND,
            end_release_id=None,
        )
    )

    session.add(Table(table_id=1))
    session.add(
        TableVersion(
            table_vid=101,
            table_id=1,
            code="T_BOUNDARY",
            start_release_id=1,
            end_release_id=PLAYGROUND,
        )
    )
    session.add(
        TableVersion(
            table_vid=102,
            table_id=1,
            code="T_BOUNDARY",
            start_release_id=PLAYGROUND,
            end_release_id=None,
        )
    )
    session.add(
        ModuleVersionComposition(module_vid=10, table_vid=101, table_id=1)
    )
    session.add(
        ModuleVersionComposition(module_vid=11, table_vid=102, table_id=1)
    )

    session.add(Header(header_id=1, direction="Y", is_key=True))
    session.add(HeaderVersion(header_vid=10, header_id=1, code="0010"))
    session.add(Header(header_id=2, direction="Y", is_key=True))
    session.add(HeaderVersion(header_vid=20, header_id=2, code="0020"))

    session.add(Cell(cell_id=900, table_id=1, row_id=1))
    session.add(Cell(cell_id=901, table_id=1, row_id=2))

    session.add(VariableVersion(variable_vid=500, variable_id=50, code="V1"))

    # Row "0010": mapped in the adopted version, unmapped in the draft.
    session.add(
        TableVersionCell(
            table_vid=101,
            cell_id=900,
            cell_code="{T_BOUNDARY, r0010}",
            variable_vid=500,
            is_nullable=True,
            is_void=False,
            is_excluded=False,
        )
    )
    session.add(
        TableVersionCell(
            table_vid=102,
            cell_id=900,
            cell_code="{T_BOUNDARY, r0010}",
            variable_vid=None,
            is_nullable=True,
            is_void=False,
            is_excluded=False,
        )
    )
    # Row "0020": only exists in the draft, unmapped.
    session.add(
        TableVersionCell(
            table_vid=102,
            cell_id=901,
            cell_code="{T_BOUNDARY, r0020}",
            variable_vid=None,
            is_nullable=True,
            is_void=False,
            is_excluded=False,
        )
    )
    session.commit()


def _seed_table_where_adopted_version_also_ends_in_null(session):
    """The adopted version ends in ``NULL``, not the Playground sentinel."""
    session.add_all(
        [
            Release(release_id=1, code="1.0", date=date(2024, 1, 1)),
            Release(
                release_id=PLAYGROUND,
                code="Playground",
                date=date(1970, 1, 1),
                type="playground",
            ),
        ]
    )
    session.add(Framework(framework_id=1, code="FW"))
    session.add(Module(module_id=1, framework_id=1))
    session.add(
        ModuleVersion(
            module_vid=20, module_id=1, start_release_id=1, end_release_id=None
        )
    )
    session.add(
        ModuleVersion(
            module_vid=21,
            module_id=1,
            start_release_id=PLAYGROUND,
            end_release_id=None,
        )
    )

    session.add(Table(table_id=2))
    session.add(
        TableVersion(
            table_vid=111,
            table_id=2,
            code="T_NULL_END",
            start_release_id=1,
            end_release_id=None,
        )
    )
    session.add(
        TableVersion(
            table_vid=112,
            table_id=2,
            code="T_NULL_END",
            start_release_id=PLAYGROUND,
            end_release_id=None,
        )
    )
    session.add(
        ModuleVersionComposition(module_vid=20, table_vid=111, table_id=2)
    )
    session.add(
        ModuleVersionComposition(module_vid=21, table_vid=112, table_id=2)
    )

    session.add(Header(header_id=3, direction="Y", is_key=True))
    session.add(HeaderVersion(header_vid=30, header_id=3, code="0010"))
    session.add(Header(header_id=4, direction="Y", is_key=True))
    session.add(HeaderVersion(header_vid=40, header_id=4, code="0020"))

    session.add(Cell(cell_id=910, table_id=2, row_id=3))
    session.add(Cell(cell_id=911, table_id=2, row_id=4))

    session.add(VariableVersion(variable_vid=600, variable_id=60, code="V2"))

    session.add(
        TableVersionCell(
            table_vid=111,
            cell_id=910,
            cell_code="{T_NULL_END, r0010}",
            variable_vid=600,
            is_nullable=True,
            is_void=False,
            is_excluded=False,
        )
    )
    session.add(
        TableVersionCell(
            table_vid=112,
            cell_id=910,
            cell_code="{T_NULL_END, r0010}",
            variable_vid=None,
            is_nullable=True,
            is_void=False,
            is_excluded=False,
        )
    )
    # Row "0020": only exists in the draft, unmapped.
    session.add(
        TableVersionCell(
            table_vid=112,
            cell_id=911,
            cell_code="{T_NULL_END, r0020}",
            variable_vid=None,
            is_nullable=True,
            is_void=False,
            is_excluded=False,
        )
    )
    session.commit()


def test_adopted_version_ending_in_null_is_still_preferred(memory_session):
    """The double match also happens when the adopted version ends in NULL."""
    session = memory_session
    _seed_table_where_adopted_version_also_ends_in_null(session)

    data = ViewDatapointsQuery.get_table_data(
        session, "T_NULL_END", release_id=None
    )

    assert sorted(data["table_vid"].unique().tolist()) == [111]
    assert sorted(data["row_code"].tolist()) == ["0010"]
    assert data.loc[data["row_code"] == "0010", "variable_id"].iloc[0] == 60


def test_explicit_perpetual_release_prefers_the_adopted_version(
    memory_session,
):
    """``release_id=PLAYGROUND`` is what ``release_id=None`` resolves to internally."""
    session = memory_session
    _seed_adopted_and_draft_table(session)

    data = ViewDatapointsQuery.get_table_data(
        session, "T_BOUNDARY", release_id=PLAYGROUND
    )

    assert sorted(data["table_vid"].unique().tolist()) == [101]
    assert sorted(data["row_code"].tolist()) == ["0010"]
    assert data.loc[data["row_code"] == "0010", "variable_id"].iloc[0] == 50


def test_none_release_id_also_prefers_the_adopted_version(memory_session):
    """Direct callers passing ``release_id=None`` get the same, correct answer."""
    session = memory_session
    _seed_adopted_and_draft_table(session)

    data = ViewDatapointsQuery.get_table_data(
        session, "T_BOUNDARY", release_id=None
    )

    assert sorted(data["table_vid"].unique().tolist()) == [101]
    assert sorted(data["row_code"].tolist()) == ["0010"]
    assert data.loc[data["row_code"] == "0010", "variable_id"].iloc[0] == 50


def test_resolve_current_table_vids_falls_back_when_nothing_is_adopted(
    memory_session,
):
    """A table that only exists as drafts still resolves to something."""
    session = memory_session
    session.add_all(
        [
            Release(
                release_id=9001,
                code="Playground1",
                date=date(1970, 1, 1),
                type="playground",
            ),
            Release(
                release_id=9002,
                code="Playground2",
                date=date(1970, 1, 1),
                type="playground",
            ),
        ]
    )
    session.add(
        TableVersion(
            table_vid=201,
            code="T_ALLDRAFT",
            start_release_id=9001,
            end_release_id=None,
        )
    )
    session.add(
        TableVersion(
            table_vid=202,
            code="T_ALLDRAFT",
            start_release_id=9002,
            end_release_id=None,
        )
    )
    session.commit()

    table_vids = ViewDatapointsQuery._resolve_current_table_vids(
        session, "T_ALLDRAFT", 9001
    )

    assert sorted(table_vids) == [201, 202]
