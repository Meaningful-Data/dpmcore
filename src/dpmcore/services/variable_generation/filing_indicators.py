"""Filing-indicator derivation (SQL ``#FICodes`` / ``#FITable``).

A filing indicator is the (trimmed) code of an active table version —
or, for technical tables derived from an abstract table, the code of
the abstract table's active version. For every code employed by a
module version starting in the current release, the plan proposes the
missing supporting objects: the Templates ``Item``/``ItemCategory``,
the single-composition ``Context`` (Template property -> item), the
``Variable`` of type ``filingindicator`` with its version (property
``isReported``), and the ``ModuleParameters`` links.

Notes on ambiguous SQL constructs (faithful readings chosen):
    * The SQL resolves the Templates category by ``Name='Templates'``
      in most steps but hard-codes ``CategoryID=1004`` in the context
      step, and compares codes sometimes trimmed and sometimes raw.
      Here the category is always resolved by name and codes are
      always compared trimmed.
    * The proposed ItemCategory signature follows the SQL literal
      ``'eba__TE:' + code``.
    * The SQL cross-joins every ``Item`` named ``Template`` /
      ``isReported``; the plan deterministically uses the one with
      the highest item id.
    * When no ``isReported`` item exists the SQL still inserts the
      Variable but no VariableVersion (and the ModuleParameters
      subquery yields NULL); the plan mirrors this by proposing a
      version-less variable and no module links.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from dpmcore.services.model_validation.release_context import (
    ReleaseContext,
)
from dpmcore.services.model_validation.snapshot import (
    ModelSnapshot,
    TableVersionRow,
)
from dpmcore.services.variable_generation.state import GenerationState
from dpmcore.services.variable_generation.types import (
    Aspect,
    OptionalRef,
    ProposedContext,
    ProposedFilingIndicator,
    ProposedVariable,
    ProposedVariableVersion,
    Ref,
)


def codes_for_table_version(
    snapshot: ModelSnapshot, tv: TableVersionRow
) -> List[str]:
    """Filing-indicator codes one active table version contributes.

    Mirrors the SQL left join: a plain table contributes its own
    (trimmed) code; a technical table contributes the codes of the
    active versions of its abstract table — or its own code when the
    abstract table has no versions at all (null-extended join), and
    nothing when all abstract versions are expired.
    """
    if tv.end_release_id is not None:
        return []
    if tv.abstract_table_id is None:
        return [tv.code.strip()] if tv.code is not None else []
    abstract_tvs = snapshot.table_versions_by_table().get(
        tv.abstract_table_id, []
    )
    if not abstract_tvs:
        return [tv.code.strip()] if tv.code is not None else []
    return [
        t2.code.strip()
        for t2 in abstract_tvs
        if t2.end_release_id is None and t2.code is not None
    ]


def _fi_codes(
    snapshot: ModelSnapshot, release: ReleaseContext
) -> List[str]:
    """Sorted codes employed by a current-release module version."""
    current_tables = {
        mvc.table_vid
        for mvc in snapshot.module_version_compositions
        if mvc.table_vid is not None
        and (
            mv := snapshot.module_versions_by_vid.get(mvc.module_vid)
        )
        is not None
        and release.is_current(mv.start_release_id)
    }
    codes = {
        code
        for tv in snapshot.table_versions
        if tv.table_vid in current_tables
        for code in codes_for_table_version(snapshot, tv)
    }
    return sorted(codes)


def _templates_category_ids(snapshot: ModelSnapshot) -> Set[int]:
    """Ids of the ``Templates`` category (resolved by name)."""
    return {
        c.category_id
        for c in snapshot.categories
        if c.name == "Templates"
    }


def _existing_template_items(
    snapshot: ModelSnapshot,
) -> Dict[str, int]:
    """Trimmed code -> item id of active Templates ItemCategories."""
    category_ids = _templates_category_ids(snapshot)
    mapping: Dict[str, int] = {}
    for ic in snapshot.item_categories:
        if (
            ic.end_release_id is not None
            or ic.category_id not in category_ids
            or ic.code is None
        ):
            continue
        code = ic.code.strip()
        if code not in mapping or ic.item_id > mapping[code]:
            mapping[code] = ic.item_id
    return mapping


def _item_by_name(
    snapshot: ModelSnapshot, name: str
) -> Optional[int]:
    """Highest item id among items with the given name."""
    ids = [it.item_id for it in snapshot.items if it.name == name]
    return max(ids) if ids else None


def _active_codes_by_item(snapshot: ModelSnapshot) -> Dict[int, Set[str]]:
    """Item id -> trimmed codes of its active ItemCategory rows."""
    mapping: Dict[int, Set[str]] = {}
    for ic in snapshot.item_categories:
        if ic.end_release_id is None and ic.code is not None:
            mapping.setdefault(ic.item_id, set()).add(ic.code.strip())
    return mapping


class _FiResolver:
    """Shared lookups for the filing-indicator stage."""

    def __init__(
        self, snapshot: ModelSnapshot, release: ReleaseContext
    ) -> None:
        """Precompute the indexes used per filing-indicator code."""
        self.snapshot = snapshot
        self.release = release
        self.items_by_code = _existing_template_items(snapshot)
        self.template_item = _item_by_name(snapshot, "Template")
        self.is_reported_item = _item_by_name(snapshot, "isReported")
        self.codes_by_item = _active_codes_by_item(snapshot)
        self.composition_count: Dict[int, int] = {}
        for cc in snapshot.context_compositions:
            self.composition_count[cc.context_id] = (
                self.composition_count.get(cc.context_id, 0) + 1
            )
        self.fi_versions: Dict[str, int] = {}
        for vv in snapshot.variable_versions:
            variable = snapshot.variables_by_id.get(
                vv.variable_id or -1
            )
            if (
                variable is None
                or variable.type != "filingindicator"
                or vv.end_release_id is not None
                or vv.code is None
            ):
                continue
            code = vv.code.strip()
            best = self.fi_versions.get(code)
            if best is None or vv.variable_vid > best:
                self.fi_versions[code] = vv.variable_vid

    def single_composition_context_exists(self, code: str) -> bool:
        """True when a 1-composition Template->code context exists."""
        return any(
            cc.property_id == self.template_item
            and cc.item_id is not None
            and code in self.codes_by_item.get(cc.item_id, set())
            and self.composition_count.get(cc.context_id) == 1
            for cc in self.snapshot.context_compositions
        )

    def context_pool(self, item_ref: OptionalRef) -> List[int]:
        """Existing contexts linking the Template property to item."""
        return [
            cc.context_id
            for cc in self.snapshot.context_compositions
            if cc.property_id == self.template_item
            and cc.item_id == item_ref
        ]

    def module_links(
        self, code: str, target_vv: OptionalRef
    ) -> Tuple[int, ...]:
        """Module versions needing a ModuleParameters link."""
        if target_vv is None:
            return ()
        existing_pairs = {
            (mp.module_vid, mp.variable_vid)
            for mp in self.snapshot.module_parameters
        }
        module_vids = {
            mvc.module_vid
            for mvc in self.snapshot.module_version_compositions
            if mvc.table_vid is not None
            and self._tv_matches(mvc.table_vid, code)
            and (
                mv := self.snapshot.module_versions_by_vid.get(
                    mvc.module_vid
                )
            )
            is not None
            and mv.end_release_id is None
            and self.release.is_current(mv.start_release_id)
            and (mvc.module_vid, target_vv) not in existing_pairs
        }
        return tuple(sorted(module_vids))

    def _tv_matches(self, table_vid: int, code: str) -> bool:
        """True when the active table version carries the FI code."""
        tv = self.snapshot.table_versions_by_vid.get(table_vid)
        if tv is None or tv.end_release_id is not None:
            return False
        return code in codes_for_table_version(self.snapshot, tv)


def generate_filing_indicators(
    snapshot: ModelSnapshot,
    release: ReleaseContext,
    state: GenerationState,
) -> None:
    """Propose the missing filing-indicator objects.

    One :class:`ProposedFilingIndicator` bundle is emitted per code
    that introduces anything new (item, context, variable or module
    link); fully pre-existing, fully linked codes are skipped.
    """
    resolver = _FiResolver(snapshot, release)
    for code in _fi_codes(snapshot, release):
        bundle = _build_bundle(code, resolver, state)
        if bundle is not None:
            state.filing_indicators.append(bundle)


def _build_bundle(
    code: str, resolver: _FiResolver, state: GenerationState
) -> Optional[ProposedFilingIndicator]:
    """Assemble the proposal bundle for one filing-indicator code."""
    existing_item = resolver.items_by_code.get(code)
    temp_id: Optional[str] = None
    item_ref: Ref
    if existing_item is None:
        temp_id = state.ids.next("fi")
        item_ref = temp_id
    else:
        item_ref = existing_item
    context_ref, new_context = _resolve_context(
        code, item_ref, resolver, state
    )
    variable_ref, version_ref, new_variable = _resolve_variable(
        code, context_ref, resolver, state
    )
    module_vids = resolver.module_links(code, version_ref)
    is_new = (
        existing_item is None
        or new_context is not None
        or new_variable is not None
        or bool(module_vids)
    )
    if not is_new:
        return None
    if temp_id is None:
        temp_id = state.ids.next("fi")
    signature = f"eba__TE:{code}" if existing_item is None else None
    return ProposedFilingIndicator(
        temp_id=temp_id,
        code=code,
        module_vids=module_vids,
        item_ref=item_ref,
        item_category_signature=signature,
        context_ref=context_ref,
        variable_ref=variable_ref,
        variable_version_ref=version_ref,
    )


def _resolve_context(
    code: str,
    item_ref: Ref,
    resolver: _FiResolver,
    state: GenerationState,
) -> Tuple[OptionalRef, Optional[ProposedContext]]:
    """Existing or proposed context for one filing indicator."""
    if resolver.template_item is None:
        return None, None
    signature = f"{resolver.template_item}_{item_ref}#"
    signature_exists = any(
        cx.signature == signature for cx in resolver.snapshot.contexts
    )
    if (
        not signature_exists
        and not resolver.single_composition_context_exists(code)
    ):
        proposed = ProposedContext(
            temp_id=state.ids.next("ctx"),
            signature=signature,
            compositions=((resolver.template_item, item_ref),),
        )
        state.fi_contexts.append(proposed)
        return proposed.temp_id, proposed
    pool = resolver.context_pool(item_ref)
    return (max(pool) if pool else None), None


def _resolve_variable(
    code: str,
    context_ref: OptionalRef,
    resolver: _FiResolver,
    state: GenerationState,
) -> Tuple[OptionalRef, OptionalRef, Optional[ProposedVariable]]:
    """Existing or proposed filing-indicator variable and version."""
    existing = resolver.fi_versions.get(code)
    if existing is not None:
        vv = resolver.snapshot.variable_versions_by_vid[existing]
        return vv.variable_id, existing, None
    var_id = state.ids.next("var")
    versions: Tuple[ProposedVariableVersion, ...] = ()
    version_ref: OptionalRef = None
    if resolver.is_reported_item is not None:
        version = ProposedVariableVersion(
            temp_id=state.ids.next("vv"),
            variable_ref=var_id,
            aspect=Aspect(
                None, resolver.is_reported_item, context_ref
            ),
            code=code,
        )
        versions = (version,)
        version_ref = version.temp_id
    variable = ProposedVariable(
        temp_id=var_id,
        type="filingindicator",
        aspect=versions[0].aspect if versions else None,
        code=code,
        versions=versions,
    )
    state.fi_variables.append(variable)
    return var_id, version_ref, variable
