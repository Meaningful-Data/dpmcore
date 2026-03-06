# dpmcore Specification — API Messages & Containment Model

## 1. Overview

This document defines:

1. **The containment model**: Which entities are independently addressable
   and which are always returned within a parent.
2. **The JSON message format**: The exact structure of API responses for
   each artefact type.

## 2. Containment Model

Following SDMX conventions, entities are classified into three tiers:

- **Maintainable**: Independently addressable via their own URL. These are
  the top-level REST resources.
- **Contained**: Exist only within a parent. Returned inline or via
  sub-resource URLs.
- **Internal**: Never exposed in the API. Used internally by the ORM.

### 2.1 SDMX Analogy

| SDMX Concept | DPM Equivalent |
|--------------|----------------|
| Codelist (MaintainableArtefact) | Category |
| Code (Item within Codelist) | Item (within Category) |
| DataStructureDefinition | Table |
| Component (within DSD) | Header, Cell (within Table) |
| ConceptScheme | *(no direct equivalent — Properties serve this role)* |
| Concept | Property |
| Dataflow | Module |
| Agency | Organisation |

### 2.2 Maintainable Artefacts (Top-Level)

These get their own `/api/v1/structure/{type}/{owner}/{id}/{version}` URL:

| # | Type | URL Segment | Contains (inline) |
|---|------|-------------|-------------------|
| 1 | **Category** | `category` | Items, SubCategories (with their items) |
| 2 | **Property** | `property` | DataType info, PropertyCategories |
| 3 | **Context** | `context` | ContextCompositions (property + item bindings) |
| 4 | **Table** | `table` | TableVersion → Headers, Cells, TableVersionCells |
| 5 | **Variable** | `variable` | VariableVersion → Property, SubCategory, Context refs |
| 6 | **Operation** | `operation` | OperationVersion → expression, scopes, metadata |
| 7 | **Framework** | `framework` | OperationCodePrefixes |
| 8 | **Module** | `module` | ModuleVersion → table compositions, parameters |
| 9 | **Release** | `release` | *(standalone — no children)* |
| 10 | **Organisation** | `organisation` | *(standalone — no children)* |
| 11 | **TableGroup** | `tablegroup` | Child groups, table references |
| 12 | **DataType** | `datatype` | Child types (hierarchy) |
| 13 | **Operator** | `operator` | OperatorArguments |

### 2.3 Contained Entities

These are **never** independently addressable at the top level. They are
returned inline within their parent or via sub-resource URLs:

| Entity | Parent | Access Pattern |
|--------|--------|----------------|
| Item | Category | Inline in Category; sub-resource: `/category/{owner}/{id}/.../items/{itemCode}` |
| SubCategory | Category | Inline in Category; sub-resource: `/category/{owner}/{id}/.../subcategories/{subCode}` |
| SubCategoryVersion | SubCategory | Inline |
| SubCategoryItem | SubCategoryVersion | Inline |
| Header | Table | Inline in Table |
| HeaderVersion | Header | Inline |
| Cell | Table | Inline in Table |
| TableVersionCell | TableVersion | Inline |
| TableVersionHeader | TableVersion | Inline |
| TableVersion | Table | Via `{version}` path segment |
| TableAssociation | TableVersion | Inline or via `?references=` |
| OperationVersion | Operation | Via `{version}` path segment |
| OperationVersionData | OperationVersion | Inline |
| OperationNode | OperationVersion | Inline (expression tree) |
| OperationScope | OperationVersion | Inline |
| OperationScopeComposition | OperationScope | Inline |
| OperandReference | OperationNode | Inline |
| ModuleVersion | Module | Via `{version}` path segment |
| ModuleVersionComposition | ModuleVersion | Inline |
| ModuleParameters | ModuleVersion | Inline |
| VariableVersion | Variable | Via `{version}` path segment |
| VariableCalculation | Variable | Inline |
| CompoundKey | *(shared)* | Inline wherever referenced |
| KeyComposition | CompoundKey | Inline |
| ItemCategory | Category / Item | Inline (release-versioned join) |
| PropertyCategory | Property / Category | Inline |
| ContextComposition | Context | Inline |
| CompoundItemContext | Context | Inline |
| TableGroupComposition | TableGroup | Inline |
| OperationCodePrefix | Framework | Inline |

