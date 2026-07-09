"""lxml parser for PWD-2013-05-17 table linkbases (TREP ``-rend.xml``).

TREP's rendering files use the 2013 public-working-draft table
linkbase — a small, regular subset: one ``gen:link`` per table with
``table:table``, ``table:breakdown``, ``table:ruleNode`` (carrying
``formula:concept`` and ``formula:explicitDimension`` aspects) and
``table:aspectNode`` resources, wired by breakdown-tree /
definition-node-subtree / table-breakdown arcs. Arelle's support for
this draft version is geared to rendering, not model extraction, so
the importer parses the files directly.

The parser also reads the accompanying label linkbases (both
2003-style ``link:label`` and 2008 generic ``label:label``), which
carry the header codes (Eurofiling ``rc-code`` role) and the
fr/nl/en display labels.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from lxml import etree

from dpmcore.loaders.xbrl.model import XbrlImportError, XLabel

_LINK = "http://www.xbrl.org/2003/linkbase"
_XLINK = "http://www.w3.org/1999/xlink"
_TABLE = "http://xbrl.org/PWD/2013-05-17/table"
_FORMULA = "http://xbrl.org/2008/formula"

_STANDARD_LABEL_ROLES = {
    "http://www.xbrl.org/2003/role/label",
    "http://www.xbrl.org/2008/role/label",
}
_CODE_LABEL_ROLES = {
    "http://www.eurofiling.info/xbrl/role/rc-code",
    "http://www.eurofiling.info/xbrl/role/filing-indicator-code",
}

#: Maps a namespace URI and local name to a canonical prefixed qname.
Canonicalizer = Callable[[str, str], str]


@dataclass(frozen=True)
class RendNode:
    """One definition node of a rendering breakdown.

    Attributes:
        node_id: XML id of the rule node.
        parent_id: Id of the parent rule node, ``None`` for roots.
        order: Document-order sequence within the axis.
        is_abstract: Whether the node is abstract.
        metric_qname: Canonical qname of the ``formula:concept``
            aspect, if present.
        dim_members: Canonical ``(dimension, member)`` aspects.
    """

    node_id: str
    parent_id: Optional[str]
    order: int
    is_abstract: bool = False
    metric_qname: Optional[str] = None
    dim_members: Tuple[Tuple[str, str], ...] = ()


@dataclass(frozen=True)
class RendAxis:
    """All breakdowns of one axis direction, merged.

    Attributes:
        direction: ``X``, ``Y`` or ``Z``.
        nodes: Rule nodes in depth-first order.
        open_dimension_qnames: Dimensions contributed by aspect
            nodes (open axes).
    """

    direction: str
    nodes: Tuple[RendNode, ...] = ()
    open_dimension_qnames: Tuple[str, ...] = ()


@dataclass(frozen=True)
class RendTable:
    """A parsed rendering file.

    Attributes:
        table_id: XML id of the ``table:table`` resource.
        code: Table code derived from the id (``be_tT_04.00`` ->
            ``T_04.00``).
        axes: One entry per axis direction present.
    """

    table_id: str
    code: str
    axes: Tuple[RendAxis, ...] = ()


@dataclass
class _Breakdown:
    axis: str
    order: float
    roots: List[Tuple[float, str]] = field(default_factory=list)


def _qname_text(
    element: etree._Element,
    text: str,
    canonicalize: Canonicalizer,
) -> str:
    """Resolve a prefixed qname *text* against *element*'s nsmap."""
    prefix, _, local = text.strip().rpartition(":")
    namespace = element.nsmap.get(prefix or None)
    if namespace is None:
        return text.strip()
    return canonicalize(namespace, local)


