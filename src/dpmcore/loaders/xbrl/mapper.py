"""Mapping of the neutral taxonomy model onto DPM Refit ORM rows.

The :class:`TaxonomyMapper` consumes a
:class:`~dpmcore.loaders.xbrl.model.TaxonomyModel` and creates the
corresponding ORM rows following the conventions observed in real
EBA DPM 2.0 Refit databases:

- every entity hangs off a ``Concept`` row whose GUID is a
  deterministic UUID5 of the entity's stable key, so re-imports are
  idempotent;
- domains become ``Category`` rows, members become ``Item`` +
  ``ItemCategory`` rows whose ``Signature`` is the XBRL qname;
- dimensions and metrics become ``Item`` + ``Property`` pairs whose
  counterpart items live in the ``_PR`` category under a global
  ``<type-letter>i<seq>`` code sequence;
- hierarchies become ``SubCategory`` / ``SubCategoryVersion`` /
  ``SubCategoryItem`` trees.

Identifier allocation follows the two observed regimes: plain
``max + 1`` in fresh databases, owner-prefixed ranges when importing
into an existing (EBA-populated) database.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Tuple, Type

from sqlalchemy import func
from sqlalchemy.orm import Session

from dpmcore.loaders.xbrl import seeds
from dpmcore.loaders.xbrl.model import (
    DIRECTION_X,
    DIRECTION_Y,
    DIRECTION_Z,
    TaxonomyModel,
    XAxis,
    XbrlImportError,
    XCell,
    XDimension,
    XDomain,
    XHeaderNode,
    XHierarchy,
    XLabel,
    XMember,
    XMetric,
    XModule,
    XTable,
)
from dpmcore.orm.base import Base
from dpmcore.orm.glossary import (
    Category,
    Context,
    ContextComposition,
    Item,
    ItemCategory,
    Property,
    PropertyCategory,
    SubCategory,
    SubCategoryItem,
    SubCategoryVersion,
)
from dpmcore.orm.infrastructure import (
    Concept,
    Organisation,
    Release,
    Translation,
)
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
    TableVersionHeader,
)
from dpmcore.orm.variables import Variable, VariableVersion

_NBB_XBRL_UUID_NAMESPACE = uuid.UUID(
    "d5c1a2b8-90f4-4c5e-8a3d-2b7e6f0c4a91"
)

#: Canonical GUIDs of the special categories in EBA databases; reused
#: verbatim so fresh NBB databases stay merge-compatible.
_PR_CATEGORY_GUID = "{F8D60235-EEB5-49B2-B9010B020E0FF56E}"
_NA_CATEGORY_GUID = "{A526D965-641A-42E1-BAC128BF80AD37E1}"
_PR_CATEGORY_ID = 1002
_NA_CATEGORY_ID = 1003

_PERIOD_TYPE_MAP = {"instant": "stock", "duration": "flow"}

#: Normalised XSD/XBRL type local name -> DPM data-type code.
_DATA_TYPE_BY_LOCAL = {
    "monetary": "m",
    "percent": "p",
    "string": "s",
    "normalizedstring": "s",
    "boolean": "b",
    "integer": "i",
    "int": "i",
    "long": "i",
    "nonnegativeinteger": "i",
    "positiveinteger": "i",
    "decimal": "r",
    "float": "r",
    "double": "r",
    "date": "d",
    "datetime": "dt",
    "anyuri": "u",
    "qname": "e",
    "enumeration": "e",
}

#: Entities allocated inside owner-prefixed ID ranges when importing
#: into an existing database (high-volume tables).
_PREFIXED_MODELS = frozenset(
    {
        "Item",
        "Context",
        "Variable",
        "VariableVersion",
        "Header",
        "HeaderVersion",
        "Cell",
        "TableVersion",
        "SubCategoryVersion",
    }
)

_PREFIX_WIDTH = 6
_RELEASE_PREFIX_WIDTH = 7


def stable_uuid(*parts: object) -> str:
    """Build a deterministic Access-style GUID from *parts*.

    Args:
        parts: Stable key components; ``None`` renders as ``""``.

    Returns:
        An upper-case ``{UUID}`` string (38 characters).
    """
    text = "|".join("" if part is None else str(part) for part in parts)
    return f"{{{str(uuid.uuid5(_NBB_XBRL_UUID_NAMESPACE, text)).upper()}}}"


@dataclass
class MappingOutcome:
    """Mutable tally of what a mapping run did.

    Attributes:
        release_id: The release the import ran under.
        created: Rows created, keyed by entity name.
        reused: Pre-existing rows reused, keyed by entity name.
        warnings: Non-fatal findings collected while mapping.
    """

    release_id: int = 0
    created: Dict[str, int] = field(default_factory=dict)
    reused: Dict[str, int] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    def bump(self, entity: str, *, reused: bool = False) -> None:
        """Count one created (or reused) row for *entity*."""
        target = self.reused if reused else self.created
        target[entity] = target.get(entity, 0) + 1


class IdAllocator:
    """Sequential ID allocation with owner-prefixed ranges.

    In fresh databases every entity starts at ``max + 1`` (i.e. 1).
    In existing databases, high-volume entities are allocated inside
    the owner's numeric range (``<org_id><6-digit seq>``) so they
    stay clear of future EBA release imports; low-volume entities
    fall back to ``max + 1``.
    """

    def __init__(self, session: Session, *, fresh: bool) -> None:
        """Initialise the allocator.

        Args:
            session: Target database session.
            fresh: Whether the database was newly created by this
                import run.
        """
        self._session = session
        self._fresh = fresh
        self._org_id: Optional[int] = None
        self._next: Dict[str, int] = {}

    def set_owner(self, org_id: int) -> None:
        """Fix the owning organisation used for prefixed ranges."""
        self._org_id = org_id

    def next_id(self, model: Type[Base], attr_name: str) -> int:
        """Return the next identifier for *model*.

        Args:
            model: ORM entity class.
            attr_name: Name of the integer primary-key attribute.

        Returns:
            The allocated identifier.
        """
        key = model.__name__
        if key not in self._next:
            self._next[key] = self._first_id(model, attr_name)
        value = self._next[key]
        self._next[key] = value + 1
        return value

    def _first_id(self, model: Type[Base], attr_name: str) -> int:
        column = getattr(model, attr_name)
        if (
            not self._fresh
            and model.__name__ in _PREFIXED_MODELS
            and self._org_id is not None
        ):
            base = self._org_id * 10**_PREFIX_WIDTH
            upper = base + 10**_PREFIX_WIDTH
            current = (
                self._session.query(func.max(column))
                .filter(column >= base, column < upper)
                .scalar()
            )
            return int(current) + 1 if current is not None else base + 1
        current = self._session.query(func.max(column)).scalar()
        return int(current or 0) + 1


class TaxonomyMapper:
    """Map a :class:`TaxonomyModel` onto ORM rows.

    Args:
        session: Target database session (caller commits).
        owner_name: Name of the owning organisation.
        owner_acronym: Acronym of the owning organisation.
        release_code: Code of the release created for this import.
        release_date: Date of the release.
        fresh: Whether the target database was newly created (and
            seeded) by this import run.
    """

    def __init__(
        self,
        session: Session,
        *,
        owner_name: str,
        owner_acronym: str,
        release_code: str,
        release_date: Optional[date] = None,
        fresh: bool = True,
        defer_variables: bool = False,
    ) -> None:
        """Initialise the mapper; see class docstring.

        When *defer_variables* is set, cells are created without an
        inline ``VariableVersion`` (``variable_vid`` left unset and no
        ``Variable``/``Context`` rows synthesised); the caller is
        expected to run the variable-generation service and persist
        its plan afterwards.
        """
        self._session = session
        self._owner_name = owner_name
        self._owner_acronym = owner_acronym
        self._release_code = release_code
        self._release_date = release_date
        self._fresh = fresh
        self._defer_variables = defer_variables

        self.outcome = MappingOutcome()
        self._ids = IdAllocator(session, fresh=fresh)

        # Populated by prepare().
        self._class_ids: Dict[str, int] = {}
        self._attr_ids: Dict[Tuple[str, str], int] = {}
        self._data_types: Dict[str, int] = {}
        self._languages: Dict[str, int] = {}
        self._org: Optional[Organisation] = None
        self._release: Optional[Release] = None
        self._cat_pr: Optional[Category] = None
        self._cat_na: Optional[Category] = None

        # Registries built while mapping the dictionary.
        self._framework_code = ""
        self._item_by_qname: Dict[str, Item] = {}
        self._property_by_qname: Dict[str, Property] = {}
        self._category_by_domain: Dict[str, Category] = {}
        self._typed_type_by_domain: Dict[str, Optional[str]] = {}
        self._member_seq: Dict[int, int] = {}
        self._pr_seq: Optional[int] = None
        self._used_category_codes: Dict[str, str] = {}

        # Registries built while mapping tables and modules.
        self._tablev_by_code: Dict[str, TableVersion] = {}
        self._context_by_signature: Dict[str, Context] = {}
        self._varv_by_key: Dict[Tuple[int, Optional[int]], VariableVersion]
        self._varv_by_key = {}
        self._shadowed_qnames: set[str] = set()

    # -------------------------------------------------------------- #
    # Setup
    # -------------------------------------------------------------- #

    def prepare(self) -> None:
        """Seed reference data and resolve owner, release, categories."""
        self._class_ids = seeds.ensure_dpm_classes(self._session)
        self._attr_ids = seeds.ensure_dpm_attributes(self._session)
        self._data_types = seeds.ensure_data_types(self._session)
        self._languages = seeds.ensure_languages(self._session)
        seeds.ensure_operators(self._session)
        self._org = self._ensure_owner()
        self._ids.set_owner(self._org.org_id)
        self._release = self._ensure_release()
        self.outcome.release_id = self._release.release_id
        self._cat_pr = self._ensure_special_category(
            "_PR",
            "Properties",
            _PR_CATEGORY_GUID,
            _PR_CATEGORY_ID,
            is_enumerated=True,
        )
        self._cat_na = self._ensure_special_category(
            "_NA",
            "Not applicable",
            _NA_CATEGORY_GUID,
            _NA_CATEGORY_ID,
            is_enumerated=False,
        )

    @property
    def release(self) -> Release:
        """The release this import runs under."""
        if self._release is None:
            raise XbrlImportError("Mapper is not prepared.")
        return self._release

    @property
    def owner(self) -> Organisation:
        """The owning organisation."""
        if self._org is None:
            raise XbrlImportError("Mapper is not prepared.")
        return self._org

    def _ensure_owner(self) -> Organisation:
        org = (
            self._session.query(Organisation)
            .filter(Organisation.acronym == self._owner_acronym)
            .one_or_none()
        )
        if org is not None:
            self.outcome.bump("Organisation", reused=True)
            return org

        org_id = self._ids.next_id(Organisation, "org_id")
        max_prefix = (
            self._session.query(func.max(Organisation.id_prefix)).scalar()
            or 0
        )
        guid = stable_uuid("Organisation", self._owner_acronym)
        org = Organisation(
            org_id=org_id,
            name=self._owner_name,
            acronym=self._owner_acronym,
            id_prefix=int(max_prefix) + 1,
            row_guid=self._concept("Organisation", guid, owner_id=org_id),
        )
        self._session.add(org)
        self._session.flush()
        self.outcome.bump("Organisation")
        return org

    def _ensure_release(self) -> Release:
        release = (
            self._session.query(Release)
            .filter(Release.code == self._release_code)
            .one_or_none()
        )
        if release is not None:
            self.outcome.bump("Release", reused=True)
            return release

        if self._fresh:
            release_id = self._ids.next_id(Release, "release_id")
        else:
            release_id = self._next_release_id()
        release = Release(
            release_id=release_id,
            code=self._release_code,
            date=self._release_date,
            status="released",
            is_current=self._fresh,
            type="module",
            owner_id=self.owner.org_id,
            row_guid=self._concept(
                "Release", stable_uuid("Release", self._release_code)
            ),
        )
        self._session.add(release)
        self._session.flush()
        self.outcome.bump("Release")
        return release

    def _next_release_id(self) -> int:
        prefix = int(self.owner.id_prefix or self.owner.org_id)
        base = prefix * 10**_RELEASE_PREFIX_WIDTH
        upper = base + 10**_RELEASE_PREFIX_WIDTH
        current = (
            self._session.query(func.max(Release.release_id))
            .filter(Release.release_id >= base, Release.release_id < upper)
            .scalar()
        )
        return int(current) + 1 if current is not None else base + 1

    def _ensure_special_category(
        self,
        code: str,
        name: str,
        canonical_guid: str,
        canonical_id: int,
        *,
        is_enumerated: bool,
    ) -> Category:
        category = (
            self._session.query(Category)
            .filter(Category.code == code)
            .one_or_none()
        )
        if category is not None:
            self.outcome.bump("Category", reused=True)
            return category

        if self._session.get(Concept, canonical_guid) is None:
            self._session.add(
                Concept(
                    concept_guid=canonical_guid,
                    class_id=self._class_ids["Category"],
                    owner_id=self.owner.org_id,
                )
            )
        category = Category(
            category_id=canonical_id,
            code=code,
            name=name,
            is_enumerated=is_enumerated,
            is_active=True,
            is_external_ref_data=False,
            row_guid=canonical_guid,
            created_release_id=self.release.release_id,
            owner_id=self.owner.org_id,
        )
        self._session.add(category)
        self._session.flush()
        self.outcome.bump("Category")
        return category

    # -------------------------------------------------------------- #
    # Concept / label plumbing
    # -------------------------------------------------------------- #

    def _concept(
        self,
        class_name: str,
        guid: str,
        *,
        owner_id: Optional[int] = None,
    ) -> str:
        """Get-or-create the Concept row behind *guid*."""
        if self._session.get(Concept, guid) is None:
            self._session.add(
                Concept(
                    concept_guid=guid,
                    class_id=self._class_ids[class_name],
                    owner_id=(
                        owner_id
                        if owner_id is not None
                        else self.owner.org_id
                    ),
                )
            )
        return guid

    @staticmethod
    def pick_name(
        labels: Tuple[XLabel, ...],
        fallback: str,
        *,
        lang: str = "en",
    ) -> str:
        """Return the standard label in *lang*, or a fallback.

        Args:
            labels: Candidate labels.
            fallback: Value returned when no label matches.
            lang: Preferred language.

        Returns:
            The best display name.
        """
        for label in labels:
            if label.role == "standard" and label.lang == lang:
                return label.text
        for label in labels:
            if label.role == "standard":
                return label.text
        return fallback

    def _translate(
        self,
        guid: str,
        class_name: str,
        attr_name: str,
        labels: Tuple[XLabel, ...],
        *,
        primary_lang: str = "en",
    ) -> None:
        """Store non-primary-language labels as Translation rows."""
        attribute_id = self._attr_ids.get((class_name, attr_name))
        if attribute_id is None:
            return
        for label in labels:
            if label.role != "standard" or label.lang == primary_lang:
                continue
            language_code = self._languages.get(label.lang)
            if language_code is None:
                self.outcome.warnings.append(
                    f"Skipping label in unsupported language "
                    f"'{label.lang}' for {class_name} {guid}."
                )
                continue
            key = (guid, attribute_id, self.owner.org_id, language_code)
            if self._session.get(Translation, key) is not None:
                continue
            self._session.add(
                Translation(
                    concept_guid=guid,
                    attribute_id=attribute_id,
                    translator_id=self.owner.org_id,
                    language_code=language_code,
                    translation=label.text,
                    row_guid=stable_uuid("Translation", *key),
                )
            )
            self.outcome.bump("Translation")

    # -------------------------------------------------------------- #
    # Type helpers
    # -------------------------------------------------------------- #

    def _data_type_code(self, type_qname: Optional[str]) -> str:
        """Map an XSD/XBRL item type qname to a DPM data-type code."""
        if not type_qname:
            return "s"
        local = type_qname.rsplit(":", 1)[-1].lower()
        local = local.removesuffix("itemtype")
        code = _DATA_TYPE_BY_LOCAL.get(local)
        if code is None:
            self.outcome.warnings.append(
                f"Unknown XBRL type '{type_qname}'; defaulting to string."
            )
            return "s"
        return code

    def _period_type(self, xbrl_period_type: str) -> str:
        mapped = _PERIOD_TYPE_MAP.get(xbrl_period_type)
        if mapped is None:
            self.outcome.warnings.append(
                f"Unknown period type '{xbrl_period_type}'; "
                "defaulting to stock."
            )
            return "stock"
        return mapped

    # -------------------------------------------------------------- #
    # Code synthesis
    # -------------------------------------------------------------- #

    def _synth_category_code(self, qname: str) -> str:
        """Derive a short category code from a domain qname."""
        local = qname.rsplit(":", 1)[-1]
        local = re.sub(r"(Domain|Dimension)$", "", local)
        caps = "".join(c for c in local if c.isupper())
        code = caps[:4] if len(caps) >= 2 else local[:4].upper()
        base, counter = code, 1
        while (
            code in self._used_category_codes
            and self._used_category_codes[code] != qname
        ) or self._category_code_taken(code, qname):
            counter += 1
            code = f"{base}{counter}"
        self._used_category_codes[code] = qname
        return code

    def _category_code_taken(self, code: str, qname: str) -> bool:
        existing = (
            self._session.query(Category)
            .filter(Category.code == code)
            .one_or_none()
        )
        if existing is None:
            return False
        return existing.row_guid != self._category_guid(qname)

    def _category_guid(self, qname: str) -> str:
        return stable_uuid("Category", self._framework_code, qname)

    def _next_pr_code(self, data_type_code: str) -> str:
        """Allocate the next global ``<letter>i<seq>`` property code."""
        if self._pr_seq is None:
            self._pr_seq = self._max_pr_seq()
        self._pr_seq += 1
        letter = data_type_code[0]
        return f"{letter}i{self._pr_seq}"

    def _max_pr_seq(self) -> int:
        assert self._cat_pr is not None  # noqa: S101 - set in prepare()
        codes = (
            self._session.query(ItemCategory.code)
            .filter(ItemCategory.category_id == self._cat_pr.category_id)
            .all()
        )
        best = 0
        for (code,) in codes:
            match = re.fullmatch(r"[a-z]+i(\d+)", code or "")
            if match:
                best = max(best, int(match.group(1)))
        return best

    # -------------------------------------------------------------- #
    # Dictionary mapping
    # -------------------------------------------------------------- #

    def map_dictionary(self, model: TaxonomyModel) -> None:
        """Map domains, members, dimensions, metrics and hierarchies.

        Args:
            model: The taxonomy content to map.
        """
        self._framework_code = model.framework_code
        self.outcome.warnings.extend(model.warnings)
        for domain in model.domains:
            self._map_domain(domain)
        for dimension in model.dimensions:
            self._map_dimension(dimension)
        for metric in model.metrics:
            self._map_metric(metric)
        for hierarchy in model.hierarchies:
            self._map_hierarchy(hierarchy)
        self._session.flush()

    def _map_domain(self, domain: XDomain) -> None:
        if domain.is_typed:
            self._typed_type_by_domain[domain.qname] = (
                domain.typed_data_type
            )
            return
        category = self._get_or_create_category(domain)
        self._category_by_domain[domain.qname] = category
        for member in domain.members:
            self._map_member(category, member)

    def _get_or_create_category(self, domain: XDomain) -> Category:
        guid = self._category_guid(domain.qname)
        existing = (
            self._session.query(Category)
            .filter(Category.row_guid == guid)
            .one_or_none()
        )
        if existing is not None:
            self.outcome.bump("Category", reused=True)
            return existing

        code = domain.code or self._synth_category_code(domain.qname)
        category = Category(
            category_id=self._ids.next_id(Category, "category_id"),
            code=code[:20],
            name=self.pick_name(domain.labels, domain.name)[:50],
            is_enumerated=True,
            is_active=True,
            is_external_ref_data=False,
            row_guid=self._concept("Category", guid),
            created_release_id=self.release.release_id,
            owner_id=self.owner.org_id,
        )
        self._session.add(category)
        self._session.flush()
        self._translate(guid, "Category", "Name", domain.labels)
        self.outcome.bump("Category")
        return category

    def _map_member(self, category: Category, member: XMember) -> None:
        existing = self._find_item_by_signature(member.qname)
        if existing is not None:
            self._item_by_qname[member.qname] = existing
            self.outcome.bump("Item", reused=True)
            return

        guid = stable_uuid("Item", self._framework_code, member.qname)
        item = Item(
            item_id=self._ids.next_id(Item, "item_id"),
            name=self.pick_name(member.labels, member.name)[:500],
            is_property=False,
            is_active=True,
            row_guid=self._concept("Item", guid),
            owner_id=self.owner.org_id,
        )
        self._session.add(item)
        code = member.code or self._next_member_code(category)
        self._session.add(
            ItemCategory(
                item_id=item.item_id,
                start_release_id=self.release.release_id,
                category_id=category.category_id,
                code=code[:20],
                is_default_item=member.is_default,
                signature=member.qname[:255],
                row_guid=stable_uuid(
                    "ItemCategory", self._framework_code, member.qname
                ),
            )
        )
        self._item_by_qname[member.qname] = item
        self._translate(guid, "Item", "Name", member.labels)
        self.outcome.bump("Item")

    def _next_member_code(self, category: Category) -> str:
        cat_id = category.category_id
        if cat_id not in self._member_seq:
            count = (
                self._session.query(func.count(ItemCategory.item_id))
                .filter(ItemCategory.category_id == cat_id)
                .scalar()
            )
            self._member_seq[cat_id] = int(count or 0)
        self._member_seq[cat_id] += 1
        return f"x{self._member_seq[cat_id]}"

    def _map_dimension(self, dimension: XDimension) -> None:
        if dimension.qname in self._property_by_qname:
            return
        existing = self._find_property_by_guid_or_warn(dimension.qname)
        if existing is not None:
            self._property_by_qname[dimension.qname] = existing
            self.outcome.bump("Property", reused=True)
            return

        if dimension.is_typed:
            typed_type = None
            if dimension.domain_qname is not None:
                typed_type = self._typed_type_by_domain.get(
                    dimension.domain_qname
                )
            data_type = self._data_type_code(typed_type)
            category = self._cat_na
        elif dimension.is_open or dimension.domain_qname is None:
            data_type = "s"
            category = self._cat_na
        else:
            data_type = "e"
            category = self._category_by_domain.get(dimension.domain_qname)
            if category is None:
                self.outcome.warnings.append(
                    f"Dimension '{dimension.qname}' references unknown "
                    f"domain '{dimension.domain_qname}'; linking to _NA."
                )
                category = self._cat_na
        self._create_property(
            qname=dimension.qname,
            name=self.pick_name(dimension.labels, dimension.name),
            labels=dimension.labels,
            is_metric=False,
            data_type_code=data_type,
            period_type="stock",
            category=category,
        )

    def _map_metric(self, metric: XMetric) -> None:
        if metric.qname in self._property_by_qname:
            return
        existing = self._find_property_by_guid_or_warn(metric.qname)
        if existing is not None:
            self._property_by_qname[metric.qname] = existing
            self.outcome.bump("Property", reused=True)
            return
        self._create_property(
            qname=metric.qname,
            name=self.pick_name(metric.labels, metric.name),
            labels=metric.labels,
            is_metric=True,
            data_type_code=self._data_type_code(metric.xbrl_type),
            period_type=self._period_type(metric.period_type),
            category=self._cat_na,
        )

    def _create_property(
        self,
        *,
        qname: str,
        name: str,
        labels: Tuple[XLabel, ...],
        is_metric: bool,
        data_type_code: str,
        period_type: str,
        category: Optional[Category],
    ) -> None:
        item_guid = stable_uuid("Item", self._framework_code, qname)
        item = Item(
            item_id=self._ids.next_id(Item, "item_id"),
            name=name[:500],
            is_property=True,
            is_active=True,
            row_guid=self._concept("Item", item_guid),
            owner_id=self.owner.org_id,
        )
        self._session.add(item)
        assert self._cat_pr is not None  # noqa: S101 - set in prepare()
        pr_code = self._next_pr_code(data_type_code)
        self._session.add(
            ItemCategory(
                item_id=item.item_id,
                start_release_id=self.release.release_id,
                category_id=self._cat_pr.category_id,
                code=pr_code,
                is_default_item=False,
                signature=pr_code,
                row_guid=stable_uuid(
                    "ItemCategory", self._framework_code, qname, "_PR"
                ),
            )
        )
        prop_guid = stable_uuid("Property", self._framework_code, qname)
        prop = Property(
            property_id=item.item_id,
            is_composite=False,
            is_metric=is_metric,
            data_type_id=self._data_types[data_type_code],
            period_type=period_type,
            row_guid=self._concept("Property", prop_guid),
            owner_id=self.owner.org_id,
        )
        self._session.add(prop)
        if category is not None:
            self._session.add(
                PropertyCategory(
                    property_id=item.item_id,
                    start_release_id=self.release.release_id,
                    category_id=category.category_id,
                    row_guid=stable_uuid(
                        "PropertyCategory", self._framework_code, qname
                    ),
                )
            )
        self._item_by_qname[qname] = item
        self._property_by_qname[qname] = prop
        self._translate(item_guid, "Item", "Name", labels)
        self.outcome.bump("Item")
        self.outcome.bump("Property")

    def _map_hierarchy(self, hierarchy: XHierarchy) -> None:
        category = self._category_by_domain.get(hierarchy.domain_qname)
        if category is None:
            self.outcome.warnings.append(
                f"Hierarchy '{hierarchy.role_uri}' references unknown "
                f"domain '{hierarchy.domain_qname}'; skipped."
            )
            return
        guid = stable_uuid(
            "SubCategory",
            self._framework_code,
            hierarchy.role_uri,
            hierarchy.domain_qname,
        )
        existing = (
            self._session.query(SubCategory)
            .filter(SubCategory.row_guid == guid)
            .one_or_none()
        )
        if existing is not None:
            self.outcome.bump("SubCategory", reused=True)
            return

        code = hierarchy.code or self._next_subcategory_code(category)
        subcategory = SubCategory(
            subcategory_id=self._ids.next_id(
                SubCategory, "subcategory_id"
            ),
            category_id=category.category_id,
            code=code[:30],
            name=hierarchy.name[:500],
            row_guid=self._concept("SubCategory", guid),
            owner_id=self.owner.org_id,
        )
        self._session.add(subcategory)
        version = SubCategoryVersion(
            subcategory_vid=self._ids.next_id(
                SubCategoryVersion, "subcategory_vid"
            ),
            subcategory_id=subcategory.subcategory_id,
            start_release_id=self.release.release_id,
            row_guid=self._concept(
                "SubCategory",
                stable_uuid(
                    "SubCategoryVersion",
                    self._framework_code,
                    hierarchy.role_uri,
                    hierarchy.domain_qname,
                    self._release_code,
                ),
            ),
        )
        self._session.add(version)
        self._map_hierarchy_nodes(hierarchy, version)
        self.outcome.bump("SubCategory")

    def _map_hierarchy_nodes(
        self,
        hierarchy: XHierarchy,
        version: SubCategoryVersion,
    ) -> None:
        placed: set[int] = set()
        for node in hierarchy.nodes:
            item = self._item_by_qname.get(node.member_qname)
            if item is None:
                self.outcome.warnings.append(
                    f"Hierarchy '{hierarchy.role_uri}' places unknown "
                    f"member '{node.member_qname}'; node skipped."
                )
                continue
            if item.item_id in placed:
                self.outcome.warnings.append(
                    f"Hierarchy '{hierarchy.role_uri}' places member "
                    f"'{node.member_qname}' more than once; extra "
                    "placement skipped."
                )
                continue
            placed.add(item.item_id)
            parent: Optional[Item] = None
            if node.parent_qname is not None:
                parent = self._item_by_qname.get(node.parent_qname)
            self._session.add(
                SubCategoryItem(
                    item_id=item.item_id,
                    subcategory_vid=version.subcategory_vid,
                    order=node.order,
                    parent_item_id=(
                        parent.item_id if parent is not None else None
                    ),
                    row_guid=self._concept(
                        "SubCategoryItem",
                        stable_uuid(
                            "SubCategoryItem",
                            self._framework_code,
                            hierarchy.role_uri,
                            hierarchy.domain_qname,
                            node.member_qname,
                        ),
                    ),
                )
            )
            self.outcome.bump("SubCategoryItem")

    def _next_subcategory_code(self, category: Category) -> str:
        count = (
            self._session.query(func.count(SubCategory.subcategory_id))
            .filter(SubCategory.category_id == category.category_id)
            .scalar()
        )
        return f"{category.code}{int(count or 0) + 1}"

    # -------------------------------------------------------------- #
    # Lookups
    # -------------------------------------------------------------- #

    def _find_item_by_signature(self, qname: str) -> Optional[Item]:
        """Find an existing member item by its qname signature."""
        row = (
            self._session.query(Item)
            .join(ItemCategory, ItemCategory.item_id == Item.item_id)
            .filter(ItemCategory.signature == qname)
            .order_by(ItemCategory.start_release_id.desc())
            .first()
        )
        return row

    def _find_property_by_guid_or_warn(
        self, qname: str
    ) -> Optional[Property]:
        """Find a previously imported property by deterministic GUID."""
        guid = stable_uuid("Property", self._framework_code, qname)
        return (
            self._session.query(Property)
            .filter(Property.row_guid == guid)
            .one_or_none()
        )

    # -------------------------------------------------------------- #
    # Shadow rows for unresolvable qnames
    # -------------------------------------------------------------- #

    def _shadow_property(
        self, qname: str, *, is_metric: bool
    ) -> Property:
        """Create an owned stand-in for an unresolvable property.

        Tables can reference concepts from taxonomies the importer
        cannot read (TREP references the retired EBA DPM 1.x
        dictionary). When no existing row matches by signature, an
        owned placeholder keeps the table structure complete; a
        later import into a database that contains the real
        dictionary reuses it by signature instead.
        """
        existing = self._find_property_by_signature(qname)
        if existing is not None:
            self._property_by_qname[qname] = existing
            self.outcome.bump("Property", reused=True)
            return existing
        self._warn_shadow(qname)
        self._create_property(
            qname=qname,
            name=qname,
            labels=(),
            is_metric=is_metric,
            data_type_code="s",
            period_type="stock",
            category=self._cat_na,
        )
        return self._property_by_qname[qname]

    def _find_property_by_signature(
        self, qname: str
    ) -> Optional[Property]:
        """Find an existing property whose item matches *qname*."""
        item = self._find_item_by_signature(qname)
        if item is None:
            return None
        return self._session.get(Property, item.item_id)

    def _shadow_member(self, qname: str) -> Item:
        """Create an owned stand-in for an unresolvable member."""
        self._warn_shadow(qname)
        assert self._cat_na is not None  # noqa: S101 - set in prepare()
        self._map_member(
            self._cat_na,
            XMember(qname=qname, name=qname),
        )
        return self._item_by_qname[qname]

    def _warn_shadow(self, qname: str) -> None:
        if qname in self._shadowed_qnames:
            return
        self._shadowed_qnames.add(qname)
        self.outcome.warnings.append(
            f"Concept '{qname}' is not defined in this taxonomy and "
            "no existing row matches its signature; created an "
            f"owned shadow row (owner {self._owner_acronym})."
        )

    # -------------------------------------------------------------- #
    # Full pipeline
    # -------------------------------------------------------------- #

    def map_model(self, model: TaxonomyModel) -> MappingOutcome:
        """Map *model* onto the database in full.

        Args:
            model: The taxonomy content to map.

        Returns:
            The tally of created and reused rows.
        """
        self.prepare()
        self.map_dictionary(model)
        self.map_rendering(model)
        return self.outcome

    # -------------------------------------------------------------- #
    # Rendering mapping (tables, cells, modules)
    # -------------------------------------------------------------- #

    def map_rendering(self, model: TaxonomyModel) -> None:
        """Map tables, datapoints, framework and modules.

        Args:
            model: The taxonomy content to map. The dictionary must
                have been mapped first.
        """
        self._framework_code = model.framework_code
        framework = self._ensure_framework(model)
        for table in model.tables:
            self._map_table(table)
        for module in model.modules:
            self._map_module(framework, module)
        self._session.flush()

    def _ensure_framework(self, model: TaxonomyModel) -> Framework:
        existing = (
            self._session.query(Framework)
            .filter(Framework.code == model.framework_code)
            .one_or_none()
        )
        if existing is not None:
            self.outcome.bump("Framework", reused=True)
            return existing
        guid = stable_uuid("Framework", model.framework_code)
        framework = Framework(
            framework_id=self._ids.next_id(Framework, "framework_id"),
            code=model.framework_code[:255],
            name=model.framework_name[:255],
            row_guid=self._concept("Framework", guid),
            owner_id=self.owner.org_id,
        )
        self._session.add(framework)
        self._session.flush()
        self.outcome.bump("Framework")
        return framework

    # ----------------------------- tables ------------------------- #

    def _map_table(self, xtable: XTable) -> None:
        entity = self._ensure_table_entity(xtable)
        open_version = self._find_open_table_version(entity)
        if open_version is not None:
            if open_version.start_release_id == self.release.release_id:
                self._tablev_by_code[xtable.code] = open_version
                self.outcome.bump("TableVersion", reused=True)
                return
            open_version.end_release_id = self.release.release_id

        tv_guid = stable_uuid(
            "TableVersion",
            self._framework_code,
            xtable.code,
            self._release_code,
        )
        version = TableVersion(
            table_vid=self._ids.next_id(TableVersion, "table_vid"),
            code=xtable.code[:30],
            name=xtable.name[:255],
            description=(
                xtable.description[:500]
                if xtable.description is not None
                else None
            ),
            table_id=entity.table_id,
            start_release_id=self.release.release_id,
            row_guid=self._concept("TableVersion", tv_guid),
        )
        self._session.add(version)
        self._translate(tv_guid, "TableVersion", "Name", xtable.labels)
        self._tablev_by_code[xtable.code] = version

        headers: Dict[str, Tuple[Header, HeaderVersion, str]] = {}
        for axis in xtable.axes:
            self._map_axis(entity, version, xtable.code, axis, headers)
        for cell in xtable.cells:
            self._map_cell(entity, version, xtable, cell, headers)
        self.outcome.bump("TableVersion")

    def _ensure_table_entity(self, xtable: XTable) -> Table:
        guid = stable_uuid("Table", self._framework_code, xtable.code)
        existing = (
            self._session.query(Table)
            .filter(Table.row_guid == guid)
            .one_or_none()
        )
        if existing is not None:
            self.outcome.bump("Table", reused=True)
            return existing

        def _open(direction: str) -> bool:
            axis = xtable.axis(direction)
            return axis.is_open if axis is not None else False

        table = Table(
            table_id=self._ids.next_id(Table, "table_id"),
            is_abstract=False,
            has_open_columns=_open(DIRECTION_X),
            has_open_rows=_open(DIRECTION_Y),
            has_open_sheets=_open(DIRECTION_Z),
            is_normalised=False,
            is_flat=False,
            row_guid=self._concept("Table", guid),
            owner_id=self.owner.org_id,
        )
        self._session.add(table)
        self._session.flush()
        self.outcome.bump("Table")
        return table

    def _find_open_table_version(
        self, entity: Table
    ) -> Optional[TableVersion]:
        return (
            self._session.query(TableVersion)
            .filter(
                TableVersion.table_id == entity.table_id,
                TableVersion.end_release_id.is_(None),
            )
            .order_by(TableVersion.start_release_id.desc())
            .first()
        )

    # ----------------------------- headers ------------------------ #

    def _map_axis(
        self,
        entity: Table,
        version: TableVersion,
        table_code: str,
        axis: XAxis,
        headers: Dict[str, Tuple[Header, HeaderVersion, str]],
    ) -> None:
        prefix = {
            DIRECTION_X: "c",
            DIRECTION_Y: "r",
            DIRECTION_Z: "s",
        }[axis.direction]
        for seq, node in enumerate(axis.nodes, start=1):
            code = node.code or f"{seq * 10:04d}"
            headers[node.node_id] = self._add_header(
                entity,
                version,
                table_code,
                axis,
                node,
                code=code,
                parent=headers.get(node.parent_id or ""),
            )
        for pos, dim_qname in enumerate(axis.open_dimension_qnames):
            self._add_key_header(
                entity, version, table_code, axis, dim_qname, prefix, pos
            )

    def _add_header(
        self,
        entity: Table,
        version: TableVersion,
        table_code: str,
        axis: XAxis,
        node: XHeaderNode,
        *,
        code: str,
        parent: Optional[Tuple[Header, HeaderVersion, str]],
    ) -> Tuple[Header, HeaderVersion, str]:
        guid_key = (
            self._framework_code,
            table_code,
            self._release_code,
            node.node_id,
        )
        header = Header(
            header_id=self._ids.next_id(Header, "header_id"),
            table_id=entity.table_id,
            direction=axis.direction,
            is_key=False,
            row_guid=self._concept(
                "Header", stable_uuid("Header", *guid_key)
            ),
            owner_id=self.owner.org_id,
        )
        self._session.add(header)

        metric_prop = None
        if node.metric_qname is not None:
            metric_prop = self._property_by_qname.get(node.metric_qname)
            if metric_prop is None:
                metric_prop = self._shadow_property(
                    node.metric_qname, is_metric=True
                )
        context = self._context_for(node.dim_members, table_code)
        hv_guid = stable_uuid("HeaderVersion", *guid_key)
        header_version = HeaderVersion(
            header_vid=self._ids.next_id(HeaderVersion, "header_vid"),
            header_id=header.header_id,
            code=code[:10],
            label=node.label[:500],
            property_id=(
                metric_prop.property_id
                if metric_prop is not None
                else None
            ),
            context_id=(
                context.context_id if context is not None else None
            ),
            start_release_id=self.release.release_id,
            row_guid=self._concept("HeaderVersion", hv_guid),
        )
        self._session.add(header_version)
        self._translate(hv_guid, "HeaderVersion", "Label", node.labels)
        self._session.add(
            TableVersionHeader(
                table_vid=version.table_vid,
                header_id=header.header_id,
                header_vid=header_version.header_vid,
                parent_header_id=(
                    parent[0].header_id if parent is not None else None
                ),
                order=node.order,
                is_abstract=node.is_abstract,
                row_guid=stable_uuid("TableVersionHeader", *guid_key),
            )
        )
        self.outcome.bump("Header")
        return header, header_version, code

    def _add_key_header(
        self,
        entity: Table,
        version: TableVersion,
        table_code: str,
        axis: XAxis,
        dim_qname: str,
        prefix: str,
        pos: int,
    ) -> None:
        prop = self._property_by_qname.get(dim_qname)
        if prop is None:
            self.outcome.warnings.append(
                f"Table '{table_code}' opens unknown dimension "
                f"'{dim_qname}'; key header skipped."
            )
            return
        guid_key = (
            self._framework_code,
            table_code,
            self._release_code,
            f"key:{dim_qname}",
        )
        header = Header(
            header_id=self._ids.next_id(Header, "header_id"),
            table_id=entity.table_id,
            direction=axis.direction,
            is_key=True,
            row_guid=self._concept(
                "Header", stable_uuid("Header", *guid_key)
            ),
            owner_id=self.owner.org_id,
        )
        self._session.add(header)
        item = self._item_by_qname.get(dim_qname)
        header_version = HeaderVersion(
            header_vid=self._ids.next_id(HeaderVersion, "header_vid"),
            header_id=header.header_id,
            code=f"{prefix}K{pos + 1}"[:10],
            label=(
                item.name if item is not None and item.name else dim_qname
            )[:500],
            property_id=prop.property_id,
            start_release_id=self.release.release_id,
            row_guid=self._concept(
                "HeaderVersion",
                stable_uuid("HeaderVersion", *guid_key),
            ),
        )
        self._session.add(header_version)
        self._session.add(
            TableVersionHeader(
                table_vid=version.table_vid,
                header_id=header.header_id,
                header_vid=header_version.header_vid,
                order=1000 + pos,
                is_abstract=False,
                row_guid=stable_uuid("TableVersionHeader", *guid_key),
            )
        )
        self.outcome.bump("Header")

    # ----------------------------- cells -------------------------- #

    def _map_cell(
        self,
        entity: Table,
        version: TableVersion,
        xtable: XTable,
        xcell: XCell,
        headers: Dict[str, Tuple[Header, HeaderVersion, str]],
    ) -> None:
        row = headers.get(xcell.row_node_id)
        column = headers.get(xcell.column_node_id)
        sheet = (
            headers.get(xcell.sheet_node_id)
            if xcell.sheet_node_id is not None
            else None
        )
        if row is None or column is None:
            self.outcome.warnings.append(
                f"Cell of table '{xtable.code}' references unknown "
                f"headers ({xcell.row_node_id}, "
                f"{xcell.column_node_id}); skipped."
            )
            return
        variable_version = (
            None
            if self._defer_variables
            else self._variable_for(xcell, xtable.code)
        )
        guid_key = (
            self._framework_code,
            xtable.code,
            self._release_code,
            xcell.row_node_id,
            xcell.column_node_id,
            xcell.sheet_node_id,
        )
        cell = Cell(
            cell_id=self._ids.next_id(Cell, "cell_id"),
            table_id=entity.table_id,
            column_id=column[0].header_id,
            row_id=row[0].header_id,
            sheet_id=sheet[0].header_id if sheet is not None else None,
            row_guid=self._concept(
                "Cell", stable_uuid("Cell", *guid_key)
            ),
            owner_id=self.owner.org_id,
        )
        self._session.add(cell)
        code_parts = [xtable.code, f"r{row[2]}", f"c{column[2]}"]
        if sheet is not None:
            code_parts.append(f"s{sheet[2]}")
        self._session.add(
            TableVersionCell(
                table_vid=version.table_vid,
                cell_id=cell.cell_id,
                cell_code=("{" + ", ".join(code_parts) + "}")[:100],
                is_nullable=True,
                is_excluded=False,
                is_void=False,
                variable_vid=(
                    variable_version.variable_vid
                    if variable_version is not None
                    else None
                ),
                row_guid=stable_uuid("TableVersionCell", *guid_key),
            )
        )
        self.outcome.bump("Cell")

    def _variable_for(
        self, xcell: XCell, table_code: str
    ) -> VariableVersion:
        metric = self._property_by_qname.get(xcell.metric_qname)
        if metric is None:
            metric = self._shadow_property(
                xcell.metric_qname, is_metric=True
            )
        context = self._context_for(xcell.dim_members, table_code)
        context_id = (
            context.context_id if context is not None else None
        )
        key = (metric.property_id, context_id)
        cached = self._varv_by_key.get(key)
        if cached is not None:
            return cached

        existing = (
            self._session.query(VariableVersion)
            .filter(
                VariableVersion.property_id == metric.property_id,
                VariableVersion.context_id == context_id,
                VariableVersion.end_release_id.is_(None),
            )
            .first()
        )
        if existing is not None:
            self._varv_by_key[key] = existing
            self.outcome.bump("Variable", reused=True)
            return existing

        signature = context.signature if context is not None else ""
        var_guid = stable_uuid(
            "Variable", xcell.metric_qname, signature
        )
        variable = Variable(
            variable_id=self._ids.next_id(Variable, "variable_id"),
            type="fact",
            row_guid=self._concept("Variable", var_guid),
            owner_id=self.owner.org_id,
        )
        self._session.add(variable)
        variable_version = VariableVersion(
            variable_vid=self._ids.next_id(
                VariableVersion, "variable_vid"
            ),
            variable_id=variable.variable_id,
            property_id=metric.property_id,
            context_id=context_id,
            is_multi_valued=False,
            start_release_id=self.release.release_id,
            row_guid=self._concept(
                "VariableVersion",
                stable_uuid(
                    "VariableVersion",
                    xcell.metric_qname,
                    signature,
                    self._release_code,
                ),
            ),
        )
        self._session.add(variable_version)
        self._varv_by_key[key] = variable_version
        self.outcome.bump("Variable")
        return variable_version

    def _context_for(
        self,
        dim_members: Tuple[Tuple[str, str], ...],
        table_code: str,
    ) -> Optional[Context]:
        pairs = self._resolve_context_pairs(dim_members, table_code)
        if not pairs:
            return None
        signature = "".join(
            f"{pid}_{iid}#" for pid, iid in sorted(pairs)
        )
        cached = self._context_by_signature.get(signature)
        if cached is not None:
            return cached

        existing = (
            self._session.query(Context)
            .filter(Context.signature == signature)
            .first()
        )
        if existing is not None:
            self._context_by_signature[signature] = existing
            self.outcome.bump("Context", reused=True)
            return existing

        context = Context(
            context_id=self._ids.next_id(Context, "context_id"),
            signature=signature[:2000],
            row_guid=self._concept(
                "Context", stable_uuid("Context", signature)
            ),
            owner_id=self.owner.org_id,
        )
        self._session.add(context)
        for pid, iid in pairs:
            self._session.add(
                ContextComposition(
                    context_id=context.context_id,
                    property_id=pid,
                    item_id=iid,
                    row_guid=stable_uuid(
                        "ContextComposition", signature, pid, iid
                    ),
                )
            )
        self._context_by_signature[signature] = context
        self.outcome.bump("Context")
        return context

    def _resolve_context_pairs(
        self,
        dim_members: Tuple[Tuple[str, str], ...],
        table_code: str,
    ) -> List[Tuple[int, int]]:
        pairs: List[Tuple[int, int]] = []
        for dim_qname, member_qname in dim_members:
            prop = self._property_by_qname.get(dim_qname)
            if prop is None:
                prop = self._shadow_property(dim_qname, is_metric=False)
            item = self._item_by_qname.get(member_qname)
            if item is None:
                found = self._find_item_by_signature(member_qname)
                if found is not None:
                    self._item_by_qname[member_qname] = found
                    self.outcome.bump("Item", reused=True)
                    item = found
                else:
                    item = self._shadow_member(member_qname)
            pairs.append((prop.property_id, item.item_id))
        return pairs

    # ----------------------------- modules ------------------------ #

    def _map_module(
        self, framework: Framework, xmodule: XModule
    ) -> None:
        module = self._ensure_module_entity(framework, xmodule)
        open_version = self._find_open_module_version(module)
        if open_version is not None:
            start = open_version.start_release_id
            if start == self.release.release_id:
                self.outcome.bump("ModuleVersion", reused=True)
                return
            open_version.end_release_id = self.release.release_id

        mv_guid = stable_uuid(
            "ModuleVersion",
            self._framework_code,
            xmodule.code,
            self._release_code,
        )
        version = ModuleVersion(
            module_vid=self._ids.next_id(ModuleVersion, "module_vid"),
            module_id=module.module_id,
            start_release_id=self.release.release_id,
            code=xmodule.code[:30],
            name=xmodule.name[:100],
            description=(
                xmodule.entry_point[:255]
                if xmodule.entry_point
                else None
            ),
            version_number=(
                xmodule.version[:20]
                if xmodule.version is not None
                else None
            ),
            from_reference_date=xmodule.from_date,
            row_guid=self._concept("ModuleVersion", mv_guid),
            is_reported=True,
            is_calculated=False,
        )
        self._session.add(version)
        self._translate(mv_guid, "ModuleVersion", "Name", xmodule.labels)
        self._map_module_composition(version, xmodule)
        self.outcome.bump("ModuleVersion")

    def _ensure_module_entity(
        self, framework: Framework, xmodule: XModule
    ) -> Module:
        guid = stable_uuid(
            "Module", self._framework_code, xmodule.code
        )
        existing = (
            self._session.query(Module)
            .filter(Module.row_guid == guid)
            .one_or_none()
        )
        if existing is not None:
            self.outcome.bump("Module", reused=True)
            return existing
        module = Module(
            module_id=self._ids.next_id(Module, "module_id"),
            framework_id=framework.framework_id,
            row_guid=self._concept("Module", guid),
            is_document_module=False,
            owner_id=self.owner.org_id,
        )
        self._session.add(module)
        self._session.flush()
        self.outcome.bump("Module")
        return module

    def _find_open_module_version(
        self, module: Module
    ) -> Optional[ModuleVersion]:
        return (
            self._session.query(ModuleVersion)
            .filter(
                ModuleVersion.module_id == module.module_id,
                ModuleVersion.end_release_id.is_(None),
            )
            .order_by(ModuleVersion.start_release_id.desc())
            .first()
        )

    def _map_module_composition(
        self, version: ModuleVersion, xmodule: XModule
    ) -> None:
        for order, table_code in enumerate(xmodule.table_codes, start=1):
            table_version = self._tablev_by_code.get(table_code)
            if table_version is None:
                self.outcome.warnings.append(
                    f"Module '{xmodule.code}' lists unknown table "
                    f"'{table_code}'; composition entry skipped."
                )
                continue
            self._session.add(
                ModuleVersionComposition(
                    module_vid=version.module_vid,
                    table_id=table_version.table_id,
                    table_vid=table_version.table_vid,
                    order=order,
                    row_guid=stable_uuid(
                        "ModuleVersionComposition",
                        self._framework_code,
                        xmodule.code,
                        table_code,
                        self._release_code,
                    ),
                )
            )
