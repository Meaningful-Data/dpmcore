# DPM-XL multi-sub serialization — design check

**Audience:** adam-engine maintainer
**Asker:** dpmcore (Andrés)
**Status:** draft for discussion, not yet merged

## Background

DPM-XL is being extended so the `sub` clause accepts multiple substitutions:

```
{tT, r010}[sub c0010 = "ES", c0020 = "FR"]
```

Today only a single `key = value` is allowed. The grammar/AST change lives in
**dpmcore PR #57** (`a2` → `cr-48/grammar-docs-consistency`):
<https://github.com/Meaningful-Data/dpmcore/pull/57>.

In the dpmcore AST the parser builds `SubOp(operand, substitutions:
list[SubAssignment])`. The open question is **what JSON dpmcore should emit
on the wire so adam-engine can consume it without regressions.**

## adam-engine contract today

From `crates/dpm-ml-script/schema/dpm-ml-script.json` (ast_SubClauseOp):

```json
{
  "additionalProperties": false,
  "required": ["class_name", "operand", "condition"],
  "properties": {
    "class_name": { "const": "SubClauseOp" },
    "operand":    { "$ref": "#/definitions/ast_node" },
    "condition":  { "$ref": "#/definitions/ast_node" }
  }
}
```

`SubOperator` in `crates/dpm-ml-script/src/ast/nodes.rs`:

```rust
pub struct SubOperator {
    pub operand:   Box<Node>,
    pub condition: Box<Node>,
}
```

The interpreter (`src/interpreter/analyzer.rs:visit_sub`) recurses into
`operand`, then evaluates `condition` via `Operator::sub_expression`, which
filters + drops the dimension.

Also noted: the TODO in `src/dpm/operators/old/sub.rs:17`:

> `// TODO: Refactor once script change to adapt several sub clauses`

So multi-sub was already anticipated on your side; this is the moment to
decide the wire format.

I grepped `data/ECB/scripts/*.json` — **zero existing multi-sub usages**.
This PR is paving new ground; no backfill required for existing scripts.

---

## Option A — chained `SubClauseOp` (left-deep nesting)

dpmcore emits one `SubClauseOp` per substitution, nested via `operand`.
Outermost wraps the **last** substitution; innermost wraps the original
recordset and the **first** substitution.

Example for `X[sub a = "ES", b = "FR"]`:

```json
{
  "class_name": "SubClauseOp",
  "operand": {
    "class_name": "SubClauseOp",
    "operand": <X>,
    "condition": {
      "class_name": "BinOp", "op": "=",
      "left":  { "class_name": "Dimension", "dimension_code": "a" },
      "right": { "class_name": "Scalar", "scalar_type": "String", "value": "ES" }
    }
  },
  "condition": {
    "class_name": "BinOp", "op": "=",
    "left":  { "class_name": "Dimension", "dimension_code": "b" },
    "right": { "class_name": "Scalar", "scalar_type": "String", "value": "FR" }
  }
}
```

**Evaluation flow** (your `visit_sub` as written today):

1. `visit_node(outer.operand)` → recurses to inner SubClauseOp.
2. Inner: `visit_node(X)` → filter by `a = "ES"` → drop dimension `a`.
3. Outer: filter the result by `b = "FR"` → drop dimension `b`.

Left-to-right order matches the source syntax.

**Pros**
- **No schema change** on adam-engine.
- **No interpreter change** on adam-engine — existing recursion handles it.
- Single-substitution wire format is unchanged (100% backwards compatible).
- Each level stays "filter + drop one dimension"; `sub_expression` keeps its
  current shape.

**Cons**
- Original combined syntax is lost in the JSON tree — debug print of the
  AST won't reproduce `sub a=1, b=2` directly.
- N substitutions = N nested objects (slightly verbose for humans reading
  the JSON, no impact on the engine).