def _rule_node_aspects(
    node: etree._Element,
    canonicalize: Canonicalizer,
) -> Tuple[Optional[str], Tuple[Tuple[str, str], ...]]:
    metric: Optional[str] = None
    concept = node.find(f"{{{_FORMULA}}}concept/{{{_FORMULA}}}qname")
    if concept is not None and concept.text:
        metric = _qname_text(concept, concept.text, canonicalize)
    pairs: List[Tuple[str, str]] = []
    for explicit in node.findall(f"{{{_FORMULA}}}explicitDimension"):
        dimension = explicit.get("dimension")
        member = explicit.find(
            f"{{{_FORMULA}}}member/{{{_FORMULA}}}qname"
        )
        if dimension is None or member is None or not member.text:
            continue
        pairs.append(
            (
                _qname_text(explicit, dimension, canonicalize),
                _qname_text(member, member.text, canonicalize),
            )
        )
    return metric, tuple(pairs)


class _RendDocument:
    """Indexed resources and arcs of one rendering linkbase."""

    def __init__(self, path: Path, canonicalize: Canonicalizer) -> None:
        self.canonicalize = canonicalize
        self.tables: Dict[str, str] = {}  # xlink:label -> id
        self.breakdowns: Dict[str, _Breakdown] = {}
        self.rule_nodes: Dict[str, etree._Element] = {}
        self.aspect_dims: Dict[str, str] = {}
        self.subtree: Dict[str, List[Tuple[float, str]]] = {}
        root = etree.parse(str(path)).getroot()
        self._scan_resources(root)
        self._scan_arcs(root)

    def _scan_resources(self, root: etree._Element) -> None:
        for element in root.iter():
            tag = element.tag
            label = element.get(f"{{{_XLINK}}}label")
            if not label:
                continue
            if tag == f"{{{_TABLE}}}table":
                self.tables[label] = element.get("id", label)
            elif tag == f"{{{_TABLE}}}breakdown":
                self.breakdowns[label] = _Breakdown(axis="", order=0.0)
            elif tag == f"{{{_TABLE}}}ruleNode":
                self.rule_nodes[label] = element
            elif tag == f"{{{_TABLE}}}aspectNode":
                aspect = element.find(f"{{{_TABLE}}}dimensionAspect")
                if aspect is not None and aspect.text:
                    self.aspect_dims[label] = _qname_text(
                        aspect, aspect.text, self.canonicalize
                    )

    def _scan_arcs(self, root: etree._Element) -> None:
        for element in root.iter():
            tag = element.tag
            source = element.get(f"{{{_XLINK}}}from")
            target = element.get(f"{{{_XLINK}}}to")
            if source is None or target is None:
                continue
            order = float(element.get("order", "0"))
            if tag == f"{{{_TABLE}}}tableBreakdownArc":
                breakdown = self.breakdowns.get(target)
                if breakdown is not None:
                    breakdown.axis = element.get("axis", "").upper()
                    breakdown.order = order
            elif tag == f"{{{_TABLE}}}breakdownTreeArc":
                breakdown = self.breakdowns.get(source)
                if breakdown is not None:
                    breakdown.roots.append((order, target))
            elif tag == f"{{{_TABLE}}}definitionNodeSubtreeArc":
                self.subtree.setdefault(source, []).append(
                    (order, target)
                )


def parse_rend_file(
    path: Path,
    canonicalize: Canonicalizer,
) -> RendTable:
    """Parse the rendering linkbase at *path*.

    Args:
        path: A ``*-rend.xml`` table linkbase file.
        canonicalize: Namespace canonicaliser used for all qnames.

    Returns:
        The parsed table structure.

    Raises:
        XbrlImportError: If the file contains no table resource.
    """
    document = _RendDocument(path, canonicalize)
    if not document.tables:
        raise XbrlImportError(
            f"'{path.name}' contains no table:table resource."
        )
    table_id = next(iter(document.tables.values()))
    axes = []
    for direction in ("X", "Y", "Z"):
        axis = _assemble_axis(document, direction)
        if axis is not None:
            axes.append(axis)
    return RendTable(
        table_id=table_id,
        code=_code_from_table_id(table_id),
        axes=tuple(axes),
    )


