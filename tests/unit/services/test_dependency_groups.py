"""Unit tests for the ``dependency_groups`` section of the script."""

from __future__ import annotations

import pytest

from dpmcore.services.script_document.dependency_groups import (
    DependencyResolver,
    NoDependencyGroup,
    build_dependency_groups,
)
from dpmcore.services.script_document.modules import AT_T, Read, RefDateLag

# Module versions of the scopes: ``ModuleVID -> (ModuleID, code)``. The
# script is for OWN, ModuleID 1.
OWN = (1, "OWN")
FINREP9 = (2, "FINREP9")
FINREP9DP = (3, "FINREP9DP")
COREP_OF = (4, "COREP_OF")
VERSIONS = {10: OWN, 11: OWN, 20: FINREP9, 30: FINREP9DP, 40: COREP_OF}


def _resolver(holders):
    """A resolver for OWN whose tables are held as ``holders`` says."""
    resolver = DependencyResolver(None, 1, "OWN", 1)
    resolver._holders = lambda tables: holders
    resolver._modules = lambda module_vids: VERSIONS
    return resolver


def _read(table, lag=AT_T, branch=()):
    return Read(0, table, frozenset({1}), lag, branch)


def _ref(code, lag=0, unit=None):
    ref = {"code": code, "ref_date_lag": lag}
    if unit:
        ref["ref_date_lag_unit"] = unit
    return ref


def _op(operator, left, right):
    return {operator: {"left": left, "right": right, "decided_by": "scope"}}


