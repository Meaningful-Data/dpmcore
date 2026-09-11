"""Super-category expansion, shared by every domain-resolving path.

A *super-category* is a ``Category`` whose value set is the union of its
own items and the value sets of the categories composing it
(``SuperCategoryComposition``). EBA's ``qTU`` ("qAI, qFI, qSR & qTA")
holds a single item of its own and draws the other 926 from those four.
``ItemCategory`` files each item under the one category that owns it, so
any code that answers "which items does this domain hold?" by reading
``ItemCategory`` alone sees only that single item (#359).

Every such caller — the DPM-XL domain-membership check, the structure
service's category/property/table enumerations, the layout exporter —
needs the same expansion, so it lives here once rather than being
reimplemented per call site with subtly different filters.

Members are restricted to *enumerated* categories carrying a code: a
non-enumerated category (dates, identifiers, free text) is not a value
set, so it contributes no items to the domain.

The composition is release-versioned and is resolved transitively: the
EBA dictionary does not nest super-categories today (0 of 102
composition rows names a member that is itself a super-category), but
nothing in the schema forbids it, and a silently missing second level
would drop items from enumerations and manufacture false domain
warnings. The closure walk costs one extra query only when a member
turns out to be a super-category, so honouring the general case is
effectively free.
"""

from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
    Collection,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
)

from sqlalchemy.orm import aliased

from dpmcore.orm.glossary import Category, SupercategoryComposition
from dpmcore.orm.query_utils import chunked_in

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def load_supercategory_members(
    session: "Session",
    category_ids: Collection[int],
    *,
    release_id: Optional[int],
) -> Dict[int, Set[int]]:
    """Map super-category IDs to the IDs of the categories in them.

    Args:
        session: SQLAlchemy session.
        category_ids: Category IDs to expand. One that composes nothing
            at *release_id* gets no entry, so the result is also the
            answer to "which of these are super-categories?".
        release_id: Release the composition is resolved at; ``None``
            resolves against the currently-open compositions.

    Returns:
        ``{supercategory_id: {member_category_id, ...}}``, transitively
        expanded.
    """
    return _closure(session, category_ids, release_id, by_code=False)


def load_supercategory_member_codes(
    session: "Session",
    codes: Collection[str],
    *,
    release_id: Optional[int],
) -> Dict[str, Set[str]]:
    """Map super-category codes to the codes of the categories in them.

    Code-keyed twin of :func:`load_supercategory_members`, for callers
    that resolve domains by ``Category.code`` rather than by ID.

    Args:
        session: SQLAlchemy session.
        codes: Category codes to expand; a code that composes nothing at
            *release_id* gets no entry.
        release_id: Release the composition is resolved at.

    Returns:
        ``{supercategory_code: {member_code, ...}}``, transitively
        expanded.
    """
    return _closure(session, codes, release_id, by_code=True)


def load_supercategory_compositions(
    session: "Session",
    category_ids: Collection[int],
) -> Dict[int, List[SupercategoryComposition]]:
    """Composition rows for *category_ids*, every release window kept.

    :func:`load_supercategory_members` answers "what composes this
    domain *at one release*". A caller that walks releases in Python --
    the structure service's virtual category versions, which emit a new
    version whenever the item set changes -- needs each row's own
    window instead, so the composition opening or closing shows up as a
    version boundary like any other change.

    Nesting is followed like it is by :func:`load_supercategory_members`,
    but the windows are *not* collapsed: the result is the composition
    graph reachable from *category_ids*, keyed by super-category, so a
    nested member that is only reachable while both links are open is
    the caller's own intersection to make, release by release.

    Members are filtered the same way as everywhere else: an
    enumerated category carrying a code.

    Args:
        session: SQLAlchemy session.
        category_ids: Super-category IDs to load compositions for.

    Returns:
        ``{supercategory_id: [SupercategoryComposition, ...]}`` for every
        super-category reachable from *category_ids*, omitting
        categories that compose nothing at any release.
    """
    compositions: Dict[int, List[SupercategoryComposition]] = {}
    pending = set(category_ids)
    asked: Set[int] = set()
    while pending:
        asked |= pending
        next_level: Set[int] = set()
        for row in _composition_rows(session, pending):
            compositions.setdefault(row.supercategory_id, []).append(row)
            next_level.add(row.category_id)
        # A member reached twice is queried once, so a cycle in the
        # data terminates instead of looping.
        pending = next_level - asked
    return compositions


