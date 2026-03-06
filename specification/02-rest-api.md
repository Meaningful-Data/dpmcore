# dpmcore Specification — Layer 2: REST API

## 1. Overview

The REST API provides HTTP access to DPM structures and services. It follows
SDMX REST API conventions adapted for the DPM domain, making it familiar to
users of statistical data APIs.

## 2. Design Principles

| Principle | Description |
|-----------|-------------|
| **SDMX-inspired URL patterns** | Hierarchical paths with `/{type}/{owner}/{id}/{version}` |
| **Convention over configuration** | Sensible defaults; trailing path segments can be omitted |
| **Content negotiation** | JSON primary format, XML optional |
| **204 for empty results** | Following SDMX, empty results return 204 (not 404) |
| **Consistent filtering** | `detail` and `references` parameters across all structure endpoints |
| **OpenAPI auto-documentation** | FastAPI generates interactive docs automatically |

## 3. Technology

- **Standalone mode**: FastAPI with Uvicorn
- **Django mode**: Django REST Framework views that delegate to the same
  service layer
- Both share the same URL structure and response format

## 4. Base URL Structure

```
/api/v1/                         # API version prefix
├── structure/                    # Structural metadata (DPM artefacts)
│   ├── {artefactType}/          # Specific artefact type
│   │   ├── {owner}/             # Organisation owner
│   │   │   ├── {id}/           # Resource ID (code)
│   │   │   │   └── {version}/  # Version code
│   │   │   └── ...
│   │   └── ...
│   └── ...
├── dpm-xl/                      # DPM-XL expression services
│   ├── validate/
│   ├── ast/
│   ├── scopes/
│   └── script/
├── query/                       # Pre-built complex queries
│   ├── data-dictionary/
│   ├── explorer/
│   └── hierarchy/
└── system/                      # System endpoints
    ├── health/
    ├── info/
    └── releases/
```

## 5. Structure Endpoints

### 5.1 Artefact Types

The `{artefactType}` path segment accepts the following **maintainable**
(top-level) artefact types. For the full containment model, including which
entities are inline within these types, see
[06-api-messages.md](06-api-messages.md).

| Artefact Type | DPM Entity | SDMX Analogy | Contains (inline) |
|---------------|------------|--------------|-------------------|
| `category` | Category | Codelist | Items, SubCategories |
| `property` | Property | Concept | DataType, PropertyCategories |
| `context` | Context | ContentConstraint | Compositions (property + item bindings) |
| `table` | Table + TableVersion | DSD | Headers, Cells, TableVersionCells |
| `variable` | Variable + VariableVersion | Component | Property, SubCategory, Context refs |
| `operation` | Operation + OperationVersion | TransformationScheme | Expression, scopes, metadata |
| `framework` | Framework | StructureSet | CodePrefixes |
| `module` | Module + ModuleVersion | Dataflow | Table compositions, parameters |
| `release` | Release | *(version milestone)* | — |
| `organisation` | Organisation | Agency | — |
| `tablegroup` | TableGroup | CategoryScheme | Child groups, table refs |
| `datatype` | DataType | *(reference data)* | Child types |
| `operator` | Operator | *(reference data)* | Arguments |
| `structure` | *(wildcard)* | *(wildcard)* | *(matches any type)* |