### 2.4 Internal / Never Exposed

| Entity | Reason |
|--------|--------|
| Concept | Embedded as `conceptGuid` field in every entity |
| ConceptRelation | Internal metadata |
| DpmClass / DpmAttribute | Metamodel schema (admin only) |
| Translation | Inline via `Accept-Language` content negotiation |
| Changelog | Operational — separate audit endpoint |
| VariableGeneration | Batch job tracking — operational endpoint |
| User / Role / UserRole | Admin — separate admin endpoint |

### 2.5 Removed from Top-Level

These were listed as top-level artefact types in the initial design but are
now **demoted** to contained entities:

| Former Type | Now | Rationale |
|-------------|-----|-----------|
| `item` | Contained in Category | Items are codes within a codelist. In SDMX you never `GET /code` — you `GET /codelist` and read its codes. |
| `subcategory` | Contained in Category | Alternative groupings within a Category |
| `header` | Contained in Table | Structural parts of a Table. Users never browse headers independently. |
| `cell` | Contained in Table | Intersection points within a Table. Meaningless outside Table context. |
| `compounditem` | Contained in Context | Value combinations within a Context |

## 3. Response Envelope

All API responses use a simple, consistent envelope:

### 3.1 Success with Data

```json
{
  "meta": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "prepared": "2025-03-15T10:30:00Z",
    "contentLanguage": "en",
    "sender": "dpmcore",
    "release": "3.4",
    "pagination": {
      "totalCount": 42,
      "offset": 0,
      "limit": 100
    }
  },
  "data": { ... }
}
```

- `meta.id`: Unique request ID (UUID)
- `meta.prepared`: Response timestamp
- `meta.contentLanguage`: Language of labels/descriptions
- `meta.sender`: Server identity
- `meta.release`: Active release filter (if applied)
- `meta.pagination`: Only present when paginated

### 3.2 Success with No Results

```
HTTP/1.1 204 No Content
```

Empty body. Following SDMX convention, "no matching results" is 204, not 404.

### 3.3 Error

```json
{
  "meta": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "prepared": "2025-03-15T10:30:00Z"
  },
  "errors": [
    {
      "code": 400,
      "title": "Bad Request",
      "detail": "Unknown artefact type: 'tablezz'"
    }
  ]
}
```

### 3.4 Collection vs Single Resource

When the response contains **multiple artefacts**, `data` is an object with
a key matching the artefact type (plural):

```json
{
  "meta": { ... },
  "data": {
    "categories": [ ... ]
  }
}
```

When the response contains a **single artefact** (specific ID requested),
`data` is the artefact directly:

```json
{
  "meta": { ... },
  "data": {
    "category": { ... }
  }
}
```

## 4. JSON Message Formats

### 4.1 Common Patterns

**Versioned artefact pattern**: All versioned entities share this structure:

```json
{
  "id": 123,
  "code": "ABC",
  "name": "Human-readable name",
  "description": "Optional description",
  "version": {
    "code": "3.2",
    "startRelease": "3.0",
    "endRelease": null
  },
  "conceptGuid": "550e8400-..."
}
```

**Reference pattern**: When referencing another entity (not inlining it),
use a compact reference:

```json
{
  "ref": {
    "type": "category",
    "id": 456,
    "code": "CL_SECTOR"
  }
}
```

**`detail` parameter effects on all types:**

| `detail` value | Behaviour |
|----------------|-----------|
| `full` | All attributes + inline contained entities |
| `allstubs` | Only `id`, `code`, `name`, `version` |
| `referencestubs` | Full for requested type, stubs for referenced types |

### 4.2 Category

A Category is the DPM equivalent of an SDMX Codelist. It contains Items
(codes) and SubCategories (alternative groupings).

**`GET /api/v1/structure/category/EBA/CL_SECTOR`** — `detail=full`:

