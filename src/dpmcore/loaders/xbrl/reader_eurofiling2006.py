"""Reader for 2006-Eurofiling-architecture taxonomies (B2P2/FIB/SEG).

These taxonomies are flat directories where ``d-*`` schemas define
dimensions, domains and abstract members, ``p-*`` schemas define the
concrete (reportable) primary items, and each ``t-*`` schema wires
primary items to hypercubes through XDT ``all`` arcs. There is no
table linkbase; the reader derives the table layout:

- **rows** from the presentation tree of the primary-item schema,
- **columns** from the cartesian product of the usable members of
  the closed dimensions reached through the row hypercubes,
- **sheets** (keys) from open dimensions (no usable members) and
  from dimensions dropped by the ``max_enumerated_columns`` valve,
- **cells** from row x column combinations where the row's
  hypercubes cover every column dimension.

The reader is a pure function of a loaded Arelle ``ModelXbrl``; it
returns the neutral :class:`~dpmcore.loaders.xbrl.model.TaxonomyModel`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from arelle import XbrlConst

from dpmcore.loaders.xbrl.model import (
    DIRECTION_X,
    DIRECTION_Y,
    DIRECTION_Z,
    TaxonomyModel,
    XAxis,
    XCell,
    XDimension,
    XDomain,
    XHeaderNode,
    XHierarchy,
    XHierarchyNode,
    XLabel,
    XMember,
    XMetric,
    XModule,
    XTable,
)

_STANDARD_LABEL_ROLE = "http://www.xbrl.org/2003/role/label"
_STANDARD_LINK_ROLE = "http://www.xbrl.org/2003/role/link"
_ENTRY_RE = re.compile(r"^t-(?P<code>.+?)-(?P<date>\d{4}-\d{2}-\d{2})$")

_Labels = Dict[str, Tuple[XLabel, ...]]


def read_entry_point(
    model_xbrl: Any,
    *,
    framework_code: str,
    framework_name: str,
    entry_path: Path,
    max_enumerated_columns: int = 512,
) -> TaxonomyModel:
    """Reduce one ``t-*`` entry point to a taxonomy model.

    Args:
        model_xbrl: Loaded Arelle model of the entry point.
        framework_code: Framework the content belongs to.
        framework_name: Human-readable framework name.
        entry_path: Path of the entry schema (table/module code and
            reference date are derived from its file name).
        max_enumerated_columns: Upper bound on enumerated columns;
            dimensions that would exceed it become key (sheet)
            dimensions instead.

    Returns:
        The extracted model with exactly one table and one module.
    """
    warnings: List[str] = []
    labels = _label_index(model_xbrl)
    table_code, from_date = _parse_entry_name(entry_path, warnings)

    metrics = _read_metrics(model_xbrl, labels)
    primary_namespaces = {
        qname.rsplit(":", 1)[0] for qname in (m.qname for m in metrics)
    }

    hc_dims = _hypercube_dimensions(model_xbrl)
    dimensions, domains, hierarchies = _read_dictionary(
        model_xbrl, labels, warnings
    )
    dim_by_qname = {dim.qname: dim for dim in dimensions}
    members_by_domain = {dom.qname: dom.members for dom in domains}

    rows, metric_rows, row_roles = _presentation_rows(
        model_xbrl, labels, primary_namespaces
    )
    row_coverage = _row_hypercube_coverage(
        model_xbrl, primary_namespaces
    )
    table = _build_table(
        model_xbrl,
        table_code=table_code,
        entry_path=entry_path,
        rows=rows,
        metric_rows=metric_rows,
        row_coverage=row_coverage,
        hc_dims=hc_dims,
        dim_by_qname=dim_by_qname,
        members_by_domain=members_by_domain,
        row_roles=row_roles,
        max_enumerated_columns=max_enumerated_columns,
        warnings=warnings,
    )

    module = XModule(
        code=table_code,
        name=table.name,
        entry_point=entry_path.name,
        table_codes=(table_code,),
        from_date=from_date,
    )
    return TaxonomyModel(
        framework_code=framework_code,
        framework_name=framework_name,
        dimensions=tuple(dimensions),
        domains=tuple(domains),
        hierarchies=tuple(hierarchies),
        metrics=tuple(metrics),
        tables=(table,),
        modules=(module,),
        warnings=tuple(warnings),
    )


# ------------------------------------------------------------------ #
# Concept-level helpers
# ------------------------------------------------------------------ #


def _qname(concept: Any) -> str:
    return str(concept.qname)


def _namespace(qname: str) -> str:
    return qname.rsplit(":", 1)[0]


def _parse_entry_name(
    entry_path: Path, warnings: List[str]
) -> Tuple[str, Optional[Any]]:
    from datetime import date as date_cls

    match = _ENTRY_RE.match(entry_path.stem)
    if match is None:
        warnings.append(
            f"Entry file name '{entry_path.name}' does not follow "
            "the t-<code>-<date>.xsd convention; using the stem as "
            "table code."
        )
        return entry_path.stem, None
    return match.group("code"), date_cls.fromisoformat(match.group("date"))


def _label_index(model_xbrl: Any) -> _Labels:
    """Collect standard labels for every concept, keyed by qname."""
    index: Dict[str, List[XLabel]] = {}
    rel_set = model_xbrl.relationshipSet(XbrlConst.conceptLabel)
    for rel in rel_set.modelRelationships:
        resource = rel.toModelObject
        if getattr(resource, "role", None) != _STANDARD_LABEL_ROLE:
            continue
        lang = (resource.xmlLang or "en").split("-")[0]
        qname = _qname(rel.fromModelObject)
        index.setdefault(qname, []).append(
            XLabel(lang=lang, text=resource.textValue)
        )
    return {qname: tuple(labels) for qname, labels in index.items()}


def _display_name(labels: _Labels, qname: str) -> str:
    for label in labels.get(qname, ()):
        if label.lang == "en":
            return label.text
    for label in labels.get(qname, ()):
        return label.text
    return qname.rsplit(":", 1)[-1]


def _read_metrics(model_xbrl: Any, labels: _Labels) -> List[XMetric]:
    metrics: List[XMetric] = []
    for concept in model_xbrl.qnameConcepts.values():
        if (
            not concept.isItem
            or concept.isAbstract
            or concept.isHypercubeItem
            or concept.isDimensionItem
        ):
            continue
        qname = _qname(concept)
        metrics.append(
            XMetric(
                qname=qname,
                code=None,
                name=_display_name(labels, qname),
                xbrl_type=str(concept.typeQname or ""),
                period_type=concept.periodType or "instant",
                labels=labels.get(qname, ()),
            )
        )
    return metrics


# ------------------------------------------------------------------ #
# Dictionary: dimensions, domains, members and hierarchies
# ------------------------------------------------------------------ #


def _member_closure(
    model_xbrl: Any, domain_concept: Any
) -> List[Tuple[Any, Optional[str], int, bool]]:
    """DFS the domain-member closure below *domain_concept*.

    Returns:
        ``(concept, parent_qname, order, usable)`` tuples in
        depth-first document order; the domain head is excluded.
    """
    rel_set = model_xbrl.relationshipSet(XbrlConst.domainMember)
    out: List[Tuple[Any, Optional[str], int, bool]] = []
    seen: Set[str] = set()
    order = 0

    def visit(concept: Any, parent_qname: Optional[str]) -> None:
        nonlocal order
        rels = sorted(
            rel_set.fromModelObject(concept),
            key=lambda rel: rel.order or 0,
        )
        for rel in rels:
            member = rel.toModelObject
            member_qname = _qname(member)
            if member_qname in seen:
                continue
            seen.add(member_qname)
            order += 1
            out.append((member, parent_qname, order, rel.isUsable))
            visit(member, member_qname)

    visit(domain_concept, None)
    return out


def _read_dictionary(
    model_xbrl: Any,
    labels: _Labels,
    warnings: List[str],
) -> Tuple[List[XDimension], List[XDomain], List[XHierarchy]]:
    dim_domain = model_xbrl.relationshipSet(XbrlConst.dimensionDomain)
    default_rels = model_xbrl.relationshipSet(XbrlConst.dimensionDefault)
    default_members = {
        _qname(rel.toModelObject)
        for rel in default_rels.modelRelationships
    }

    dimensions: List[XDimension] = []
    domains: Dict[str, XDomain] = {}
    hierarchies: List[XHierarchy] = []

    dim_concepts = sorted(
        (
            concept
            for concept in model_xbrl.qnameConcepts.values()
            if concept.isDimensionItem
        ),
        key=_qname,
    )
    for concept in dim_concepts:
        qname = _qname(concept)
        if concept.isTypedDimension:
            dimensions.append(
                XDimension(
                    qname=qname,
                    code=None,
                    name=_display_name(labels, qname),
                    is_typed=True,
                    is_open=True,
                    labels=labels.get(qname, ()),
                )
            )
            continue
        domain_qname = _read_domain_for_dimension(
            model_xbrl,
            concept,
            dim_domain,
            labels,
            domains,
            hierarchies,
            default_members,
        )
        domain = domains.get(domain_qname) if domain_qname else None
        has_members = domain is not None and bool(domain.members)
        dimensions.append(
            XDimension(
                qname=qname,
                code=None,
                name=_display_name(labels, qname),
                domain_qname=domain_qname,
                is_open=not has_members,
                labels=labels.get(qname, ()),
            )
        )
    return dimensions, list(domains.values()), hierarchies


def _read_domain_for_dimension(
    model_xbrl: Any,
    dim_concept: Any,
    dim_domain: Any,
    labels: _Labels,
    domains: Dict[str, XDomain],
    hierarchies: List[XHierarchy],
    default_members: Set[str],
) -> Optional[str]:
    rels = dim_domain.fromModelObject(dim_concept)
    if not rels:
        return None
    domain_concept = rels[0].toModelObject
    domain_qname = _qname(domain_concept)
    if domain_qname in domains:
        return domain_qname

    closure = _member_closure(model_xbrl, domain_concept)
    members = tuple(
        XMember(
            qname=_qname(member),
            name=_display_name(labels, _qname(member)),
            labels=labels.get(_qname(member), ()),
            is_default=_qname(member) in default_members,
        )
        for member, _parent, _order, usable in closure
        if usable
    )
    domains[domain_qname] = XDomain(
        qname=domain_qname,
        code=None,
        name=_display_name(labels, domain_qname),
        members=members,
        labels=labels.get(domain_qname, ()),
    )
    usable_qnames = {member.qname for member in members}
    nodes = tuple(
        XHierarchyNode(
            member_qname=_qname(member),
            parent_qname=(
                parent if parent in usable_qnames else None
            ),
            order=order,
        )
        for member, parent, order, usable in closure
        if usable
    )
    if nodes:
        hierarchies.append(
            XHierarchy(
                code=None,
                name=_display_name(labels, domain_qname),
                domain_qname=domain_qname,
                role_uri=f"closure:{domain_qname}",
                nodes=nodes,
            )
        )
    return domain_qname


# ------------------------------------------------------------------ #
# Rows (presentation tree of the primary schema)
# ------------------------------------------------------------------ #


def _presentation_rows(
    model_xbrl: Any,
    labels: _Labels,
    primary_namespaces: Set[str],
) -> Tuple[List[XHeaderNode], Dict[str, str], List[str]]:
    """Build the Y axis from the primary-item presentation tree.

    Returns:
        The header nodes, a mapping of metric qname to the node id
        of its first concrete occurrence, and the link roles the
        tree was read from.
    """
    rels = [
        rel
        for rel in model_xbrl.relationshipSet(
            XbrlConst.parentChild
        ).modelRelationships
        if _namespace(_qname(rel.fromModelObject)) in primary_namespaces
        and _namespace(_qname(rel.toModelObject)) in primary_namespaces
    ]
    preferred = [
        rel for rel in rels if rel.linkrole != _STANDARD_LINK_ROLE
    ]
    if preferred:
        rels = preferred

    children: Dict[str, List[Tuple[float, Any]]] = {}
    child_qnames: Set[str] = set()
    parent_order: List[str] = []
    concepts: Dict[str, Any] = {}
    for rel in rels:
        parent = _qname(rel.fromModelObject)
        child = _qname(rel.toModelObject)
        concepts[parent] = rel.fromModelObject
        concepts[child] = rel.toModelObject
        children.setdefault(parent, []).append(
            (rel.order or 0, rel.toModelObject)
        )
        child_qnames.add(child)
        if parent not in parent_order:
            parent_order.append(parent)

    roots = [
        qname for qname in parent_order if qname not in child_qnames
    ]
    nodes: List[XHeaderNode] = []
    metric_rows: Dict[str, str] = {}
    counter = 0

    def emit(concept: Any, parent_id: Optional[str]) -> None:
        nonlocal counter
        counter += 1
        node_id = f"y{counter}"
        qname = _qname(concept)
        is_abstract = bool(concept.isAbstract)
        nodes.append(
            XHeaderNode(
                node_id=node_id,
                parent_id=parent_id,
                order=counter,
                label=_display_name(labels, qname),
                is_abstract=is_abstract,
                metric_qname=None if is_abstract else qname,
            )
        )
        if not is_abstract and qname not in metric_rows:
            metric_rows[qname] = node_id
        for _order, child in sorted(
            children.get(qname, ()), key=lambda pair: pair[0]
        ):
            emit(child, node_id)

    for root in roots:
        emit(concepts[root], None)
    roles: List[str] = []
    for rel in rels:
        if rel.linkrole not in roles:
            roles.append(rel.linkrole)
    return nodes, metric_rows, roles


# ------------------------------------------------------------------ #
# Hypercube wiring
# ------------------------------------------------------------------ #


def _hypercube_dimensions(model_xbrl: Any) -> Dict[str, List[str]]:
    """Map hypercube qname to its dimension qnames (all roles)."""
    out: Dict[str, List[str]] = {}
    rel_set = model_xbrl.relationshipSet(XbrlConst.hypercubeDimension)
    for rel in rel_set.modelRelationships:
        hypercube = _qname(rel.fromModelObject)
        dimension = _qname(rel.toModelObject)
        bucket = out.setdefault(hypercube, [])
        if dimension not in bucket:
            bucket.append(dimension)
    return out


def _row_hypercube_coverage(
    model_xbrl: Any,
    primary_namespaces: Set[str],
) -> Dict[str, Set[str]]:
    """Map primary-item qname to the hypercubes covering it.

    ``all`` arcs attach to specific primary items and are inherited
    down the primary-item domain-member tree.
    """
    own: Dict[str, Set[str]] = {}
    for rel in model_xbrl.relationshipSet(
        XbrlConst.all
    ).modelRelationships:
        primary = _qname(rel.fromModelObject)
        own.setdefault(primary, set()).add(_qname(rel.toModelObject))

    parents: Dict[str, Set[str]] = {}
    for rel in model_xbrl.relationshipSet(
        XbrlConst.domainMember
    ).modelRelationships:
        parent = _qname(rel.fromModelObject)
        child = _qname(rel.toModelObject)
        if (
            _namespace(parent) in primary_namespaces
            and _namespace(child) in primary_namespaces
        ):
            parents.setdefault(child, set()).add(parent)

    coverage: Dict[str, Set[str]] = {}

    def resolve(qname: str, trail: Set[str]) -> Set[str]:
        if qname in coverage:
            return coverage[qname]
        result = set(own.get(qname, ()))
        for parent in parents.get(qname, ()):
            if parent not in trail:
                result |= resolve(parent, trail | {qname})
        coverage[qname] = result
        return result

    for qname in set(own) | set(parents):
        resolve(qname, {qname})
    return coverage


# ------------------------------------------------------------------ #
# Table assembly
# ------------------------------------------------------------------ #


def _split_enumerable_dimensions(
    closed_dims: List[Tuple[str, Tuple[XMember, ...]]],
    max_enumerated_columns: int,
    table_code: str,
    warnings: List[str],
) -> Tuple[
    List[Tuple[str, Tuple[XMember, ...]]],
    List[str],
]:
    """Split closed dimensions into enumerated and key dimensions.

    Dimensions are admitted smallest-first while the column product
    stays within *max_enumerated_columns*; the rest become key
    dimensions (reported as open sheets).
    """
    enumerated: List[Tuple[str, Tuple[XMember, ...]]] = []
    keys: List[str] = []
    product = 1
    for qname, members in sorted(
        closed_dims, key=lambda pair: (len(pair[1]), pair[0])
    ):
        if product * len(members) <= max_enumerated_columns:
            enumerated.append((qname, members))
            product *= len(members)
        else:
            keys.append(qname)
            warnings.append(
                f"Table '{table_code}': dimension '{qname}' has too "
                f"many members ({len(members)}) to enumerate as "
                "columns; imported as a key dimension."
            )
    return enumerated, keys


def _column_nodes(
    enumerated: List[Tuple[str, Tuple[XMember, ...]]],
) -> List[XHeaderNode]:
    """Cartesian product of the enumerated dimensions' members."""
    combos: List[Tuple[Tuple[str, str], ...]] = [()]
    label_parts: List[Tuple[str, ...]] = [()]
    for dim_qname, members in enumerated:
        combos = [
            existing + ((dim_qname, member.qname),)
            for existing in combos
            for member in members
        ]
        label_parts = [
            existing + (member.name,)
            for existing in label_parts
            for member in members
        ]
    nodes = []
    for index, (combo, parts) in enumerate(
        zip(combos, label_parts, strict=True), start=1
    ):
        nodes.append(
            XHeaderNode(
                node_id=f"x{index}",
                parent_id=None,
                order=index,
                label=" | ".join(parts) if parts else "Value",
                dim_members=combo,
            )
        )
    return nodes