**Contained entities** (Items, SubCategories, Headers, Cells, etc.) are
accessed through their parent or via sub-resource URLs — they do NOT have
their own top-level artefact type. See [06-api-messages.md §6](06-api-messages.md#6-sub-resource-urls).

### 5.2 URL Pattern

```
GET /api/v1/structure/{artefactType}/{owner}/{id}/{version}
```

**Path parameters:**

| Parameter | Default | Wildcard | Description |
|-----------|---------|----------|-------------|
| `artefactType` | *(required)* | `structure` | Type of artefact |
| `owner` | `*` (all) | `*` | Organisation code |
| `id` | `*` (all) | `*` | Resource code/ID |
| `version` | `~` (latest) | `*` (all), `+` (latest stable), `~` (latest any) | Version code |

**Omission rule:** Trailing path parameters that use their defaults can be
omitted. So `/api/v1/structure/table` is equivalent to
`/api/v1/structure/table/*/*/*`.

**Multiple values:** Path parameters accept comma-separated values for OR
logic: `/api/v1/structure/table/EBA/C_01.00,C_02.00`.

### 5.3 Query Parameters

#### `detail` — Response granularity

| Value | Description |
|-------|-------------|
| `full` (default) | Complete artefact with all attributes and nested objects |
| `allstubs` | Only code, name, and version for all artefacts |
| `referencestubs` | Full detail for requested artefacts, stubs for referenced ones |
| `raw` | Full detail without any computed/derived fields |

#### `references` — Related artefact inclusion

| Value | Description |
|-------|-------------|
| `none` (default) | No related artefacts |
| `children` | Direct children (e.g., table → cells, module → tables) |
| `descendants` | All descendants recursively |
| `parents` | Direct parents |
| `ancestors` | All ancestors recursively |
| `all` | All related artefacts |
| *specific type* | e.g., `references=variable` — only related variables |

#### `release` — Release filtering

| Parameter | Type | Description |
|-----------|------|-------------|
| `release` | string | Release code — return only versions active in this release |
| `releaseDate` | date | Return versions active at this date |

#### Pagination

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `offset` | int | 0 | Skip first N results |
| `limit` | int | 100 | Maximum results per page |

#### Sorting

| Parameter | Type | Description |
|-----------|------|-------------|
| `sort` | string | Field to sort by (e.g., `code`, `name`, `startRelease`) |
| `order` | string | `asc` or `desc` (default: `asc`) |

### 5.4 Examples

```
# All tables
GET /api/v1/structure/table

# All tables owned by EBA
GET /api/v1/structure/table/EBA

# Specific table, latest version
GET /api/v1/structure/table/EBA/C_01.00

# Specific table version
GET /api/v1/structure/table/EBA/C_01.00/3.2

# All tables with their cells included
GET /api/v1/structure/table?references=children

# Tables in release 3.4, stubs only
GET /api/v1/structure/table?release=3.4&detail=allstubs

# All operations of type validation
GET /api/v1/structure/operation?type=validation

# All modules with their table compositions
GET /api/v1/structure/module?references=children

# Specific property with its items
GET /api/v1/structure/property/*/MI1?references=children

# Wildcard search across all structure types
GET /api/v1/structure/structure?release=3.4&detail=allstubs
```

## 6. DPM-XL Service Endpoints

### 6.1 Syntax Validation

```
POST /api/v1/dpm-xl/validate/syntax
```

**Request body:**

```json
{
  "expression": "v1234 = v5678 + v9012"
}
```

**Response (200):**

```json
{
  "isValid": true,
  "expression": "v1234 = v5678 + v9012",
  "validationType": "syntax",
  "errorMessage": null,
  "errorCode": null
}
```

**Response (200, invalid):**

```json
{
  "isValid": false,
  "expression": "v1234 = v5678 +",
  "validationType": "syntax",
  "errorMessage": "Unexpected end of expression at line 1, column 16",
  "errorCode": "SYNTAX_001"
}
```

### 6.2 Semantic Validation

```
POST /api/v1/dpm-xl/validate/semantic
```

**Request body:**

```json
{
  "expression": "v1234 = v5678 + v9012",
  "releaseCode": "3.4"
}
```

**Response (200):**

```json
{
  "isValid": true,
  "expression": "v1234 = v5678 + v9012",
  "validationType": "semantic",
  "errorMessage": null,
  "errorCode": null,
  "warning": null,
  "results": {
    "operands": [...],
    "typeInfo": {...}
  }
}
```

### 6.3 AST Generation

```
POST /api/v1/dpm-xl/ast
```

**Request body:**

```json
{
  "expression": "v1234 = v5678 + v9012",
  "level": 1,
  "releaseCode": "3.4"
}
```

**Levels:**

| Level | Name | DB Required | Description |
|-------|------|-------------|-------------|
| 1 | Basic AST | No | Syntax tree only |
| 2 | Complete AST | Yes | Semantic validation + metadata |
| 3 | Validations Script | Yes | Engine-ready AST with scopes |

**Response (200):**

```json
{
  "level": 1,
  "expression": "v1234 = v5678 + v9012",
  "ast": {
    "type": "BinaryExpression",
    "operator": "=",
    "left": {
      "type": "VariableReference",
      "code": "v1234"
    },
    "right": {
      "type": "BinaryExpression",
      "operator": "+",
      "left": {"type": "VariableReference", "code": "v5678"},
      "right": {"type": "VariableReference", "code": "v9012"}
    }
  }
}
```

### 6.4 Operation Scope Calculation

```
POST /api/v1/dpm-xl/scopes
```

**Request body:**

```json
{
  "expression": "v1234 = v5678 + v9012",
  "operationVersionId": 456,
  "releaseCode": "3.4"
}
```

**Response (200):**

```json
{
  "scopes": [
    {
      "scopeId": 1,
      "moduleVersion": {"code": "FINREP_IND", "vid": 101},
      "tables": [
        {"code": "F_01.01", "vid": 201, "name": "Balance Sheet"}
      ]
    }
  ],
  "metadata": {
    "tablesCount": 3,
    "modulesCount": 1
  }
}
```

### 6.5 Validation Script Generation

```
POST /api/v1/dpm-xl/script
```

**Request body:**

```json
{
  "expressions": [
    "v1234 = v5678 + v9012",
    "v4567 > 0"
  ],
  "releaseCode": "3.4",
  "severity": "error"
}
```

Or with per-operation severity:

```json
{
  "expressions": [
    ["v1234 = v5678 + v9012", "op_code_1", "op_vid_1", "warning"],
    ["v4567 > 0", "op_code_2", "op_vid_2", "error"]
  ],
  "releaseCode": "3.4"
}
```

**Response (200):**

```json
{
  "script": [...],
  "metadata": {
    "expressionCount": 2,
    "severity": "error",
    "releaseCode": "3.4"
  }
}
```

## 7. Query Endpoints

Pre-built complex queries that combine multiple entities.

### 7.1 Data Dictionary

```
GET /api/v1/query/data-dictionary/tables
GET /api/v1/query/data-dictionary/tables?release=3.4
GET /api/v1/query/data-dictionary/tables?module=FINREP_IND
GET /api/v1/query/data-dictionary/tables/{tableCode}
GET /api/v1/query/data-dictionary/tables/{tableCode}/details
```

**Response for table details:**

```json
{
  "table": {
    "code": "F_01.01",
    "name": "Balance Sheet - Assets",
    "version": "3.2",
    "headers": {
      "columns": [...],
      "rows": [...],
      "sheets": [...]
    },
    "cells": [...],
    "variables": [...]
  }
}
```

### 7.2 Explorer (Inverse Queries)

```
GET /api/v1/query/explorer/properties-using-item/{itemCode}
GET /api/v1/query/explorer/tables-using-variable/{variableCode}
GET /api/v1/query/explorer/variable-from-cell/{tableCode}/{column}/{row}
GET /api/v1/query/explorer/variable-from-cell/{tableCode}/{column}/{row}/{sheet}
GET /api/v1/query/explorer/module-url/{moduleCode}
```

### 7.3 Hierarchical Queries

```
GET /api/v1/query/hierarchy/{domainCode}
GET /api/v1/query/hierarchy/{domainCode}/children/{itemCode}
GET /api/v1/query/hierarchy/{domainCode}/ancestors/{itemCode}
```

## 8. System Endpoints

### 8.1 Health Check

```
GET /api/v1/system/health
```

```json
{
  "status": "healthy",
  "database": "connected",
  "version": "1.0.0"
}
```

### 8.2 Server Information

```
GET /api/v1/system/info
```

```json
{
  "name": "dpmcore",
  "version": "1.0.0",
  "database": "postgresql",
  "features": ["dpm-xl", "rest-api", "instance-generation"]
}
```

### 8.3 Available Releases

```
GET /api/v1/system/releases
```

```json
{
  "releases": [
    {"code": "3.4", "date": "2024-06-01", "isCurrent": true},
    {"code": "3.3", "date": "2024-01-01", "isCurrent": false}
  ]
}
```

## 9. Response Envelope

All responses use a consistent envelope structure:

### Success Response

```json
{
  "meta": {
    "id": "req-uuid",
    "prepared": "2024-01-15T10:30:00Z",
    "contentLanguage": "en",
    "totalCount": 42,
    "offset": 0,
    "limit": 100
  },
  "data": { ... }
}
```

### Empty Response

```
HTTP/1.1 204 No Content
```

No body. Following SDMX convention.

### Error Response

```json
{
  "meta": {
    "id": "req-uuid",
    "prepared": "2024-01-15T10:30:00Z"
  },
  "errors": [
    {
      "code": 400,
      "title": "Bad Request",
      "detail": "Unknown artefact type: 'tablezz'. Valid types are: table, variable, ..."
    }
  ]
}
```

## 10. HTTP Status Codes

| Code | Usage |
|------|-------|
| **200** | Success with data |
| **204** | Success but no matching results |
| **400** | Invalid query syntax or parameters |
| **401** | Authentication required (when auth is enabled) |
| **403** | Not authorised |
| **404** | Invalid endpoint (not "no results" — use 204 for that) |
| **406** | Unsupported format requested |
| **422** | Semantically invalid request (e.g., invalid release code) |
| **500** | Internal server error |

## 11. Content Negotiation

### Request

```
Accept: application/json              # Default
Accept: application/xml               # XML format (optional support)
Accept-Language: en                    # Language preference
```

### Response

```
Content-Type: application/json; charset=utf-8
Content-Language: en
```

The primary format is JSON. XML support is optional and may be added in a
future version.

## 12. Filtering Patterns

### Component-Based Filtering

For endpoints that return versioned entities, component-based filtering uses
query parameters:

```
GET /api/v1/structure/table?c[hasOpenRows]=true
GET /api/v1/structure/variable?c[type]=F
GET /api/v1/structure/operation?c[type]=V&c[source]=EBA
```

Supported operators (following SDMX `c` parameter pattern):

| Operator | Meaning | Example |
|----------|---------|---------|
| `eq` (default) | Equals | `c[type]=V` |
| `ne` | Not equal | `c[type]=ne:C` |
| `co` | Contains | `c[code]=co:FINREP` |
| `sw` | Starts with | `c[code]=sw:v12` |
| `ew` | Ends with | `c[code]=ew:_IND` |

### Text Search

```
GET /api/v1/structure/table?q=balance+sheet
```

Full-text search across code, name, and description fields.

## 13. API Versioning

The API version is embedded in the URL path (`/api/v1/`). Breaking changes
require a new version prefix. Non-breaking additions (new fields, new optional
parameters) do not.

## 14. Authentication & Authorization

Authentication is **optional** and configurable:

- **No auth** (default): Open access for standalone/internal use
- **API key**: Simple key-based auth via `X-API-Key` header
- **OAuth2/OIDC**: For enterprise deployments

When running as a Django app, authentication delegates to Django's
authentication system.

## 15. OpenAPI Documentation

FastAPI automatically generates OpenAPI 3.0 documentation:

- **Swagger UI**: `GET /api/v1/docs`
- **ReDoc**: `GET /api/v1/redoc`
- **OpenAPI JSON**: `GET /api/v1/openapi.json`

In Django mode, DRF's browsable API provides similar functionality.