```json
{
  "meta": { ... },
  "data": {
    "category": {
      "id": 1,
      "code": "CL_SECTOR",
      "name": "Sector classification",
      "description": "Classification of institutional sectors",
      "isEnumerated": true,
      "isSuperCategory": false,
      "isActive": true,
      "conceptGuid": "abc-123",
      "items": [
        {
          "id": 101,
          "code": "SECT_01",
          "name": "Central banks",
          "description": null,
          "isDefault": false,
          "signature": null
        },
        {
          "id": 102,
          "code": "SECT_02",
          "name": "General governments",
          "description": null,
          "isDefault": false,
          "signature": null
        }
      ],
      "subcategories": [
        {
          "id": 10,
          "code": "SC_SECTOR_MAIN",
          "name": "Main sector grouping",
          "version": {
            "vid": 20,
            "startRelease": "3.0",
            "endRelease": null
          },
          "items": [
            {
              "itemCode": "SECT_01",
              "order": 1,
              "label": null,
              "parentItemCode": null
            },
            {
              "itemCode": "SECT_02",
              "order": 2,
              "label": null,
              "parentItemCode": null
            }
          ]
        }
      ]
    }
  }
}
```

**`detail=allstubs`:**

```json
{
  "meta": { ... },
  "data": {
    "category": {
      "id": 1,
      "code": "CL_SECTOR",
      "name": "Sector classification",
      "itemCount": 45
    }
  }
}
```

### 4.3 Property

```json
{
  "meta": { ... },
  "data": {
    "property": {
      "id": 50,
      "code": "MI1",
      "name": "Main metric indicator",
      "isComposite": false,
      "isMetric": true,
      "dataType": {
        "id": 3,
        "code": "Monetary",
        "name": "Monetary"
      },
      "valueLength": null,
      "periodType": null,
      "conceptGuid": "def-456",
      "categories": [
        {
          "ref": { "type": "category", "id": 1, "code": "CL_MI" },
          "startRelease": "3.0",
          "endRelease": null
        }
      ]
    }
  }
}
```

### 4.4 Context

```json
{
  "meta": { ... },
  "data": {
    "context": {
      "id": 10,
      "signature": "MI1|SC1|CT2",
      "conceptGuid": "ghi-789",
      "compositions": [
        {
          "property": {
            "ref": { "type": "property", "id": 50, "code": "MI1" }
          },
          "item": null
        },
        {
          "property": {
            "ref": { "type": "property", "id": 51, "code": "SC1" }
          },
          "item": {
            "ref": { "type": "item", "id": 101, "code": "SECT_01" }
          }
        }
      ]
    }
  }
}
```

### 4.5 Table

The Table message is the richest. At `detail=full`, it includes the active
TableVersion with all structural children (headers, cells).

**`GET /api/v1/structure/table/EBA/F_01.01`** — `detail=full`:

```json
{
  "meta": { ... },
  "data": {
    "table": {
      "id": 200,
      "code": "F_01.01",
      "name": "Balance Sheet - Assets",
      "description": "...",
      "isAbstract": false,
      "hasOpenColumns": false,
      "hasOpenRows": true,
      "hasOpenSheets": false,
      "conceptGuid": "tbl-001",
      "version": {
        "vid": 300,
        "code": "F_01.01_v3.2",
        "name": "Balance Sheet - Assets v3.2",
        "startRelease": "3.0",
        "endRelease": null,
        "property": {
          "ref": { "type": "property", "id": 50, "code": "MI1" }
        },
        "context": {
          "ref": { "type": "context", "id": 10, "signature": "MI1|SC1" }
        }
      },
      "headers": {
        "columns": [
          {
            "id": 401,
            "direction": "x",
            "isKey": false,
            "version": {
              "vid": 501,
              "code": "C010",
              "label": "Carrying amount",
              "property": {
                "ref": { "type": "property", "id": 50, "code": "MI1" }
              },
              "subcategory": null,
              "startRelease": "3.0",
              "endRelease": null
            }
          }
        ],
        "rows": [
          {
            "id": 402,
            "direction": "y",
            "isKey": true,
            "version": {
              "vid": 502,
              "code": "R010",
              "label": "Cash and cash balances",
              "property": null,
              "subcategory": {
                "ref": { "type": "subcategory", "id": 10, "code": "SC_ROW_F01" }
              },
              "startRelease": "3.0",
              "endRelease": null
            }
          }
        ],
        "sheets": []
      },
      "cells": [
        {
          "id": 600,
          "code": "C010_R010",
          "column": "C010",
          "row": "R010",
          "sheet": null,
          "isNullable": false,
          "isExcluded": false,
          "isVoid": false,
          "sign": null,
          "variable": {
            "ref": { "type": "variable", "id": 700, "code": "v1234" }
          }
        }
      ]
    }
  }
}
```