class TestRequires:
    def test_reading_the_own_module_needs_nothing_else(self):
        resolver = _resolver({"F_01.01": {OWN}})

        assert resolver.requires([frozenset({10})], [_read("F_01.01")]) == {}

    def test_a_shifted_own_table_needs_the_own_module_then(self):
        resolver = _resolver({"F_01.01": {OWN, FINREP9}})

        requires = resolver.requires(
            [frozenset({10})],
            [_read("F_01.01"), _read("F_01.01", RefDateLag(-1, "A"))],
        )

        assert requires == {"is": _ref("OWN", -1, "A")}

    def test_a_table_of_another_module_needs_that_module(self):
        resolver = _resolver({"F_01.01": {OWN}, "C_01.00": {COREP_OF}})

        requires = resolver.requires(
            [frozenset({10, 40})],
            [_read("F_01.01"), _read("C_01.00", RefDateLag(-1, "Q"))],
        )

        assert requires == {"is": _ref("COREP_OF", -1, "Q")}

    def test_scopes_with_either_module_are_alternatives(self):
        resolver = _resolver({"F_01.01": {FINREP9, FINREP9DP}})

        requires = resolver.requires(
            [frozenset({11, 30}), frozenset({10, 20})], [_read("F_01.01")]
        )

        assert requires == _op("or", _ref("FINREP9"), _ref("FINREP9DP"))

    def test_a_scope_with_two_modules_needs_both(self):
        resolver = _resolver({"F_01.01": {FINREP9}, "C_01.00": {COREP_OF}})

        requires = resolver.requires(
            [frozenset({10, 20, 40})], [_read("F_01.01"), _read("C_01.00")]
        )

        assert requires == _op("and", _ref("COREP_OF"), _ref("FINREP9"))

    def test_a_scope_short_of_a_table_is_no_alternative(self):
        resolver = _resolver({"F_01.01": {FINREP9}, "C_01.00": {COREP_OF}})

        requires = resolver.requires(
            [frozenset({10, 20}), frozenset({10, 20, 40})],
            [_read("F_01.01"), _read("C_01.00")],
        )

        assert requires == _op("and", _ref("COREP_OF"), _ref("FINREP9"))

    def test_a_table_with_no_version_is_left_out(self):
        resolver = _resolver({"F_01.01": {OWN}, "GONE": set()})

        requires = resolver.requires(
            [frozenset({10})], [_read("F_01.01"), _read("GONE")]
        )

        assert requires == {}

    def test_module_references_are_in_canonical_order(self):
        resolver = _resolver({"F_01.01": {OWN}, "C_01.00": {COREP_OF}})
        lags = [
            RefDateLag(-3),
            RefDateLag(1, "Q"),
            RefDateLag(-1, "Q"),
            RefDateLag(-1, "A"),
        ]

        requires = resolver.requires(
            [frozenset({10, 40})],
            [_read("C_01.00")] + [_read("F_01.01", lag) for lag in lags],
        )

        assert requires == _op(
            "and",
            _ref("COREP_OF"),
            _op(
                "and",
                _ref("OWN", -1, "A"),
                _op(
                    "and",
                    _ref("OWN", -1, "Q"),
                    _op("and", _ref("OWN", 1, "Q"), _ref("OWN", -3, "M")),
                ),
            ),
        )

    def test_single_alternatives_come_before_the_others(self):
        resolver = _resolver({"F_01.01": {FINREP9, FINREP9DP, COREP_OF}})

        requires = resolver.requires(
            [frozenset({10, 20, 40}), frozenset({10, 30})],
            [_read("F_01.01")],
        )

        assert requires == _op(
            "or",
            _ref("FINREP9DP"),
            _op("and", _ref("COREP_OF"), _ref("FINREP9")),
        )

    def test_an_alternative_holding_another_adds_nothing(self):
        resolver = _resolver({"F_01.01": {FINREP9, FINREP9DP}})

        requires = resolver.requires(
            [frozenset({10, 20}), frozenset({10, 20, 30})],
            [_read("F_01.01")],
        )

        assert requires == {"is": _ref("FINREP9")}

    def test_a_read_no_lag_describes_has_no_group(self):
        resolver = _resolver({"F_01.01": {OWN}})

        with pytest.raises(NoDependencyGroup, match="F_01.01 at a reference"):
            resolver.requires([frozenset({10})], [_read("F_01.01", None)])

    def test_branches_reading_different_instances_have_no_group(self):
        resolver = _resolver({"F_01.01": {OWN}})

        with pytest.raises(NoDependencyGroup, match="if-then-else branches"):
            resolver.requires(
                [frozenset({10})],
                [
                    _read("F_01.01"),
                    _read("F_01.01", RefDateLag(-1, "Q"), ((1, "then"),)),
                    _read("F_01.01", RefDateLag(-2, "Q"), ((1, "else"),)),
                ],
            )

    def test_one_branch_reading_more_stands_for_both(self):
        resolver = _resolver({"F_01.01": {OWN}})

        requires = resolver.requires(
            [frozenset({10})],
            [
                _read("F_01.01", RefDateLag(-1, "Q"), ((1, "then"),)),
                _read("F_01.01", AT_T, ((1, "else"),)),
            ],
        )

        assert requires == {"is": _ref("OWN", -1, "Q")}

    def test_branches_reading_the_same_instances_keep_them(self):
        resolver = _resolver({"F_01.01": {OWN}})

        requires = resolver.requires(
            [frozenset({10})],
            [
                _read("F_01.01", RefDateLag(-1, "Q"), ((1, "then"),)),
                _read("F_01.01", RefDateLag(-1, "Q"), ((1, "else"),)),
            ],
        )

        assert requires == {"is": _ref("OWN", -1, "Q")}

    def test_branches_reading_own_tables_at_one_date_keep_it(self):
        resolver = _resolver({"F_01.01": {OWN}, "F_02.00": {OWN}})

        requires = resolver.requires(
            [frozenset({10})],
            [
                _read("F_01.01", RefDateLag(-1, "Q"), ((1, "then"),)),
                _read("F_02.00", RefDateLag(-1, "Q"), ((1, "else"),)),
            ],
        )

        assert requires == {"is": _ref("OWN", -1, "Q")}

    def test_branches_reading_tables_of_one_module_keep_it(self):
        resolver = _resolver(
            {"F_01.01": {OWN}, "C_01.00": {COREP_OF}, "C_02.00": {COREP_OF}}
        )

        requires = resolver.requires(
            [frozenset({10, 40})],
            [
                _read("F_01.01"),
                _read("C_01.00", branch=((1, "then"),)),
                _read("C_02.00", branch=((1, "else"),)),
            ],
        )

        assert requires == {"is": _ref("COREP_OF")}

    def test_no_scope_with_the_own_module_has_no_group(self):
        resolver = _resolver({"C_01.00": {COREP_OF}})

        with pytest.raises(NoDependencyGroup, match="None of its scopes"):
            resolver.requires([frozenset({40})], [_read("C_01.00")])

    def test_no_scope_holding_every_table_has_no_group(self):
        resolver = _resolver({"C_01.00": {COREP_OF}})

        with pytest.raises(NoDependencyGroup, match="No scope with module"):
            resolver.requires([frozenset({10, 20})], [_read("C_01.00")])


class TestBuildDependencyGroups:
    def test_validations_with_the_same_requires_share_a_group(self):
        corep_of = {"is": _ref("COREP_OF")}
        shifted = {"is": _ref("OWN", -1, "A")}

        groups = build_dependency_groups(
            {"v1": corep_of, "v2": {}, "v3": corep_of, "v4": shifted, "v5": {}}
        )

        assert groups == {
            "G1": {"requires": {}, "validations": ["v2", "v5"]},
            "G2": {"requires": corep_of, "validations": ["v1", "v3"]},
            "G3": {"requires": shifted, "validations": ["v4"]},
        }

    def test_no_validations_no_groups(self):
        assert build_dependency_groups({}) == {}
