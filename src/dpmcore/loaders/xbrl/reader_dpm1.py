"""Reader for EBA-DPM-1.0-style taxonomies (TREP).

These taxonomies mirror the Eurofiling/EBA layout: a ``dict`` tree
with dimensions (``dict/dim/dim.xsd``), explicit domains
(``dict/dom/exp.xsd`` heads plus per-domain ``mem.xsd`` member
schemas and ``mem-def.xml`` membership linkbases), typed domains
(``dict/dom/typ.xsd``) and metrics (``dict/met/met.xsd``); and a
``fws`` tree with module entry points (``mod/*.xsd``) and one table
directory per table carrying a PWD-2013 rendering linkbase
(``*-rend.xml``) with code/fr/nl label linkbases.

Everything is parsed directly with lxml — deliberately without
Arelle DTS resolution, because the NBB dictionary schemas import the
retired EBA CRR dictionary URLs, which no longer resolve online.
Concepts from those EBA namespaces are carried through as opaque
canonical qnames (``eba_BA:x17``); the mapper reuses them by
signature when importing into a populated database and otherwise
creates owned shadow rows.

Canonical qnames follow the DPM signature convention:
``<owner>_<domain>:<name>`` (``be_QD:x1``, ``eba_met:mi53``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from lxml import etree

from dpmcore.loaders.xbrl.model import (
    TaxonomyModel,
    XAxis,
    XbrlImportError,
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
from dpmcore.loaders.xbrl.rend_parser import (
    RendAxis,
    RendNode,
    RendTable,
    parse_label_linkbase,
    parse_rend_file,
)


class _NodeLabelIndex:
    """Label lookups for the nodes of one rendering file."""

    def __init__(
        self,
        rend_file_name: str,
        labels: Dict[Tuple[str, str], List["XLabel"]],
    ) -> None:
        self._file_name = rend_file_name
        self._labels = labels

    def _for(self, node_id: str) -> List["XLabel"]:
        return self._labels.get((self._file_name, node_id), [])

    def code(self, node_id: str) -> Optional[str]:
        """First Eurofiling code label of the node, if any."""
        for label in self._for(node_id):
            if label.role == "code":
                return label.text
        return None

    def display(self, node_id: str, fallback: str) -> str:
        """Best standard label (en first), or *fallback*."""
        found = self._for(node_id)
        for label in found:
            if label.role == "standard" and label.lang == "en":
                return label.text
        for label in found:
            if label.role == "standard":
                return label.text
        return fallback

    def standard(self, node_id: str) -> Tuple["XLabel", ...]:
        """All standard-role labels of the node."""
        return tuple(
            label
            for label in self._for(node_id)
            if label.role == "standard"
        )

_XS = "http://www.w3.org/2001/XMLSchema"
_LINK = "http://www.xbrl.org/2003/linkbase"
_XLINK = "http://www.w3.org/1999/xlink"
_XBRLDT = "http://xbrl.org/2005/xbrldt"
_XBRLI = "http://www.xbrl.org/2003/instance"

_ARCROLE_DIMENSION_DOMAIN = (
    "http://xbrl.org/int/dim/arcrole/dimension-domain"
)
_ARCROLE_DIMENSION_DEFAULT = (
    "http://xbrl.org/int/dim/arcrole/dimension-default"
)
_ARCROLE_DOMAIN_MEMBER = "http://xbrl.org/int/dim/arcrole/domain-member"

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class _SchemaElement:
    """One ``xs:element`` declaration found in a dictionary schema."""

    path: Path
    fragment: str
    name: str
    namespace: str
    type_attr: Optional[str]
    substitution_group: Optional[str]
    period_type: Optional[str]
    typed_domain_ref: Optional[str]


@dataclass(frozen=True)
class _Arc:
    """One resolved definition arc between schema elements."""

    source: Tuple[Path, str]
    target: Tuple[Path, str]
    order: float
    usable: bool


def canonical_prefix(namespace: str) -> str:
    """Derive the canonical DPM prefix for *namespace*.

    ``.../xbrl/crr/dict/dom/BA`` becomes ``eba_BA`` or ``be_BA``
    depending on the host; ``.../dict/met`` and ``.../dict/dim``
    become ``<owner>_met`` / ``<owner>_dim``. Other namespaces fall
    back to their last path segment.
    """
    owner = "eba" if "eba.europa.eu" in namespace else "be"
    if "/dict/" in namespace:
        tail = namespace.rsplit("/dict/", 1)[1]
        parts = [part for part in tail.split("/") if part]
        if parts and parts[0] == "dom" and len(parts) > 1:
            return f"{owner}_{parts[1]}"
        if parts:
            return f"{owner}_{parts[0]}"
    segment = namespace.rstrip("/").rsplit("/", 1)[-1]
    return f"{owner}_{segment}" if segment else owner


def canonicalize(namespace: str, local: str) -> str:
    """Build the canonical prefixed qname for an element."""
    return f"{canonical_prefix(namespace)}:{local}"


def read_taxonomy(
    root: Path,
    *,
    framework_code: str,
    framework_name: str,
) -> TaxonomyModel:
    """Read a dpm1-architecture taxonomy rooted at *root*.

    Args:
        root: Directory containing the ``dict`` and ``fws`` trees.
        framework_code: Framework the content belongs to.
        framework_name: Human-readable framework name.

    Returns:
        The extracted taxonomy model.

    Raises:
        XbrlImportError: If *root* lacks the expected layout.
    """
    dict_dir = root / "dict"
    fws_dir = root / "fws"
    if not dict_dir.is_dir() or not fws_dir.is_dir():
        raise XbrlImportError(
            f"'{root}' does not look like a dpm1 taxonomy "
            "(missing dict/ or fws/ directory)."
        )
    warnings: List[str] = []
    reader = _Dpm1Reader(root, warnings)
    dimensions, domains, hierarchies = reader.read_dictionary()
    metrics = reader.read_metrics()
    tables = reader.read_tables()
    modules = reader.read_modules()
    return TaxonomyModel(
        framework_code=framework_code,
        framework_name=framework_name,
        dimensions=tuple(dimensions),
        domains=tuple(domains),
        hierarchies=tuple(hierarchies),
        metrics=tuple(metrics),
        tables=tuple(tables),
        modules=tuple(modules),
        warnings=tuple(warnings),
    )


class _Dpm1Reader:
    """Stateful helper walking one dpm1 taxonomy tree."""

    def __init__(self, root: Path, warnings: List[str]) -> None:
        self._root = root
        self._warnings = warnings
        self._elements: Dict[Tuple[Path, str], _SchemaElement] = {}
        self._elements_by_file: Dict[Path, List[_SchemaElement]] = {}
        self._labels: Dict[Tuple[Path, str], List[XLabel]] = {}
        self._scan_dictionary_files()

    # ------------------------------------------------------------ #
    # File scanning
    # ------------------------------------------------------------ #

    def _scan_dictionary_files(self) -> None:
        dict_dir = self._root / "dict"
        for schema_path in sorted(dict_dir.rglob("*.xsd")):
            self._scan_schema(schema_path)
        for label_path in sorted(dict_dir.rglob("*-lab-*.xml")):
            self._merge_labels(label_path)

    def _scan_schema(self, schema_path: Path) -> None:
        schema_root = etree.parse(str(schema_path)).getroot()
        namespace = schema_root.get("targetNamespace", "")
        bucket = self._elements_by_file.setdefault(schema_path, [])
        for element in schema_root.iter(f"{{{_XS}}}element"):
            name = element.get("name")
            fragment = element.get("id")
            if name is None or fragment is None:
                continue
            record = _SchemaElement(
                path=schema_path,
                fragment=fragment,
                name=name,
                namespace=namespace,
                type_attr=element.get("type"),
                substitution_group=element.get("substitutionGroup"),
                period_type=element.get(f"{{{_XBRLI}}}periodType"),
                typed_domain_ref=element.get(
                    f"{{{_XBRLDT}}}typedDomainRef"
                ),
            )
            self._elements[(schema_path, fragment)] = record
            bucket.append(record)

    def _merge_labels(self, label_path: Path) -> None:
        parsed = parse_label_linkbase(label_path)
        for (file_name, fragment), labels in parsed.items():
            target = label_path.parent / file_name
            self._labels.setdefault((target, fragment), []).extend(
                labels
            )

    # ------------------------------------------------------------ #
    # Generic lookups
    # ------------------------------------------------------------ #

    def _resolve_href(
        self, base: Path, href: str
    ) -> Optional[Tuple[Path, str]]:
        target, _, fragment = href.partition("#")
        if not fragment:
            return None
        try:
            resolved = (base.parent / target).resolve()
        except OSError:  # pragma: no cover - defensive
            return None
        return (resolved, fragment)

    def _element(
        self, key: Tuple[Path, str]
    ) -> Optional[_SchemaElement]:
        return self._elements.get(key)

    def _qname(self, record: _SchemaElement) -> str:
        return canonicalize(record.namespace, record.name)

    def _labels_for(self, record: _SchemaElement) -> Tuple[XLabel, ...]:
        return tuple(
            self._labels.get((record.path.resolve(), record.fragment), ())
        ) or tuple(self._labels.get((record.path, record.fragment), ()))

    def _display_name(self, record: _SchemaElement) -> str:
        labels = self._labels_for(record)
        for label in labels:
            if label.role == "standard" and label.lang == "en":
                return label.text
        for label in labels:
            if label.role == "standard":
                return label.text
        return record.name

    def _parse_arcs(self, linkbase_path: Path, arcrole: str) -> List[_Arc]:
        root = etree.parse(str(linkbase_path)).getroot()
        locators: Dict[str, Tuple[Path, str]] = {}
        arcs: List[_Arc] = []
        for element in root.iter():
            if element.tag == f"{{{_LINK}}}loc":
                label = element.get(f"{{{_XLINK}}}label")
                href = element.get(f"{{{_XLINK}}}href", "")
                key = self._resolve_href(linkbase_path, href)
                if label and key is not None:
                    locators[label] = key
            elif element.tag == f"{{{_LINK}}}definitionArc":
                if element.get(f"{{{_XLINK}}}arcrole") != arcrole:
                    continue
                source = locators.get(
                    element.get(f"{{{_XLINK}}}from", "")
                )
                target = locators.get(element.get(f"{{{_XLINK}}}to", ""))
                if source is None or target is None:
                    continue
                arcs.append(
                    _Arc(
                        source=source,
                        target=target,
                        order=float(element.get("order", "0")),
                        usable=element.get(f"{{{_XBRLDT}}}usable")
                        != "false",
                    )
                )
        return arcs

    # ------------------------------------------------------------ #
    # Dictionary
    # ------------------------------------------------------------ #

    def read_metrics(self) -> List[XMetric]:
        """Read ``dict/met/met.xsd``."""
        met_path = self._root / "dict" / "met" / "met.xsd"
        metrics: List[XMetric] = [
            XMetric(
                qname=self._qname(record),
                code=record.name,
                name=self._display_name(record),
                xbrl_type=record.type_attr or "",
                period_type=record.period_type or "instant",
                labels=self._labels_for(record),
            )
            for record in self._elements_by_file.get(met_path, [])
        ]
        if not metrics:
            self._warnings.append(
                "No metrics found under dict/met/met.xsd."
            )
        return metrics

    def read_dictionary(
        self,
    ) -> Tuple[List[XDimension], List[XDomain], List[XHierarchy]]:
        """Read dimensions, domains, members and hierarchies."""
        domains = self._read_domains()
        hierarchies = self._read_hierarchies(domains)
        dimensions = self._read_dimensions(domains)
        return dimensions, list(domains.values()), hierarchies

    def _read_domains(self) -> Dict[Tuple[Path, str], XDomain]:
        """Explicit domains from exp.xsd + per-domain memberships."""
        domains: Dict[Tuple[Path, str], XDomain] = {}
        dom_dir = self._root / "dict" / "dom"
        exp_path = dom_dir / "exp.xsd"
        for record in self._elements_by_file.get(exp_path, []):
            members = self._domain_members(dom_dir, record)
            domains[(exp_path.resolve(), record.fragment)] = XDomain(
                qname=self._qname(record),
                code=record.name,
                name=self._display_name(record),
                members=members,
                labels=self._labels_for(record),
            )
        for record in self._elements_by_file.get(dom_dir / "typ.xsd", []):
            key = ((dom_dir / "typ.xsd").resolve(), record.fragment)
            domains[key] = XDomain(
                qname=self._qname(record),
                code=record.name,
                name=record.name,
                is_typed=True,
                typed_data_type=record.type_attr,
            )
        return domains

    def _domain_members(
        self, dom_dir: Path, head: _SchemaElement
    ) -> Tuple[XMember, ...]:
        """Members of *head* from the matching mem-def linkbase."""
        folder = dom_dir / head.name.lower()
        mem_def = folder / "mem-def.xml"
        if not mem_def.is_file():
            return ()
        members: List[XMember] = []
        seen = set()
        arcs = self._parse_arcs(mem_def, _ARCROLE_DOMAIN_MEMBER)
        for arc in sorted(arcs, key=lambda a: a.order):
            record = self._element(arc.target)
            if record is None or record.fragment in seen:
                continue
            seen.add(record.fragment)
            members.append(
                XMember(
                    qname=self._qname(record),
                    name=self._display_name(record),
                    code=record.name,
                    labels=self._labels_for(record),
                )
            )
        return tuple(members)

    def _read_hierarchies(
        self, domains: Dict[Tuple[Path, str], XDomain]
    ) -> List[XHierarchy]:
        hierarchies: List[XHierarchy] = []
        dom_dir = self._root / "dict" / "dom"
        for hier_def in sorted(dom_dir.rglob("hier-def.xml")):
            hierarchy = self._read_hierarchy(hier_def, domains)
            if hierarchy is not None:
                hierarchies.append(hierarchy)
        return hierarchies

    def _read_hierarchy(
        self,
        hier_def: Path,
        domains: Dict[Tuple[Path, str], XDomain],
    ) -> Optional[XHierarchy]:
        arcs = self._parse_arcs(hier_def, _ARCROLE_DOMAIN_MEMBER)
        if not arcs:
            return None
        domain: Optional[XDomain] = None
        head_fragments = set()
        for arc in arcs:
            candidate = domains.get(
                (arc.source[0], arc.source[1])
            )
            if candidate is not None:
                domain = candidate
                head_fragments.add(arc.source[1])
        if domain is None:
            self._warnings.append(
                f"Hierarchy '{hier_def}' does not start from a known "
                "domain; skipped."
            )
            return None
        nodes: List[XHierarchyNode] = []
        placed: Set[str] = set()
        order = 0
        for arc in sorted(arcs, key=lambda a: a.order):
            target = self._element(arc.target)
            if target is None:
                continue
            member_qname = self._qname(target)
            if member_qname in placed:
                # A member can be reachable through several parents;
                # DPM hierarchies place each item once.
                continue
            placed.add(member_qname)
            parent = self._element(arc.source)
            order += 1
            nodes.append(
                XHierarchyNode(
                    member_qname=member_qname,
                    parent_qname=(
                        self._qname(parent)
                        if parent is not None
                        and arc.source[1] not in head_fragments
                        else None
                    ),
                    order=order,
                )
            )
        role_uri = f"hier:{hier_def.parent.name}"
        return XHierarchy(
            code=None,
            name=f"{domain.name} hierarchy",
            domain_qname=domain.qname,
            role_uri=role_uri,
            nodes=tuple(nodes),
        )

    def _read_dimensions(
        self, domains: Dict[Tuple[Path, str], XDomain]
    ) -> List[XDimension]:
        dim_path = self._root / "dict" / "dim" / "dim.xsd"
        dim_def = self._root / "dict" / "dim" / "dim-def.xml"
        domain_arcs: Dict[str, Tuple[Path, str]] = {}
        if dim_def.is_file():
            for arc in self._parse_arcs(
                dim_def, _ARCROLE_DIMENSION_DOMAIN
            ):
                domain_arcs.setdefault(arc.source[1], arc.target)

        dimensions: List[XDimension] = []
        for record in self._elements_by_file.get(dim_path, []):
            if record.typed_domain_ref is not None:
                key = self._resolve_href(
                    record.path, record.typed_domain_ref
                )
                typed_domain = (
                    domains.get(key) if key is not None else None
                )
                dimensions.append(
                    XDimension(
                        qname=self._qname(record),
                        code=record.name,
                        name=self._display_name(record),
                        domain_qname=(
                            typed_domain.qname
                            if typed_domain is not None
                            else None
                        ),
                        is_typed=True,
                        is_open=True,
                        labels=self._labels_for(record),
                    )
                )
                continue
            domain_key = domain_arcs.get(record.fragment)
            domain = (
                domains.get(domain_key)
                if domain_key is not None
                else None
            )
            if domain is None:
                self._warnings.append(
                    f"Dimension '{record.name}' has no "
                    "dimension-domain arc; imported as open."
                )
            dimensions.append(
                XDimension(
                    qname=self._qname(record),
                    code=record.name,
                    name=self._display_name(record),
                    domain_qname=(
                        domain.qname if domain is not None else None
                    ),
                    is_open=domain is None or not domain.members,
                    labels=self._labels_for(record),
                )
            )
        return dimensions

    # ------------------------------------------------------------ #
    # Tables
    # ------------------------------------------------------------ #

    def read_tables(self) -> List[XTable]:
        """Parse every ``*-rend.xml`` under the fws tree."""
        tables: List[XTable] = [
            self._read_table(rend_path)
            for rend_path in sorted(self._root.rglob("*-rend.xml"))
        ]
        if not tables:
            self._warnings.append(
                "No *-rend.xml table linkbases found under fws/."
            )
        return tables

    def _read_table(self, rend_path: Path) -> XTable:
        rend = parse_rend_file(rend_path, canonicalize)
        labels = _NodeLabelIndex(
            rend_path.name, self._table_labels(rend_path)
        )
        axes = [
            self._build_axis(rend_axis, labels)
            for rend_axis in rend.axes
        ]
        cells = _enumerate_rend_cells(rend, self._warnings)
        return XTable(
            code=rend.code,
            name=labels.display(rend.table_id, rend.code),
            axes=tuple(axes),
            cells=tuple(cells),
            entry_schema=rend_path.name,
            labels=labels.standard(rend.table_id),
        )

    def _build_axis(
        self, rend_axis: RendAxis, labels: "_NodeLabelIndex"
    ) -> XAxis:
        nodes = tuple(
            XHeaderNode(
                node_id=node.node_id,
                parent_id=node.parent_id,
                order=node.order,
                label=labels.display(node.node_id, node.node_id),
                code=labels.code(node.node_id),
                is_abstract=node.is_abstract,
                metric_qname=node.metric_qname,
                dim_members=node.dim_members,
                labels=labels.standard(node.node_id),
            )
            for node in rend_axis.nodes
        )
        return XAxis(
            direction=rend_axis.direction,
            nodes=nodes,
            open_dimension_qnames=rend_axis.open_dimension_qnames,
        )

    def _table_labels(
        self, rend_path: Path
    ) -> Dict[Tuple[str, str], List[XLabel]]:
        labels: Dict[Tuple[str, str], List[XLabel]] = {}
        for label_path in sorted(rend_path.parent.glob("*-lab-*.xml")):
            for key, found in parse_label_linkbase(label_path).items():
                labels.setdefault(key, []).extend(found)
        return labels

    # ------------------------------------------------------------ #
    # Modules
    # ------------------------------------------------------------ #

    def read_modules(self) -> List[XModule]:
        """Parse the module entry schemas under ``fws/**/mod/``."""
        modules: List[XModule] = []
        for mod_path in sorted(self._root.rglob("mod/*.xsd")):
            module = self._read_module(mod_path)
            if module is not None:
                modules.append(module)
        if not modules:
            self._warnings.append(
                "No module schemas found under fws/**/mod/."
            )
        return modules

    def _read_module(self, mod_path: Path) -> Optional[XModule]:
        schema_root = etree.parse(str(mod_path)).getroot()
        declaration = None
        for element in schema_root.iter(f"{{{_XS}}}element"):
            type_attr = element.get("type", "")
            if type_attr.endswith(":moduleType"):
                declaration = element
                break
        if declaration is None:
            self._warnings.append(
                f"'{mod_path.name}' declares no moduleType element; "
                "skipped."
            )
            return None

        table_codes: List[str] = []
        for imported in schema_root.iter(f"{{{_XS}}}import"):
            namespace = imported.get("namespace", "")
            if "/tab/" in namespace:
                table_codes.append(
                    namespace.rstrip("/").rsplit("/", 1)[-1]
                )

        code = declaration.get("name", mod_path.stem)
        labels = self._module_labels(mod_path, declaration.get("id"))
        name = (
            next(
                (
                    label.text
                    for label in labels
                    if label.lang == "en"
                ),
                None,
            )
            or next((label.text for label in labels), None)
            or code
        )
        return XModule(
            code=code,
            name=name,
            entry_point=str(mod_path.relative_to(self._root)),
            table_codes=tuple(table_codes),
            from_date=_date_from_path(mod_path),
            labels=labels,
        )

    def _module_labels(
        self, mod_path: Path, fragment: Optional[str]
    ) -> Tuple[XLabel, ...]:
        if fragment is None:
            return ()
        labels: List[XLabel] = []
        pattern = f"{mod_path.stem}-lab-*.xml"
        for label_path in sorted(mod_path.parent.glob(pattern)):
            parsed = parse_label_linkbase(label_path)
            labels.extend(parsed.get((mod_path.name, fragment), ()))
        return tuple(
            label for label in labels if label.role == "standard"
        )


def _date_from_path(path: Path) -> Optional[date]:
    """Extract a ``YYYY-MM-DD`` directory name from *path*."""
    for part in reversed(path.parts):
        if _DATE_RE.match(part):
            return date.fromisoformat(part)
    return None


def _enumerate_rend_cells(
    rend: RendTable,
    warnings: List[str],
) -> List[XCell]:
    """Cartesian product of non-abstract leaves across axes."""
    leaves: Dict[str, List[Tuple[RendNode, ...]]] = {}
    for axis in rend.axes:
        chains = _leaf_chains(tuple(axis.nodes))
        if chains:
            leaves[axis.direction] = chains
    if "X" not in leaves or "Y" not in leaves:
        return []

    cells: List[XCell] = []
    sheet_chains: List[Optional[Tuple[RendNode, ...]]] = list(
        leaves.get("Z", ())
    ) or [None]
    for y_chain in leaves["Y"]:
        for x_chain in leaves["X"]:
            for z_chain in sheet_chains:
                cell = _merge_cell(
                    rend.code, y_chain, x_chain, z_chain, warnings
                )
                if cell is not None:
                    cells.append(cell)
    return cells


def _leaf_chains(
    nodes: Tuple[RendNode, ...],
) -> List[Tuple[RendNode, ...]]:
    """Ancestor chains (root..leaf) for each non-abstract leaf."""
    by_id = {node.node_id: node for node in nodes}
    has_children = {
        node.parent_id for node in nodes if node.parent_id is not None
    }
    chains: List[Tuple[RendNode, ...]] = []
    for node in nodes:
        if node.node_id in has_children or node.is_abstract:
            continue
        chain: List[RendNode] = []
        cursor: Optional[RendNode] = node
        while cursor is not None:
            chain.append(cursor)
            cursor = (
                by_id.get(cursor.parent_id)
                if cursor.parent_id is not None
                else None
            )
        chains.append(tuple(reversed(chain)))
    return chains


def _merge_cell(
    table_code: str,
    y_chain: Tuple[RendNode, ...],
    x_chain: Tuple[RendNode, ...],
    z_chain: Optional[Tuple[RendNode, ...]],
    warnings: List[str],
) -> Optional[XCell]:
    metric: Optional[str] = None
    dims: Dict[str, str] = {}
    chains = [y_chain, x_chain] + (
        [z_chain] if z_chain is not None else []
    )
    for chain in chains:
        for node in chain:
            if node.metric_qname is not None:
                if metric is not None and metric != node.metric_qname:
                    warnings.append(
                        f"Table '{table_code}': conflicting concept "
                        f"aspects for cell ({y_chain[-1].node_id}, "
                        f"{x_chain[-1].node_id}); cell skipped."
                    )
                    return None
                metric = node.metric_qname
            dims.update(node.dim_members)
    if metric is None:
        warnings.append(
            f"Table '{table_code}': no concept aspect for cell "
            f"({y_chain[-1].node_id}, {x_chain[-1].node_id}); "
            "cell skipped."
        )
        return None
    return XCell(
        row_node_id=y_chain[-1].node_id,
        column_node_id=x_chain[-1].node_id,
        sheet_node_id=(
            z_chain[-1].node_id if z_chain is not None else None
        ),
        metric_qname=metric,
        dim_members=tuple(sorted(dims.items())),
    )
