"""Key variables and compound (table) keys.

Port of the SQL "IDENTIFICATION OF KEY VARIABLES" and "Generation of
Table Keys" stages: key-header properties without an active key
Variable become :class:`ProposedVariable` objects, header versions
starting in the current release get their key variable resolved
virtually, and each current-release table version's ``'#'``-joined
key-property signature is matched against ``CompoundKey`` — unseen
signatures become :class:`ProposedCompoundKey` objects.

Note:
    The SQL cleaning stage (nulling ``HeaderVersion.KeyVariableVID``
    and ``TableVersion.KeyID`` for current-release rows before
    regenerating them) has no counterpart here: the computation is
    stateless and assumes a pre-generation database, so stored values
    on current-release rows are recomputed rather than trusted.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from dpmcore.services.model_validation.release_context import (
    ReleaseContext,
)
from dpmcore.services.model_validation.snapshot import (
    HeaderVersionRow,
    ModelSnapshot,
    TableVersionRow,
)
from dpmcore.services.variable_generation.state import (
    GenerationState,
    ref_sort_key,
)
from dpmcore.services.variable_generation.types import (
    Aspect,
    ProposedCompoundKey,
    ProposedVariable,
    ProposedVariableVersion,
    Ref,
)


def _current_table_versions(
    snapshot: ModelSnapshot, release: ReleaseContext
) -> List[TableVersionRow]:
    """Current-release table versions in current-release modules.

    Table versions starting in the current release that belong to a
    module version also starting in the current release.
    """
    mvc_index = snapshot.mvc_by_table_vid()
    result = []
    for tv in snapshot.table_versions:
        if not release.is_current(tv.start_release_id):
            continue
        in_current_module = any(
            release.is_current(mv.start_release_id)
            for mvc in mvc_index.get(tv.table_vid, [])
            if (
                mv := snapshot.module_versions_by_vid.get(
                    mvc.module_vid
                )
            )
            is not None
        )
        if in_current_module:
            result.append(tv)
    return result


def _key_header_versions(
    snapshot: ModelSnapshot, table_vid: int
) -> List[HeaderVersionRow]:
    """Active header versions of the key headers of a table version.

    Mirrors the SQL's ``#tablekeycomposition`` joins: the
    ``TableVersionHeader`` link is by *HeaderID*, so every active
    version of a key header attached to the table version counts,
    not only the version the TVH row points to.
    """
    versions: List[HeaderVersionRow] = []
    for tvh in snapshot.tvh_by_table_vid().get(table_vid, []):
        header = snapshot.headers_by_id.get(tvh.header_id)
        if header is None or header.is_key is not True:
            continue
        versions.extend(
            hv
            for hv in snapshot.header_versions_by_header().get(
                tvh.header_id, []
            )
            if hv.end_release_id is None
        )
    return versions


def _active_key_versions_by_property(
    snapshot: ModelSnapshot,
) -> Dict[int, int]:
    """property_id -> active key VariableVersion (max vid on ties)."""
    mapping: Dict[int, int] = {}
    for vv in snapshot.variable_versions:
        variable = snapshot.variables_by_id.get(vv.variable_id or -1)
        if (
            variable is None
            or variable.type != "key"
            or vv.end_release_id is not None
            or vv.property_id is None
        ):
            continue
        current = mapping.get(vv.property_id)
        if current is None or vv.variable_vid > current:
            mapping[vv.property_id] = vv.variable_vid
    return mapping


def identify_key_variables(
    snapshot: ModelSnapshot,
    release: ReleaseContext,
    state: GenerationState,
) -> None:
    """Propose missing key variables and resolve header key refs.

    Mirrors ``#non_existing_keyproperties`` (the TVH join here is by
    *HeaderVID*: only the header version the table version actually
    uses counts) and the subsequent ``HeaderVersion.KeyVariableVID``
    assignment for header versions starting in the current release.

    Note:
        When several active key VariableVersions exist for the same
        property the SQL update picks one arbitrarily; the plan picks
        the one with the highest VariableVID for determinism.
    """
    existing = _active_key_versions_by_property(snapshot)
    used_hvids = {
        tvh.header_vid
        for tv in _current_table_versions(snapshot, release)
        for tvh in snapshot.tvh_by_table_vid().get(tv.table_vid, [])
        if tvh.header_vid is not None
    }
    missing: Set[int] = set()
    for hvid in used_hvids:
        hv = snapshot.header_versions_by_vid.get(hvid)
        if hv is None or hv.property_id is None:
            continue
        header = snapshot.headers_by_id.get(hv.header_id or -1)
        if header is None or header.is_key is not True:
            continue
        if hv.property_id not in existing:
            missing.add(hv.property_id)

    state.key_variable_by_property = dict(existing)
    for property_id in sorted(missing):
        var_id = state.ids.next("var")
        vv_id = state.ids.next("vv")
        version = ProposedVariableVersion(
            temp_id=vv_id,
            variable_ref=var_id,
            aspect=Aspect(None, property_id, None),
        )
        state.key_variables.append(
            ProposedVariable(
                temp_id=var_id,
                type="key",
                aspect=None,
                code=None,
                versions=(version,),
            )
        )
        state.key_variable_by_property[property_id] = vv_id

    _resolve_header_key_refs(snapshot, release, state)


def _resolve_header_key_refs(
    snapshot: ModelSnapshot,
    release: ReleaseContext,
    state: GenerationState,
) -> None:
    """Virtual ``HeaderVersion.KeyVariableVID`` for current HVs."""
    for hv in snapshot.header_versions:
        if not release.is_current(hv.start_release_id):
            continue
        header = snapshot.headers_by_id.get(hv.header_id or -1)
        if header is None or header.is_key is not True:
            continue
        if hv.property_id is None:
            continue
        ref = state.key_variable_by_property.get(hv.property_id)
        if ref is not None:
            state.header_key_refs[hv.header_vid] = ref


def _header_key_ref(
    hv: HeaderVersionRow,
    release: ReleaseContext,
    state: GenerationState,
) -> Optional[Ref]:
    """The key variable version a header version resolves to.

    Header versions starting in the current release use the virtual
    assignment; older ones keep their stored ``KeyVariableVID``.
    """
    if release.is_current(hv.start_release_id):
        return state.header_key_refs.get(hv.header_vid)
    return hv.key_variable_vid


def generate_compound_keys(
    snapshot: ModelSnapshot,
    release: ReleaseContext,
    state: GenerationState,
) -> None:
    """Build table-key signatures and propose missing compound keys.

    Mirrors ``#tablekeys``: the signature is the ``'#'``-joined list
    of the table's key-header property ids, ordered numerically, with
    a trailing ``'#'`` (duplicate property ids stemming from distinct
    key variable versions are kept, as the SQL's ``STRING_AGG`` over
    distinct (table, property, key-variable) rows would).

    Note:
        When several existing compound keys share a signature the SQL
        update picks one arbitrarily; the plan uses the highest KeyID.
    """
    compositions: Dict[int, Set[Tuple[Optional[int], Optional[Ref]]]]
    compositions = {}
    for tv in _current_table_versions(snapshot, release):
        rows = compositions.setdefault(tv.table_vid, set())
        rows.update(
            (hv.property_id, _header_key_ref(hv, release, state))
            for hv in _key_header_versions(snapshot, tv.table_vid)
        )

    signatures: Dict[int, str] = {}
    for table_vid, rows in compositions.items():
        properties = sorted(
            prop for prop, _ in rows if prop is not None
        )
        if properties:
            joined = "#".join(str(p) for p in properties)
            signatures[table_vid] = joined + "#"

    existing_keys: Dict[str, int] = {}
    for ck in snapshot.compound_keys:
        if ck.signature is None:
            continue
        best = existing_keys.get(ck.signature)
        if best is None or ck.key_id > best:
            existing_keys[ck.signature] = ck.key_id

    unseen = sorted(
        {
            signature
            for signature in signatures.values()
            if signature not in existing_keys
        }
    )
    proposed: Dict[str, str] = {}
    for signature in unseen:
        members = {
            ref
            for table_vid, sig in signatures.items()
            if sig == signature
            for _, ref in compositions[table_vid]
            if ref is not None
        }
        temp_id = state.ids.next("key")
        state.compound_keys.append(
            ProposedCompoundKey(
                temp_id=temp_id,
                signature=signature,
                member_variable_refs=tuple(
                    sorted(members, key=ref_sort_key)
                ),
            )
        )
        proposed[signature] = temp_id

    for table_vid, signature in signatures.items():
        ref: Ref = existing_keys.get(
            signature, proposed.get(signature, "")
        )
        state.key_by_table_vid[table_vid] = ref