**`detail=allstubs`:**

```json
{
  "meta": { ... },
  "data": {
    "table": {
      "id": 200,
      "code": "F_01.01",
      "name": "Balance Sheet - Assets",
      "versionCode": "F_01.01_v3.2",
      "columnCount": 5,
      "rowCount": 32,
      "cellCount": 120
    }
  }
}
```

### 4.6 Variable

**`GET /api/v1/structure/variable/EBA/v1234`**:

```json
{
  "meta": { ... },
  "data": {
    "variable": {
      "id": 700,
      "code": "v1234",
      "name": "Cash and cash balances - Carrying amount",
      "type": "F",
      "typeName": "Fact",
      "conceptGuid": "var-001",
      "version": {
        "vid": 800,
        "code": "v1234",
        "name": "Cash and cash balances - Carrying amount",
        "isMultiValued": false,
        "startRelease": "3.0",
        "endRelease": null,
        "property": {
          "ref": { "type": "property", "id": 50, "code": "MI1" }
        },
        "subcategory": {
          "ref": { "type": "subcategory", "id": 10, "code": "SC_F01" }
        },
        "context": {
          "ref": { "type": "context", "id": 10, "signature": "MI1|SC1" }
        }
      }
    }
  }
}
```

### 4.7 Operation

**`GET /api/v1/structure/operation/EBA/e0123`**:

```json
{
  "meta": { ... },
  "data": {
    "operation": {
      "id": 900,
      "code": "e0123",
      "type": "V",
      "typeName": "Validation",
      "source": "EBA",
      "conceptGuid": "op-001",
      "groupOperation": null,
      "version": {
        "vid": 1000,
        "expression": "v1234 = v5678 + v9012",
        "description": "Assets must equal sum of components",
        "endorsement": "Final",
        "isVariantApproved": true,
        "startRelease": "3.0",
        "endRelease": null,
        "precondition": null,
        "severityOperation": null,
        "data": {
          "error": "Assets do not reconcile",
          "errorCode": "E0123",
          "isApplying": true,
          "proposingStatus": null
        },
        "scopes": [
          {
            "id": 1100,
            "isActive": true,
            "severity": "error",
            "fromSubmissionDate": null,
            "modules": [
              {
                "ref": { "type": "module", "id": 50, "code": "FINREP_IND" },
                "vid": 60
              }
            ]
          }
        ]
      }
    }
  }
}
```

**Note**: The expression tree (OperationNodes) is NOT included by default
at `detail=full` because it can be very large and is primarily needed by the
DPM-XL engine, not by API consumers. It is available via:

```
GET /api/v1/structure/operation/EBA/e0123?references=expressionTree
```

### 4.8 Framework

**`GET /api/v1/structure/framework/EBA/FINREP`**:

```json
{
  "meta": { ... },
  "data": {
    "framework": {
      "id": 1,
      "code": "FINREP",
      "name": "Financial Reporting",
      "description": "...",
      "conceptGuid": "fw-001",
      "codePrefixes": [
        { "id": 1, "code": "e", "listName": "FINREP validations" },
        { "id": 2, "code": "c", "listName": "FINREP calculations" }
      ]
    }
  }
}
```

With `?references=children`:

```json
{
  "meta": { ... },
  "data": {
    "framework": {
      "id": 1,
      "code": "FINREP",
      "name": "Financial Reporting",
      "description": "...",
      "codePrefixes": [ ... ],
      "modules": [
        {
          "id": 50,
          "code": "FINREP_IND",
          "name": "FINREP Individual",
          "versionCode": "3.2",
          "tableCount": 47
        }
      ]
    }
  }
}
```

### 4.9 Module