- Duplicate-key error surfaces deep in evaluation: `sub a=1, a=2` would
  trigger your `sub_expression` "condition is not a subset" error
  (`sub.rs:48-66`) because the first iteration drops `a`. Workaround:
  dpmcore can reject duplicates at the semantic-analysis stage and never
  emit such JSON. (See open question #4.)

---

## Option B — flat `conditions` list

Schema change:

```json
"ast_SubClauseOp": {
  "additionalProperties": false,
  "required": ["class_name", "operand", "conditions"],
  "properties": {
    "class_name": { "const": "SubClauseOp" },
    "operand":    { "$ref": "#/definitions/ast_node" },
    "conditions": {
      "type":  "array",
      "items": { "$ref": "#/definitions/ast_node" },
      "minItems": 1
    }
  }
}
```

dpmcore emits:

```json
{
  "class_name": "SubClauseOp",
  "operand": <X>,
  "conditions": [
    { "class_name": "BinOp", "op": "=",
      "left":  { "class_name": "Dimension", "dimension_code": "a" },
      "right": { "class_name": "Scalar", "scalar_type": "String", "value": "ES" } },
    { "class_name": "BinOp", "op": "=",
      "left":  { "class_name": "Dimension", "dimension_code": "b" },
      "right": { "class_name": "Scalar", "scalar_type": "String", "value": "FR" } }
  ]
}
```

**Pros**
- One-to-one with source syntax — easier to read/debug.
- Resolves the `sub.rs:17` TODO directly.
- Cleaner duplicate-key handling: schema or interpreter can reject duplicates
  before evaluating.
- Single AST node for the whole clause (matches dpmcore's internal AST).

**Cons**
- **Schema change** on adam-engine.
- **Interpreter rewrite**: `visit_sub` becomes a loop over `conditions`, each
  applying filter+drop sequentially. `Operator::sub_expression` either
  accepts a list, or the loop sits in `visit_sub`.
- Existing single-sub JSON must be migrated to the new shape, or adam-engine
  must accept both during a deprecation window (`condition` OR `conditions`).
- Production scripts (`data/ECB/scripts/*.json`) all use the current
  `condition` shape — they'd need regeneration or a compatibility layer.

---

## Side-by-side summary

| Aspect                         | Option A (chained)             | Option B (flat list)              |
| ------------------------------ | ------------------------------ | --------------------------------- |
| Schema change                  | No                             | Yes                               |
| Interpreter change             | No                             | Yes (small loop)                  |
| Existing scripts compatible    | Yes                            | Need migration or dual-read       |
| dpmcore emitter complexity     | Slightly more (left-fold)      | Simple (1 dict + list)            |
| Human-readable JSON            | Nested, verbose                | Flat, mirrors source              |
| Duplicate-key UX               | Needs guard in dpmcore         | Naturally rejectable in schema    |
| Resolves `sub.rs:17` TODO      | No (defers it)                 | Yes                               |

---

## Open questions for you

1. **Is Option A acceptable for the medium term?** It's the path of least
   resistance — dpmcore lands PR #57 immediately, adam-engine takes no
   change.
2. **Evaluation-order sanity check**: my reading of `analyzer.rs:1104` is
   that outer `SubClauseOp`'s `operand` is visited first, which recurses to
   the innermost. So for `sub a, b`, the `a` filter runs first and drops
   `a`, then `b` runs on the result. Same observable behavior as a
   left-to-right flat list. Agree?
3. **If you'd prefer Option B**, what's the rough effort on your side
   (schema + interpreter + script migration)? dpmcore can emit either; we
   just want alignment before merging PR #57.
4. **Duplicate dimensions** (`sub a = 1, a = 2`): reject at dpmcore parse
   time with a clear error? Or pass through and let adam-engine surface the
   subset error? My preference is parse-time rejection in dpmcore; cheaper
   and clearer.
5. **Non-public scripts**: I checked `data/ECB/scripts/*.json` and saw zero
   multi-sub usages. Anything internal I should be aware of?

## What's *not* changing either way

- DPM-XL grammar/parser is locked in PR #57.
- Single-substitution wire format is unchanged.
- AST class names (`SubClauseOp`, `BinOp`, `Dimension`, `Scalar`,
  `ItemReference`) and their existing fields are unchanged.

## My recommendation

Ship **Option A** now (zero engine work, no risk to existing scripts), and
park Option B as a follow-up if/when multi-sub usage becomes common enough
that flat JSON pays for itself. The `sub.rs:17` TODO can stay until then.

Happy to flip to Option B if you'd rather solve it once.