def _composition_rows(
    session: "Session",
    supercategory_ids: Collection[int],
) -> List[SupercategoryComposition]:
    """Composition rows of *supercategory_ids*, one level, all windows."""
    member = aliased(Category)
    query = (
        session.query(SupercategoryComposition)
        .join(
            member,
            member.category_id == SupercategoryComposition.category_id,
        )
        .filter(member.is_enumerated == True)  # noqa: E712
        .filter(member.code.isnot(None))
    )
    return chunked_in(
        query, SupercategoryComposition.supercategory_id, supercategory_ids
    )


def domain_search_order(
    category_id: int,
    members: Dict[int, Set[int]],
) -> List[int]:
    """Categories to look an item up in for a domain, best first.

    The domain's own category comes first — an item filed there is the
    domain's own item and names itself with the domain's code — then the
    categories composing it, ascending by ID. Thirteen (super-category,
    item) pairs in DPM 4.2.1 have the item filed in two members at once,
    so a fixed order is what makes their code and signature
    reproducible. Ordering by ID alone would not do: EBA's ``qTU``
    (1111) outranks every category composing it (1007..1037), so the
    domain's own item would lose to a member's.

    Args:
        category_id: The domain.
        members: ``{supercategory_id: {member_id, ...}}``, as returned
            by :func:`load_supercategory_members`.

    Returns:
        The category IDs to search, in order.
    """
    return [category_id, *sorted(members.get(category_id, set()))]


def _closure(
    session: "Session",
    keys: Collection[Any],
    release_id: Optional[int],
    *,
    by_code: bool,
) -> Dict[Any, Set[Any]]:
    """Transitively expand *keys* over the composition graph.

    Walks level by level, querying only the keys not yet resolved, then
    flattens each requested key's reachable set. A key reached twice is
    queried once, so a cycle in the data terminates instead of looping.
    """
    edges: Dict[Any, Set[Any]] = {}
    pending = set(keys)
    while pending:
        found = _direct_members(session, pending, release_id, by_code=by_code)
        # Record every key asked about, so one that composes nothing is
        # not asked about again on a later level.
        for key in pending:
            edges[key] = found.get(key, set())
        next_level: Set[Any] = set()
        for members in found.values():
            next_level |= members
        pending = next_level - set(edges)
    expanded: Dict[Any, Set[Any]] = {}
    for key in keys:
        reachable = _reachable(edges, key)
        if reachable:
            expanded[key] = reachable
    return expanded


def _reachable(edges: Dict[Any, Set[Any]], key: Any) -> Set[Any]:
    """Every key reachable from *key*, excluding *key* itself."""
    seen: Set[Any] = set()
    frontier = set(edges.get(key, set()))
    while frontier:
        member = frontier.pop()
        if member in seen:
            continue
        seen.add(member)
        frontier |= edges.get(member, set()) - seen
    seen.discard(key)
    return seen


def _direct_members(
    session: "Session",
    keys: Collection[Any],
    release_id: Optional[int],
    *,
    by_code: bool,
) -> Dict[Any, Set[Any]]:
    """One level of composition for *keys*, keyed by code or by ID."""
    if not keys:
        return {}

    from dpmcore.dpm_xl.utils.filters import filter_by_release

    supercategory = aliased(Category)
    member = aliased(Category)
    key_col, member_col = _key_columns(supercategory, member, by_code=by_code)
    query = (
        session.query(
            key_col.label("SuperKey"),
            member_col.label("MemberKey"),
        )
        .select_from(SupercategoryComposition)
        .join(
            supercategory,
            supercategory.category_id
            == SupercategoryComposition.supercategory_id,
        )
        .join(
            member,
            member.category_id == SupercategoryComposition.category_id,
        )
        .filter(member.is_enumerated == True)  # noqa: E712
        .filter(member.code.isnot(None))
    )
    query = filter_by_release(
        query,
        start_col=SupercategoryComposition.start_release_id,
        end_col=SupercategoryComposition.end_release_id,
        release_id=release_id,
        active_only_fallback=True,
    )
    members: Dict[Any, Set[Any]] = {}
    for row in chunked_in(query, key_col, keys):
        members.setdefault(row.SuperKey, set()).add(row.MemberKey)
    return members


def _key_columns(
    supercategory: Any, member: Any, *, by_code: bool
) -> Tuple[Any, Any]:
    """The (super-category, member) columns the result is keyed on."""
    if by_code:
        return supercategory.code, member.code
    return (
        SupercategoryComposition.supercategory_id,
        SupercategoryComposition.category_id,
    )