**`GET /api/v1/structure/module/EBA/FINREP_IND`**:

```json
{
  "meta": { ... },
  "data": {
    "module": {
      "id": 50,
      "code": "FINREP_IND",
      "conceptGuid": "mod-001",
      "framework": {
        "ref": { "type": "framework", "id": 1, "code": "FINREP" }
      },
      "version": {
        "vid": 60,
        "code": "FINREP_IND",
        "name": "FINREP Individual",
        "description": "...",
        "versionNumber": "3.2",
        "fromReferenceDate": "2024-01-01",
        "toReferenceDate": null,
        "startRelease": "3.0",
        "endRelease": null,
        "tables": [
          {
            "ref": { "type": "table", "id": 200, "code": "F_01.01" },
            "vid": 300,
            "order": 1
          },
          {
            "ref": { "type": "table", "id": 201, "code": "F_01.02" },
            "vid": 301,
            "order": 2
          }
        ],
        "parameters": [
          {
            "ref": { "type": "variable", "id": 700, "code": "v1234" },
            "vid": 800
          }
        ]
      }
    }
  }
}
```

### 4.10 Release

**`GET /api/v1/structure/release`**:

```json
{
  "meta": { ... },
  "data": {
    "releases": [
      {
        "id": 5,
        "code": "3.4",
        "date": "2024-06-01",
        "description": "EBA DPM Release 3.4",
        "status": "Final",
        "isCurrent": true,
        "conceptGuid": "rel-001"
      },
      {
        "id": 4,
        "code": "3.3",
        "date": "2024-01-01",
        "description": "EBA DPM Release 3.3",
        "status": "Final",
        "isCurrent": false,
        "conceptGuid": "rel-002"
      }
    ]
  }
}
```

### 4.11 Organisation

```json
{
  "meta": { ... },
  "data": {
    "organisation": {
      "id": 1,
      "name": "EBA",
      "acronym": "EBA",
      "idPrefix": "eba",
      "conceptGuid": "org-001"
    }
  }
}
```

### 4.12 TableGroup

```json
{
  "meta": { ... },
  "data": {
    "tableGroup": {
      "id": 10,
      "code": "FINREP_TABLES",
      "name": "FINREP Table Group",
      "type": "reporting",
      "startRelease": "3.0",
      "endRelease": null,
      "parentGroup": null,
      "childGroups": [
        {
          "id": 11,
          "code": "FINREP_BS",
          "name": "Balance Sheet Tables"
        }
      ],
      "tables": [
        {
          "ref": { "type": "table", "id": 200, "code": "F_01.01" },
          "order": 1
        }
      ]
    }
  }
}
```

### 4.13 DataType

```json
{
  "meta": { ... },
  "data": {
    "datatypes": [
      {
        "id": 1,
        "code": "Monetary",
        "name": "Monetary",
        "isActive": true,
        "parent": null
      },
      {
        "id": 2,
        "code": "Percentage",
        "name": "Percentage",
        "isActive": true,
        "parent": {
          "ref": { "type": "datatype", "id": 5, "code": "Decimal" }
        }
      }
    ]
  }
}
```

### 4.14 Operator

```json
{
  "meta": { ... },
  "data": {
    "operators": [
      {
        "id": 1,
        "name": "Addition",
        "symbol": "+",
        "type": "arithmetic",
        "arguments": [
          { "id": 1, "order": 1, "name": "left", "isMandatory": true },
          { "id": 2, "order": 2, "name": "right", "isMandatory": true }
        ]
      }
    ]
  }
}
```

## 5. The `references` Parameter — Dependency Graph

The `references` parameter controls how far to traverse the dependency graph
beyond the inline containment defaults.

### 5.1 Reference Directions

```
ancestors ← parents ← [ARTEFACT] → children → descendants
                           ↕
                          all
```

### 5.2 Reference Behaviour by Artefact Type