def _code_from_table_id(table_id: str) -> str:
    _, separator, code = table_id.partition("_t")
    return code if separator else table_id


class _AxisBuilder:
    """Depth-first assembly of one axis direction."""

    def __init__(self, document: _RendDocument) -> None:
        self._document = document
        self.nodes: List[RendNode] = []
        self.open_dims: List[str] = []
        self._counter = 0

    def emit(self, label: str, parent_id: Optional[str]) -> None:
        element = self._document.rule_nodes.get(label)
        if element is None:
            if label in self._document.aspect_dims:
                self.open_dims.append(
                    self._document.aspect_dims[label]
                )
            return
        self._counter += 1
        node_id = element.get("id", label)
        metric, pairs = _rule_node_aspects(
            element, self._document.canonicalize
        )
        self.nodes.append(
            RendNode(
                node_id=node_id,
                parent_id=parent_id,
                order=self._counter,
                is_abstract=element.get("abstract") == "true",
                metric_qname=metric,
                dim_members=pairs,
            )
        )
        for _order, child in sorted(
            self._document.subtree.get(label, ()),
            key=lambda pair: pair[0],
        ):
            self.emit(child, node_id)


def _assemble_axis(
    document: _RendDocument,
    direction: str,
) -> Optional[RendAxis]:
    builder = _AxisBuilder(document)
    axis_breakdowns = sorted(
        (
            breakdown
            for breakdown in document.breakdowns.values()
            if breakdown.axis == direction
        ),
        key=lambda breakdown: breakdown.order,
    )
    for breakdown in axis_breakdowns:
        for _order, root_label in sorted(
            breakdown.roots, key=lambda pair: pair[0]
        ):
            builder.emit(root_label, None)
    if not builder.nodes and not builder.open_dims:
        return None
    return RendAxis(
        direction=direction,
        nodes=tuple(builder.nodes),
        open_dimension_qnames=tuple(builder.open_dims),
    )


def parse_label_linkbase(
    path: Path,
) -> Dict[Tuple[str, str], List[XLabel]]:
    """Parse a 2003-style or generic label linkbase.

    Args:
        path: Label linkbase file.

    Returns:
        Labels keyed by ``(target file name, fragment)`` of the
        locator href. Standard labels get role ``standard``,
        Eurofiling rc-code / filing-indicator labels get ``code``;
        other roles are ignored.
    """
    root = etree.parse(str(path)).getroot()

    locators: Dict[str, Tuple[str, str]] = {}
    resources: Dict[str, List[XLabel]] = {}
    arcs: List[Tuple[str, str]] = []

    for element in root.iter():
        label = element.get(f"{{{_XLINK}}}label")
        if element.tag == f"{{{_LINK}}}loc" and label:
            href = element.get(f"{{{_XLINK}}}href", "")
            target, _, fragment = href.partition("#")
            locators[label] = (Path(target).name, fragment)
        elif label and element.tag.endswith("}label"):
            role = element.get(f"{{{_XLINK}}}role", "")
            if role in _STANDARD_LABEL_ROLES:
                role_key = "standard"
            elif role in _CODE_LABEL_ROLES:
                role_key = "code"
            else:
                continue
            lang = (
                element.get(
                    "{http://www.w3.org/XML/1998/namespace}lang"
                )
                or "en"
            ).split("-")[0]
            resources.setdefault(label, []).append(
                XLabel(
                    lang=lang,
                    text=element.text or "",
                    role=role_key,
                )
            )
        elif element.tag.endswith("Arc") or element.tag.endswith("}arc"):
            source = element.get(f"{{{_XLINK}}}from")
            target = element.get(f"{{{_XLINK}}}to")
            if source and target:
                arcs.append((source, target))

    out: Dict[Tuple[str, str], List[XLabel]] = {}
    for source, target in arcs:
        locator = locators.get(source)
        labels = resources.get(target)
        if locator is None or labels is None:
            continue
        out.setdefault(locator, []).extend(labels)
    return out
