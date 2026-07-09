"""Minimal stand-ins for the Arelle model objects the readers use.

The readers only touch a narrow surface of Arelle's model API:
``qnameConcepts``, ``relationshipSet(arcrole)`` (with
``modelRelationships`` and ``fromModelObject``), ``roleTypes`` and a
handful of concept/relationship attributes. These fakes implement
exactly that surface so reader branches can be unit-tested without
crafting taxonomy files.
"""

from arelle import XbrlConst

STANDARD_LABEL_ROLE = "http://www.xbrl.org/2003/role/label"
STANDARD_LINK_ROLE = "http://www.xbrl.org/2003/role/link"


class FakeConcept:
    def __init__(
        self,
        qname,
        *,
        is_item=True,
        abstract=False,
        hypercube=False,
        dimension=False,
        typed=False,
        type_qname="xbrli:monetaryItemType",
        period_type="instant",
    ):
        self.qname = qname
        self.isItem = is_item
        self.isAbstract = abstract
        self.isHypercubeItem = hypercube
        self.isDimensionItem = dimension
        self.isTypedDimension = typed
        self.typeQname = type_qname
        self.periodType = period_type

    def __repr__(self):
        return f"FakeConcept({self.qname})"


class FakeLabelResource:
    def __init__(self, text, lang="en", role=STANDARD_LABEL_ROLE):
        self.textValue = text
        self.xmlLang = lang
        self.role = role


class FakeRel:
    def __init__(
        self,
        source,
        target,
        *,
        order=1,
        usable=True,
        linkrole="http://example.com/role/table",
        target_role=None,
    ):
        self.fromModelObject = source
        self.toModelObject = target
        self.order = order
        self.isUsable = usable
        self.linkrole = linkrole
        self.targetRole = target_role


class FakeRelationshipSet:
    def __init__(self, rels):
        self.modelRelationships = list(rels)

    def fromModelObject(self, concept):
        return [
            rel
            for rel in self.modelRelationships
            if rel.fromModelObject is concept
        ]


class FakeRoleType:
    def __init__(self, definition):
        self.definition = definition


class FakeModelXbrl:
    """Container mimicking the ModelXbrl surface used by readers."""

    def __init__(self):
        self.qnameConcepts = {}
        self.roleTypes = {}
        self._rels = {
            XbrlConst.conceptLabel: [],
            XbrlConst.parentChild: [],
            XbrlConst.all: [],
            XbrlConst.hypercubeDimension: [],
            XbrlConst.dimensionDomain: [],
            XbrlConst.domainMember: [],
            XbrlConst.dimensionDefault: [],
        }

    def add_concept(self, concept):
        self.qnameConcepts[concept.qname] = concept
        return concept

    def add_rel(self, arcrole, rel):
        self._rels.setdefault(arcrole, []).append(rel)
        return rel

    def add_label(self, concept, text, lang="en", role=STANDARD_LABEL_ROLE):
        self.add_rel(
            XbrlConst.conceptLabel,
            FakeRel(concept, FakeLabelResource(text, lang, role)),
        )

    def relationshipSet(self, arcrole):
        return FakeRelationshipSet(self._rels.get(arcrole, []))