| Artefact | `?references=children` | `?references=parents` | Specific types |
|----------|------------------------|----------------------|----------------|
| **Category** | *(default already includes Items, SubCategories)* | — | `?references=property` → Properties using this Category |
| **Property** | Items (via its Category) | Category | `?references=variable` → Variables using this Property; `?references=table` → Tables |
| **Context** | CompoundItems | — | `?references=variable` → Variables; `?references=table` → Tables |
| **Table** | *(default already includes Headers, Cells)* | Module, TableGroup | `?references=variable` → all Variables; `?references=operation` → Operations scoped to this table |
| **Variable** | — | Table, Module | `?references=operation` → Operations referencing this Variable |
| **Operation** | — | Module | `?references=variable` → Variables in expression; `?references=table` → Tables in scope |
| **Framework** | Modules (stubs) | — | — |
| **Module** | Tables (stubs), Operations (stubs) | Framework | `?references=variable` → Variables; `?references=table` → full Tables |
| **Release** | — | — | `?references=module` → ModuleVersions active in release |
| **TableGroup** | Tables, child groups | Parent group | — |

### 5.3 Stub Format for References

When artefacts are included via `references`, they use the stub format
(regardless of the `detail` parameter for the main artefact):

```json
{
  "ref": { "type": "table", "id": 200, "code": "F_01.01" },
  "name": "Balance Sheet - Assets",
  "versionCode": "3.2"
}
```

To get full details of a referenced artefact, the consumer follows the
reference to its own URL.

## 6. Sub-Resource URLs

For contained entities that consumers may want to address individually
(primarily for deep linking and partial fetches):

```
GET /api/v1/structure/category/{owner}/{id}/{version}/items
GET /api/v1/structure/category/{owner}/{id}/{version}/items/{itemCode}
GET /api/v1/structure/category/{owner}/{id}/{version}/subcategories
GET /api/v1/structure/category/{owner}/{id}/{version}/subcategories/{subCode}

GET /api/v1/structure/table/{owner}/{id}/{version}/headers
GET /api/v1/structure/table/{owner}/{id}/{version}/cells
GET /api/v1/structure/table/{owner}/{id}/{version}/cells/{cellCode}

GET /api/v1/structure/context/{owner}/{id}/{version}/compositions
GET /api/v1/structure/context/{owner}/{id}/{version}/members

GET /api/v1/structure/operation/{owner}/{id}/{version}/expression-tree
GET /api/v1/structure/operation/{owner}/{id}/{version}/scopes

GET /api/v1/structure/module/{owner}/{id}/{version}/tables
GET /api/v1/structure/module/{owner}/{id}/{version}/parameters
GET /api/v1/structure/module/{owner}/{id}/{version}/operations
```

These return the same JSON fragments that would appear inline in the parent's
`detail=full` response, but isolated for targeted access.

## 7. Inline vs Reference Decision Rules

The guiding rules for whether to inline or reference:

| Rule | Inline | Reference |
|------|--------|-----------|
| **Structural child** with no independent identity | Always inline | — |
| **Versioned child** (e.g., TableVersion within Table) | Active version inline | Other versions via `?references=` |
| **Foreign entity** used by this artefact | — | Always reference (stub) |
| **Foreign entity** at `?references=children/all` | — | Stub (follow link for full) |
| **Expression tree** (OperationNodes) | Not by default (large) | Via `?references=expressionTree` |

## 8. Design Rationale

### Why Category contains Items (not separate)

In SDMX, you never `GET /code/A` independently — you `GET /codelist/CL_FREQ`
and read code `A` within it. Similarly, DPM Items only make sense within their
Category. A code "FR" could appear in multiple Categories (countries,
currencies, etc.). The Category provides the disambiguation context.

### Why Table contains Headers and Cells

Headers and Cells are structural parts of a Table, like columns and rows in
a spreadsheet. They have no meaning outside their Table. A Header code "C010"
could exist in many Tables. The Table provides the context.

### Why Operation does NOT inline its expression tree by default

Expression trees (OperationNodes) can have dozens or hundreds of nodes. Most
API consumers want the expression string, scope, and metadata — not the full
AST. The tree is available on demand via `?references=expressionTree` or the
sub-resource URL.

### Why stubs for cross-references

Full inlining of cross-references leads to combinatorial explosion. A Module
references many Tables, each Table has many Cells, each Cell has a Variable…
Stubs keep responses focused. Consumers follow references to get full details,
which is also cache-friendly.
