"""DPM-XL Type System.

Type definitions, type checking, and type promotion rules for DPM-XL expressions.

Submodules `scalar`, `promotion`, and `time` export overlapping names
(e.g. ``TimePeriod`` exists in both ``scalar`` and ``time``). Explicit
imports from the submodules are preferred over wildcard re-exports from
this package.
"""
