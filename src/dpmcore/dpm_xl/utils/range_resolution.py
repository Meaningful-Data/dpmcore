"""Resolve DPM-XL row/column/sheet ranges by stored display order.

A DPM-XL selector may name a range of rows, columns or sheets, e.g.
``r0010-r0090`` or ``r2-r11``. The engine must expand that range into the
codes it covers and list them in the table's display order. Comparing the
code *strings* (``r10`` < ``r2`` because ``"1" < "2"``) only works for codes
that happen to be numeric and zero-padded to a fixed width; it silently drops
or mis-orders non-numeric, non-padded or mixed-width codes.

These helpers resolve ranges against the real ordering key —
``TableVersionHeader.Order`` — exactly as :mod:`dpmcore.orm.release_sort_order`
resolves release ranges against ``Release.date`` rather than the release code.
They are pure and DB-free: callers supply a ``{code: order}`` map for one axis
and these functions never touch a session or a DataFrame.

The ordering column is nullable, so an axis is only resolvable this way when
*every* code on it carries an order. Deciding that (all-or-nothing per axis,
never mixing order-based and string-based comparison within one axis) is the
caller's job; :func:`build_axis_order_map` returns ``None`` to signal it.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Any


def _is_missing(value: object) -> bool:
    """Return True for ``None`` or a NaN float."""
    return value is None or (isinstance(value, float) and math.isnan(value))


def resolve_range_codes(
    code_to_order: Mapping[str, int], lo: str, hi: str
) -> list[str]:
    """Return the codes spanned by the range ``lo``-``hi``, in display order.

    The range covers every code whose stored order lies within
    ``[order[lo], order[hi]]``, returned ascending by that order.

    A **reversed** range (``order[lo] > order[hi]``) returns ``[]``, preserving
    the pre-existing behaviour where such an expression selects nothing and so
    raises a "cell not found" error rather than silently spanning the codes in
    between. An endpoint absent from ``code_to_order`` also returns ``[]``;
    endpoint *existence* is validated separately by the caller (see
    ``_check_range_endpoints``), which raises the user-facing ``1-2`` error.

    Args:
        code_to_order: ``{code: order}`` for one axis of a table version.
        lo: The range's first endpoint code.
        hi: The range's second endpoint code.

    Returns:
        The spanned codes, ascending by stored order; empty when an endpoint
        is absent or the range is reversed.
    """
    lo_order = code_to_order.get(lo)
    hi_order = code_to_order.get(hi)
    if lo_order is None or hi_order is None or lo_order > hi_order:
        return []
    spanned = sorted(
        (
            (order, code)
            for code, order in code_to_order.items()
            if lo_order <= order <= hi_order
        )
    )
    return [code for _, code in spanned]


def sort_by_order(
    codes: Iterable[str], code_to_order: Mapping[str, int]
) -> list[str]:
    """Sort ``codes`` by their stored display order.

    Codes absent from ``code_to_order`` sort last in lexicographic order, so
    the result stays deterministic even when the map is incomplete. Duplicate
    codes are collapsed.

    Args:
        codes: The codes to sort.
        code_to_order: ``{code: order}`` for the codes' axis.

    Returns:
        The de-duplicated codes in display order.
    """
    unique = list(dict.fromkeys(codes))
    ordered = sorted(
        (c for c in unique if c in code_to_order),
        key=lambda c: (code_to_order[c], c),
    )
    unordered = sorted(c for c in unique if c not in code_to_order)
    return ordered + unordered


def build_axis_order_map(
    codes: Iterable[Any], orders: Iterable[Any]
) -> dict[str, int] | None:
    """Build a ``{code: order}`` map from parallel code/order sequences.

    Missing codes (``None``/NaN — a cell that lacks that axis, e.g. a table
    with no sheets) are skipped. Returns ``None`` when the axis is **not fully
    ordered** — any present code lacks an order, or a code maps to two
    different orders — so the caller falls back to string comparison for the
    whole axis and the two orderings are never mixed.

    Args:
        codes: The axis code of each row (may contain ``None``/NaN).
        orders: The matching stored order of each row (may contain ``None``/NaN).

    Returns:
        ``{code: order}`` when every present code has a single integer order,
        else ``None``.
    """
    result: dict[str, int] = {}
    for code, order in zip(codes, orders, strict=False):
        if _is_missing(code):
            continue
        key = str(code)
        if _is_missing(order):
            return None
        value = int(order)
        existing = result.get(key)
        if existing is not None and existing != value:
            return None
        result[key] = value
    return result
