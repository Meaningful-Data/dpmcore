"""Neutral intermediate model for imported XBRL taxonomies.

The taxonomy readers (:mod:`dpmcore.loaders.xbrl.reader_eurofiling2006`
and :mod:`dpmcore.loaders.xbrl.reader_dpm1`) reduce an Arelle
``ModelXbrl`` to the frozen dataclasses defined here; the mapper
(:mod:`dpmcore.loaders.xbrl.mapper`) turns them into ORM rows. Nothing
in this module imports Arelle, so the mapping core stays fully
unit-testable without an XBRL processor installed.

Qnames are represented as prefixed strings (``"eba_met:mi53"``); they
are treated as opaque identity keys and never re-resolved.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date
from typing import Hashable, Iterable, Optional, Tuple, TypeVar

_K = TypeVar("_K", bound=Hashable)
_V = TypeVar("_V")

ARCHITECTURE_AUTO = "auto"
ARCHITECTURE_EUROFILING_2006 = "eurofiling2006"
ARCHITECTURE_DPM1 = "dpm1"

#: Architectures a reader exists for (``auto`` resolves to one of
#: these before a reader is chosen).
SUPPORTED_ARCHITECTURES = (
    ARCHITECTURE_EUROFILING_2006,
    ARCHITECTURE_DPM1,
)

#: Axis direction codes as stored in ``Header.Direction``.
DIRECTION_X = "X"
DIRECTION_Y = "Y"
DIRECTION_Z = "Z"


class XbrlImportError(Exception):
    """Raised when an XBRL taxonomy cannot be imported."""


@dataclass(frozen=True)
class XLabel:
    """A single label resource attached to a taxonomy concept.

    Attributes:
        lang: Two-letter language code (``en``, ``fr``, ``nl``).
        text: Label text.
        role: Short label-role discriminator; ``standard`` for the
            standard label role, ``code`` for the Eurofiling
            rc-code/generic code role.
    """

    lang: str
    text: str
    role: str = "standard"


@dataclass(frozen=True)
class XMember:
    """A domain member (enumerated value).

    Attributes:
        qname: Prefixed qname of the member element.
        name: Human-readable name (default-language label).
        code: Member code when the taxonomy provides one (dpm1
            element names such as ``x1``); ``None`` lets the mapper
            synthesise a code.
        labels: All label resources for the member.
        is_default: Whether this member is the dimension default.
    """

    qname: str
    name: str
    code: Optional[str] = None
    labels: Tuple[XLabel, ...] = ()
    is_default: bool = False


@dataclass(frozen=True)
class XDomain:
    """An explicit or typed dimension domain.

    Attributes:
        qname: Prefixed qname of the domain element.
        code: Short domain code (dpm1 provides one; ``None`` lets
            the mapper synthesise one from *qname*).
        name: Human-readable name.
        members: Member closure of the domain.
        is_typed: Whether this is a typed domain.
        typed_data_type: XSD type qname backing a typed domain.
        labels: All label resources for the domain.
    """

    qname: str
    code: Optional[str]
    name: str
    members: Tuple[XMember, ...] = ()
    is_typed: bool = False
    typed_data_type: Optional[str] = None
    labels: Tuple[XLabel, ...] = ()


@dataclass(frozen=True)
class XHierarchyNode:
    """A member placement inside a hierarchy.

    Attributes:
        member_qname: Qname of the placed member.
        parent_qname: Qname of the parent member, ``None`` for
            roots.
        order: Sort order within the parent.
    """

    member_qname: str
    parent_qname: Optional[str]
    order: int


@dataclass(frozen=True)
class XHierarchy:
    """An ordered member tree over one domain.

    Attributes:
        code: Hierarchy code (``None`` lets the mapper synthesise
            one from the category code).
        name: Human-readable name.
        domain_qname: Qname of the domain the members belong to.
        role_uri: Extended link role the tree was read from.
        nodes: Member placements, parents before children.
    """

    code: Optional[str]
    name: str
    domain_qname: str
    role_uri: str
    nodes: Tuple[XHierarchyNode, ...] = ()


@dataclass(frozen=True)
class XDimension:
    """An XBRL dimension.

    Attributes:
        qname: Prefixed qname of the dimension element.
        code: Short dimension code when provided by the taxonomy.
        name: Human-readable name.
        domain_qname: Qname of the associated domain; ``None`` for
            open explicit dimensions with no usable domain.
        is_typed: Whether this is a typed dimension.
        is_open: Whether values are unconstrained (typed dimension
            or explicit dimension whose domain is not usable).
        labels: All label resources for the dimension.
    """

    qname: str
    code: Optional[str]
    name: str
    domain_qname: Optional[str] = None
    is_typed: bool = False
    is_open: bool = False
    labels: Tuple[XLabel, ...] = ()


@dataclass(frozen=True)
class XMetric:
    """A reportable (concrete) primary item.

    Attributes:
        qname: Prefixed qname of the metric element.
        code: Metric code when provided (dpm1 element names such as
            ``mi53``); ``None`` lets the mapper synthesise one.
        name: Human-readable name.
        xbrl_type: XSD item type qname (``xbrli:monetaryItemType``).
        period_type: XBRL period type (``instant`` or ``duration``).
        labels: All label resources for the metric.
    """

    qname: str
    code: Optional[str]
    name: str
    xbrl_type: str
    period_type: str
    labels: Tuple[XLabel, ...] = ()


@dataclass(frozen=True)
class XHeaderNode:
    """One header (axis node) of a table.

    Attributes:
        node_id: Table-unique node identifier.
        parent_id: ``node_id`` of the parent header, ``None`` for
            axis roots.
        order: Sort order within the parent.
        label: Display label.
        code: Header code (``r010``/``c020`` style); ``None`` lets
            the mapper synthesise one in tree order.
        is_abstract: Whether the header is a grouping-only node.
        metric_qname: Metric contributed to cells under this
            header, if any.
        dim_members: ``(dimension_qname, member_qname)`` pairs
            contributed to cells under this header.
        labels: All label resources for the header.
    """

    node_id: str
    parent_id: Optional[str]
    order: int
    label: str
    code: Optional[str] = None
    is_abstract: bool = False
    metric_qname: Optional[str] = None
    dim_members: Tuple[Tuple[str, str], ...] = ()
    labels: Tuple[XLabel, ...] = ()


@dataclass(frozen=True)
class XAxis:
    """One axis (X, Y or Z) of a table.

    Attributes:
        direction: ``X``, ``Y`` or ``Z``.
        nodes: Header nodes, parents before children.
        open_dimension_qnames: Open dimensions reported on this
            axis (keys); a non-empty tuple marks the axis as open.
    """

    direction: str
    nodes: Tuple[XHeaderNode, ...] = ()
    open_dimension_qnames: Tuple[str, ...] = ()

    @property
    def is_open(self) -> bool:
        """Whether the axis carries open (key) dimensions."""
        return bool(self.open_dimension_qnames)


@dataclass(frozen=True)
class XCell:
    """A datapoint at the intersection of table headers.

    Attributes:
        row_node_id: ``node_id`` of the Y header.
        column_node_id: ``node_id`` of the X header.
        sheet_node_id: ``node_id`` of the Z header, if any.
        metric_qname: Metric reported in this cell.
        dim_members: Full ``(dimension_qname, member_qname)``
            context of the cell (metric excluded).
    """

    row_node_id: str
    column_node_id: str
    metric_qname: str
    sheet_node_id: Optional[str] = None
    dim_members: Tuple[Tuple[str, str], ...] = ()


@dataclass(frozen=True)
class XTable:
    """A fully resolved reporting table.

    Attributes:
        code: Table code.
        name: Human-readable name.
        description: Long description.
        axes: The table axes (at most one per direction).
        cells: Enumerated datapoints; empty when enumeration was
            skipped (open or oversized axes).
        entry_schema: Path or URL of the schema defining the table.
        labels: All label resources for the table.
    """

    code: str
    name: str
    axes: Tuple[XAxis, ...] = ()
    cells: Tuple[XCell, ...] = ()
    description: Optional[str] = None
    entry_schema: Optional[str] = None
    labels: Tuple[XLabel, ...] = ()

    def axis(self, direction: str) -> Optional[XAxis]:
        """Return the axis running in *direction*, if present."""
        for candidate in self.axes:
            if candidate.direction == direction:
                return candidate
        return None


@dataclass(frozen=True)
class XModule:
    """A reportable module (entry point).

    Attributes:
        code: Module code.
        name: Human-readable name.
        entry_point: Path or URL of the module entry schema.
        table_codes: Codes of the tables the module comprises, in
            composition order.
        version: Version string, if known.
        from_date: Validity start date, if known.
        labels: All label resources for the module.
    """

    code: str
    name: str
    entry_point: str
    table_codes: Tuple[str, ...] = ()
    version: Optional[str] = None
    from_date: Optional[date] = None
    labels: Tuple[XLabel, ...] = ()


@dataclass(frozen=True)
class TaxonomyModel:
    """Everything extracted from one taxonomy DTS.

    Attributes:
        framework_code: Framework code the content belongs to.
        framework_name: Human-readable framework name.
        dimensions: All dimensions, keyed by qname.
        domains: All domains, keyed by qname.
        hierarchies: Member trees read from linkbase roles.
        metrics: All concrete primary items.
        tables: Fully resolved tables.
        modules: Reportable modules (entry points).
        warnings: Non-fatal findings collected while reading.
    """

    framework_code: str
    framework_name: str
    dimensions: Tuple[XDimension, ...] = ()
    domains: Tuple[XDomain, ...] = ()
    hierarchies: Tuple[XHierarchy, ...] = ()
    metrics: Tuple[XMetric, ...] = ()
    tables: Tuple[XTable, ...] = ()
    modules: Tuple[XModule, ...] = ()
    warnings: Tuple[str, ...] = field(default=())


def merge_models(models: Iterable[TaxonomyModel]) -> TaxonomyModel:
    """Merge per-entry-point models into a single model.

    Each entry point loads its own DTS, so the same domain can
    surface with a different member closure per entry point (a
    table only pulls in the definition linkbases it needs). Domains
    are therefore merged by qname with their members unioned, and
    hierarchies by ``(role_uri, domain_qname)`` with their nodes
    unioned; a dimension seen as both closed and open keeps the
    closed variant. Metrics are deduplicated by qname, tables and
    modules by code (first occurrence wins). Warnings are
    concatenated and deduplicated in order.

    Args:
        models: Models produced from the individual entry points of
            one taxonomy.

    Returns:
        The merged model. Framework identity is taken from the
        first model.

    Raises:
        XbrlImportError: If *models* is empty.
    """
    materialised = list(models)
    if not materialised:
        raise XbrlImportError("No taxonomy content was read.")

    first = materialised[0]

    def _dedupe(pairs: Iterable[Tuple[_K, _V]]) -> Tuple[_V, ...]:
        seen: dict[_K, _V] = {}
        for key, value in pairs:
            if key not in seen:
                seen[key] = value
        return tuple(seen.values())

    return TaxonomyModel(
        framework_code=first.framework_code,
        framework_name=first.framework_name,
        dimensions=_merge_dimensions(materialised),
        domains=_merge_domains(materialised),
        hierarchies=_merge_hierarchies(materialised),
        metrics=_dedupe(
            (met.qname, met) for m in materialised for met in m.metrics
        ),
        tables=_dedupe(
            (table.code, table) for m in materialised for table in m.tables
        ),
        modules=_dedupe(
            (mod.code, mod) for m in materialised for mod in m.modules
        ),
        warnings=_dedupe(
            (warning, warning)
            for m in materialised
            for warning in m.warnings
        ),
    )


def _merge_dimensions(
    models: Iterable[TaxonomyModel],
) -> Tuple[XDimension, ...]:
    """Dedupe dimensions by qname, preferring closed variants."""
    merged: dict[str, XDimension] = {}
    for model in models:
        for dimension in model.dimensions:
            current = merged.get(dimension.qname)
            if current is None or (
                current.is_open and not dimension.is_open
            ):
                merged[dimension.qname] = dimension
    return tuple(merged.values())


def _merge_domains(
    models: Iterable[TaxonomyModel],
) -> Tuple[XDomain, ...]:
    """Merge domains by qname, unioning their member closures."""
    merged: dict[str, XDomain] = {}
    for model in models:
        for domain in model.domains:
            current = merged.get(domain.qname)
            if current is None:
                merged[domain.qname] = domain
                continue
            known = {member.qname for member in current.members}
            extra = tuple(
                member
                for member in domain.members
                if member.qname not in known
            )
            if extra:
                merged[domain.qname] = replace(
                    current, members=current.members + extra
                )
    return tuple(merged.values())


def _merge_hierarchies(
    models: Iterable[TaxonomyModel],
) -> Tuple[XHierarchy, ...]:
    """Merge hierarchies by role/domain, unioning their nodes."""
    merged: dict[Tuple[str, str], XHierarchy] = {}
    for model in models:
        for hierarchy in model.hierarchies:
            key = (hierarchy.role_uri, hierarchy.domain_qname)
            current = merged.get(key)
            if current is None:
                merged[key] = hierarchy
                continue
            known = {node.member_qname for node in current.nodes}
            extra = [
                node
                for node in hierarchy.nodes
                if node.member_qname not in known
            ]
            if extra:
                next_order = len(current.nodes)
                renumbered = tuple(
                    replace(node, order=next_order + offset)
                    for offset, node in enumerate(extra, start=1)
                )
                merged[key] = replace(
                    current, nodes=current.nodes + renumbered
                )
    return tuple(merged.values())
