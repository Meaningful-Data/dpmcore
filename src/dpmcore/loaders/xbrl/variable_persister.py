"""Persist a variable-generation plan into the DPM database.

:class:`~dpmcore.services.variable_generation.service
.VariableGenerationService` is compute-only: it returns a
:class:`~dpmcore.services.variable_generation.types
.VariableGenerationResult` describing the ``Variable``,
``VariableVersion``, ``Context``, ``CompoundKey`` and filing-indicator
rows the model needs, with cross references expressed as either real
database ids or plan-local temp ids (``"var:1"``, ``"vv:3"`` ...).

This module is the persistence half the service deliberately dropped:
it allocates real ids for the proposed objects, resolves every temp
reference and writes the rows, then fills each imported cell's
``variable_vid`` from the plan's per-cell assignments. It is used by
the XBRL import (:class:`~dpmcore.loaders.xbrl.service
.XbrlTaxonomyImportService`) after the mapper has laid down the model
with variables deferred.

The persister reuses the mapper's id allocator, ``Concept`` factory,
owner and release so ids and ``RowGUID``s follow the same conventions
as the rest of the import.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Optional, Tuple

from dpmcore.orm.glossary import (
    Category,
    Context,
    ContextComposition,
    Item,
    ItemCategory,
)
from dpmcore.orm.packaging import ModuleParameters
from dpmcore.orm.rendering import TableVersionCell
from dpmcore.orm.variables import (
    CompoundKey,
    KeyComposition,
    Variable,
    VariableVersion,
)
from dpmcore.services.variable_generation.types import (
    OptionalRef,
    Ref,
    VariableGenerationResult,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from dpmcore.loaders.xbrl.mapper import TaxonomyMapper


class VariablePlanPersister:
    """Write a :class:`VariableGenerationResult` to the database."""

    def __init__(self, mapper: "TaxonomyMapper") -> None:
        """Bind to the *mapper* whose import produced the model.

        Args:
            mapper: A prepared mapper; its session, id allocator,
                ``Concept`` factory, owner, release and outcome tally
                are reused so persisted rows match the import's
                conventions.
        """
        self._m = mapper
        self._session = mapper._session
        # temp id -> real id, one map per proposed object kind.
        self._ctx: Dict[str, int] = {}
        self._key: Dict[str, int] = {}
        self._var: Dict[str, int] = {}
        self._vv: Dict[str, int] = {}
        self._item: Dict[str, int] = {}

    # ------------------------------------------------------------------ #
    # Public entry point
    # ------------------------------------------------------------------ #

    def persist(self, result: VariableGenerationResult) -> None:
        """Persist every row *result* proposes and assign the cells."""
        self._allocate_ids(result)
        self._persist_contexts(result)
        self._persist_compound_keys(result)
        self._persist_variables(result)
        self._persist_variable_versions(result)
        self._persist_filing_indicators(result)
        self._assign_cells(result)
        self._session.flush()

    # ------------------------------------------------------------------ #
    # Reference resolution
    # ------------------------------------------------------------------ #

    @staticmethod
    def _resolve(ref: OptionalRef, table: Dict[str, int]) -> Optional[int]:
        """Resolve *ref* (real id, temp id or None) to a real id."""
        if ref is None:
            return None
        if isinstance(ref, int):
            return ref
        return table[ref]

    def _resolve_ctx(self, ref: OptionalRef) -> Optional[int]:
        return self._resolve(ref, self._ctx)

    def _resolve_key(self, ref: OptionalRef) -> Optional[int]:
        return self._resolve(ref, self._key)

    def _resolve_var(self, ref: Ref) -> int:
        resolved = self._resolve(ref, self._var)
        assert resolved is not None  # noqa: S101 - refs here are non-null
        return resolved

    def _resolve_vv(self, ref: OptionalRef) -> Optional[int]:
        return self._resolve(ref, self._vv)

    def _resolve_item(self, ref: Ref) -> int:
        resolved = self._resolve(ref, self._item)
        assert resolved is not None  # noqa: S101 - refs here are non-null
        return resolved

    # ------------------------------------------------------------------ #
    # Id allocation (first pass — decouples creation order from refs)
    # ------------------------------------------------------------------ #

    def _allocate_ids(self, result: VariableGenerationResult) -> None:
        ids = self._m._ids
        for ctx in result.new_contexts:
            self._ctx[ctx.temp_id] = ids.next_id(Context, "context_id")
        for key in result.new_compound_keys:
            self._key[key.temp_id] = ids.next_id(CompoundKey, "key_id")
        for var in result.new_variables:
            self._var[var.temp_id] = ids.next_id(Variable, "variable_id")
        for vv in result.new_variable_versions:
            self._vv[vv.temp_id] = ids.next_id(
                VariableVersion, "variable_vid"
            )
        for fi in result.new_filing_indicators:
            # A new Templates item is bundled when item_ref is this
            # bundle's own temp id (a str); an existing item is an int.
            if isinstance(fi.item_ref, str):
                self._item[fi.item_ref] = ids.next_id(Item, "item_id")

    # ------------------------------------------------------------------ #
    # Row creation (second pass)
    # ------------------------------------------------------------------ #

    def _persist_contexts(self, result: VariableGenerationResult) -> None:
        from dpmcore.loaders.xbrl.mapper import stable_uuid

        for ctx in result.new_contexts:
            cid = self._ctx[ctx.temp_id]
            guid = stable_uuid("Context", ctx.signature)
            self._session.add(
                Context(
                    context_id=cid,
                    signature=ctx.signature[:2000],
                    row_guid=self._m._concept("Context", guid),
                    owner_id=self._m.owner.org_id,
                )
            )
            for property_id, item_ref in ctx.compositions:
                item_id = self._resolve_item(item_ref)
                self._session.add(
                    ContextComposition(
                        context_id=cid,
                        property_id=property_id,
                        item_id=item_id,
                        row_guid=stable_uuid(
                            "ContextComposition",
                            ctx.signature,
                            property_id,
                            item_id,
                        ),
                    )
                )
            self._m.outcome.bump("Context")

    def _persist_compound_keys(
        self, result: VariableGenerationResult
    ) -> None:
        from dpmcore.loaders.xbrl.mapper import stable_uuid

        for key in result.new_compound_keys:
            kid = self._key[key.temp_id]
            guid = stable_uuid(
                "CompoundKey", self._m._framework_code, key.signature
            )
            self._session.add(
                CompoundKey(
                    key_id=kid,
                    signature=key.signature[:2000],
                    row_guid=self._m._concept("CompoundKey", guid),
                    owner_id=self._m.owner.org_id,
                )
            )
            for member_ref in key.member_variable_refs:
                vv_id = self._resolve_vv(member_ref)
                self._session.add(
                    KeyComposition(
                        key_id=kid,
                        variable_vid=vv_id,
                        row_guid=stable_uuid(
                            "KeyComposition", kid, vv_id
                        ),
                    )
                )
            self._m.outcome.bump("CompoundKey")

    def _persist_variables(
        self, result: VariableGenerationResult
    ) -> None:
        from dpmcore.loaders.xbrl.mapper import stable_uuid

        for var in result.new_variables:
            vid = self._var[var.temp_id]
            guid = stable_uuid(
                "Variable",
                self._m._framework_code,
                self._m._release_code,
                var.temp_id,
            )
            self._session.add(
                Variable(
                    variable_id=vid,
                    type=var.type,
                    row_guid=self._m._concept("Variable", guid),
                    owner_id=self._m.owner.org_id,
                )
            )
            self._m.outcome.bump("Variable")

    def _persist_variable_versions(
        self, result: VariableGenerationResult
    ) -> None:
        from dpmcore.loaders.xbrl.mapper import stable_uuid

        for vv in result.new_variable_versions:
            vvid = self._vv[vv.temp_id]
            aspect = vv.aspect
            guid = stable_uuid(
                "VariableVersion",
                self._m._framework_code,
                self._m._release_code,
                vv.temp_id,
            )
            self._session.add(
                VariableVersion(
                    variable_vid=vvid,
                    variable_id=self._resolve_var(vv.variable_ref),
                    property_id=aspect.property_id,
                    context_id=self._resolve_ctx(aspect.context_id),
                    key_id=self._resolve_key(aspect.key_id),
                    is_multi_valued=False,
                    code=vv.code[:20] if vv.code else None,
                    name=vv.name[:50] if vv.name else None,
                    start_release_id=self._m.release.release_id,
                    row_guid=self._m._concept("VariableVersion", guid),
                )
            )
            if vv.supersedes_vid is not None:
                self._close_superseded(vv.supersedes_vid)
            self._m.outcome.bump("VariableVersion")

    def _close_superseded(self, superseded_vid: int) -> None:
        """Close the ``EndReleaseID`` of a version this run replaces."""
        old = self._session.get(VariableVersion, superseded_vid)
        if old is not None and old.end_release_id is None:
            old.end_release_id = self._m.release.release_id

    def _persist_filing_indicators(
        self, result: VariableGenerationResult
    ) -> None:
        from dpmcore.loaders.xbrl.mapper import stable_uuid

        if not result.new_filing_indicators:
            return
        templates_category_id = self._ensure_templates_category()
        for fi in result.new_filing_indicators:
            # New Templates item (Item + ItemCategory) when bundled.
            if (
                isinstance(fi.item_ref, str)
                and fi.item_category_signature is not None
            ):
                item_id = self._item[fi.item_ref]
                guid = stable_uuid(
                    "Item",
                    self._m._framework_code,
                    "filingindicator",
                    fi.code,
                )
                self._session.add(
                    Item(
                        item_id=item_id,
                        name=fi.code[:500],
                        is_property=False,
                        is_active=True,
                        row_guid=self._m._concept("Item", guid),
                        owner_id=self._m.owner.org_id,
                    )
                )
                self._session.add(
                    ItemCategory(
                        item_id=item_id,
                        start_release_id=self._m.release.release_id,
                        category_id=templates_category_id,
                        code=fi.code[:20],
                        is_default_item=False,
                        signature=fi.item_category_signature[:255],
                        row_guid=stable_uuid(
                            "ItemCategory",
                            self._m._framework_code,
                            "fi",
                            fi.code,
                        ),
                    )
                )
                self._m.outcome.bump("Item")

            # Wire the filing-indicator variable version to its modules.
            vv_id = self._resolve_vv(fi.variable_version_ref)
            if vv_id is not None:
                for module_vid in fi.module_vids:
                    self._session.add(
                        ModuleParameters(
                            module_vid=module_vid,
                            variable_vid=vv_id,
                            row_guid=stable_uuid(
                                "ModuleParameters", module_vid, vv_id
                            ),
                        )
                    )

    def _ensure_templates_category(self) -> int:
        """Get-or-create the ``Templates`` category for FI items.

        Filing-indicator items live in a category named ``Templates``
        (the generation service resolves them there). A taxonomy import
        does not carry that reference category, so it is created on
        first need; re-imports reuse it, which lets the generation
        service detect the existing filing-indicator items by code.
        """
        from dpmcore.loaders.xbrl.mapper import stable_uuid

        existing = (
            self._session.query(Category)
            .filter(Category.name == "Templates")
            .order_by(Category.category_id)
            .first()
        )
        if existing is not None:
            return existing.category_id
        guid = stable_uuid("Category", self._m._framework_code, "Templates")
        category_id = self._m._ids.next_id(Category, "category_id")
        self._session.add(
            Category(
                category_id=category_id,
                code="_TEMPLATES",
                name="Templates",
                is_enumerated=False,
                is_active=True,
                is_external_ref_data=False,
                row_guid=self._m._concept("Category", guid),
                created_release_id=self._m.release.release_id,
                owner_id=self._m.owner.org_id,
            )
        )
        self._session.flush()
        self._m.outcome.bump("Category")
        return category_id

    # ------------------------------------------------------------------ #
    # Cell assignment
    # ------------------------------------------------------------------ #

    def _assign_cells(self, result: VariableGenerationResult) -> None:
        """Point every imported cell at its generated variable version."""
        by_cell: Dict[Tuple[int, int], TableVersionCell] = {
            (tvc.table_vid, tvc.cell_id): tvc
            for tvc in self._session.query(TableVersionCell).all()
        }
        for assignment in result.cell_assignments:
            vv_id = self._resolve_vv(assignment.new_variable_vid_ref)
            if vv_id is None:
                continue
            tvc = by_cell.get(
                (assignment.table_vid, assignment.cell_id)
            )
            if tvc is not None:
                tvc.variable_vid = vv_id