def _build_table(
    model_xbrl: Any,
    *,
    table_code: str,
    entry_path: Path,
    rows: List[XHeaderNode],
    metric_rows: Dict[str, str],
    row_coverage: Dict[str, Set[str]],
    hc_dims: Dict[str, List[str]],
    dim_by_qname: Dict[str, XDimension],
    members_by_domain: Dict[str, Tuple[XMember, ...]],
    row_roles: List[str],
    max_enumerated_columns: int,
    warnings: List[str],
) -> XTable:
    table_dims: List[str] = []
    for hypercubes in (
        row_coverage.get(qname, set()) for qname in metric_rows
    ):
        for hypercube in hypercubes:
            for dim_qname in hc_dims.get(hypercube, ()):
                if dim_qname not in table_dims:
                    table_dims.append(dim_qname)

    closed: List[Tuple[str, Tuple[XMember, ...]]] = []
    open_dims: List[str] = []
    for dim_qname in table_dims:
        dimension = dim_by_qname.get(dim_qname)
        if dimension is None or dimension.is_open:
            open_dims.append(dim_qname)
            continue
        members = members_by_domain.get(
            dimension.domain_qname or "", ()
        )
        closed.append((dim_qname, members))

    enumerated, demoted = _split_enumerable_dimensions(
        closed, max_enumerated_columns, table_code, warnings
    )
    open_dims.extend(demoted)
    columns = _column_nodes(enumerated)

    cells = _enumerate_cells(
        metric_rows, row_coverage, hc_dims, columns
    )
    axes = [
        XAxis(direction=DIRECTION_Y, nodes=tuple(rows)),
        XAxis(direction=DIRECTION_X, nodes=tuple(columns)),
    ]
    if open_dims:
        axes.append(
            XAxis(
                direction=DIRECTION_Z,
                open_dimension_qnames=tuple(open_dims),
            )
        )
    return XTable(
        code=table_code,
        name=_table_name(model_xbrl, table_code, row_roles),
        axes=tuple(axes),
        cells=tuple(cells),
        entry_schema=entry_path.name,
    )


def _enumerate_cells(
    metric_rows: Dict[str, str],
    row_coverage: Dict[str, Set[str]],
    hc_dims: Dict[str, List[str]],
    columns: List[XHeaderNode],
) -> List[XCell]:
    cells: List[XCell] = []
    for metric_qname, node_id in metric_rows.items():
        row_dims: Set[str] = set()
        for hypercube in row_coverage.get(metric_qname, ()):
            row_dims.update(hc_dims.get(hypercube, ()))
        for column in columns:
            column_dims = {pair[0] for pair in column.dim_members}
            if not column_dims <= row_dims:
                continue
            cells.append(
                XCell(
                    row_node_id=node_id,
                    column_node_id=column.node_id,
                    metric_qname=metric_qname,
                    dim_members=column.dim_members,
                )
            )
    return cells


def _table_name(
    model_xbrl: Any,
    table_code: str,
    row_roles: List[str],
) -> str:
    """Best-effort table name from the presentation role types."""
    candidates = [
        role for role in row_roles if role != _STANDARD_LINK_ROLE
    ]
    for role_uri in candidates:
        for role_type in model_xbrl.roleTypes.get(role_uri, ()):
            definition = role_type.definition
            if definition:
                return str(definition)
    return table_code
