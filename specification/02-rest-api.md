# dpmcore Specification — Layer 2: REST API

## 1. Overview

The dpmcore REST API provides HTTP access to DPM structural metadata. It
follows the [SDMX REST API](https://github.com/sdmx-twg/sdmx-rest)
conventions adapted for the DPM domain, making it immediately familiar to
users of statistical data APIs such as those published by the BIS, ECB, and
Eurostat.

All structural metadata is served through a single, uniform URL pattern under
`/api/v1/structure/`. Each DPM entity type is addressable by organisation
owner, code, and version — with sensible defaults so that most queries can
omit trailing path segments entirely.

## 2. Design Principles

| Principle | Description |
|-----------|-------------|
| **SDMX URL patterns** | Hierarchical paths: `/{type}/{owner}/{id}/{version}` with wildcards, comma-separated values, and version keywords |
| **Convention over configuration** | Trailing path segments can be omitted; they fall back to well-defined defaults |
| **204 for empty results** | Following SDMX, a query that matches nothing returns `204 No Content` — not `404` |
| **Consistent filtering** | `detail`, `references`, `release`, `offset`, `limit` work the same way across all artefact types |
| **Response envelope** | Every success response is wrapped in a `{"meta": {...}, "data": {...}}` envelope |
| **OpenAPI auto-documentation** | FastAPI generates interactive Swagger UI, ReDoc, and OpenAPI JSON automatically |

## 3. Technology

- **Standalone mode**: FastAPI with Uvicorn
- **Django mode**: Django REST Framework views delegating to the same service
  layer
- Both share the same URL structure and response format

## 4. Base URL

```
/api/v1/structure/{artefactType}/{owner}/{id}/{version}
```

The API version is embedded in the path (`/api/v1/`). Breaking changes require
a new version prefix; non-breaking additions (new fields, new optional
parameters) do not.

Interactive documentation is available at:

| Endpoint | Format |
|----------|--------|
| `GET /api/v1/docs` | Swagger UI |
| `GET /api/v1/redoc` | ReDoc |
| `GET /api/v1/openapi.json` | OpenAPI 3.0 JSON |


## 5. Structure Queries

Structure queries allow retrieving **DPM structural metadata** — the
categories, properties, tables, variables, operations, and supporting reference
data that define a reporting framework.

### 5.1 Artefact Types

The `{artefactType}` path segment accepts the following **maintainable**
(top-level) artefact types. For the full containment model — which entities
are inline within each type — see
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
accessed through their parent or via sub-resource URLs — they do **not** have
their own top-level artefact type. See
[06-api-messages.md §6](06-api-messages.md#6-sub-resource-urls).

### 5.2 Syntax

```
GET /api/v1/structure/{artefactType}/{owner}/{id}/{version}
```

Parameter | Type | Description | Default | Multiple values
--- | --- | --- | --- | ---
`artefactType` | One of the types listed in §5.1, or `structure` as a wildcard matching all types | The type of structural metadata to be returned. | *(required)* | No
`owner` | String | The organisation (by acronym) maintaining the artefact. Comma-separated for OR logic (e.g. `EBA,ECB`). | `*` (all) | Yes
`id` | String | The code of the artefact. Comma-separated for OR logic (e.g. `C_01.00,C_02.00`). | `*` (all) | Yes
`version` | String or keyword | The version of the artefact. Accepts a literal version code, or one of the keywords below. | `~` | Yes

**Version keywords:**

| Keyword | Meaning |
|---------|---------|
| `~` | Latest version (any status) |
| `+` | Latest version with status `Final` (latest stable) |
| `*` | All versions |

**Omission rule:** Trailing path parameters that use their defaults can be
omitted. The following are equivalent:

```
/api/v1/structure/table
/api/v1/structure/table/*
/api/v1/structure/table/*/*
/api/v1/structure/table/*/*/~
```

### 5.3 Query Parameters

#### `detail` — Response granularity

Controls the amount of information returned for each artefact.

| Value | Description |
|-------|-------------|
| `full` *(default)* | All available information for all returned artefacts |
| `allstubs` | Only identification information (code, name) for all artefacts |
| `referencestubs` | Full detail for the requested artefacts; stubs for referenced ones |
| `allcompletestubs` | Identification plus description and annotations for all artefacts |
| `referencecompletestubs` | Full detail for requested artefacts; complete stubs for referenced ones |
| `referencepartial` | Full detail, but referenced item schemes include only items actually used by the returned artefact |
| `raw` | Same as `full`, but without computed/derived fields |

#### `references` — Related artefact inclusion

Instructs the service to return artefacts referenced by (or referencing) the
matched artefact.

| Value | Description |
|-------|-------------|
| `none` *(default)* | No related artefacts |
| `parents` | Artefacts that use the matched artefact (one level up) |
| `parentsandsiblings` | Parents, plus artefacts referenced by those parents |
| `ancestors` | Parents up to any level |
| `children` | Artefacts referenced by the matched artefact (one level down) |
| `descendants` | Children, and their children, up to any level |
| `all` | Combination of `parentsandsiblings` and `descendants` |
| *specific type* | A concrete artefact type name (e.g. `references=variable`) — return only related artefacts of that type |

#### `release` — Release filtering

| Parameter | Type | Description |
|-----------|------|-------------|
| `release` | string | Release code — return only versions active in this release |
| `releaseDate` | ISO 8601 date | Return versions active at this date |

#### Pagination

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `offset` | int | `0` | Number of results to skip |
| `limit` | int | `100` | Maximum number of results per page |

#### Sorting

| Parameter | Type | Description |
|-----------|------|-------------|
| `sort` | string | Field to sort by (e.g. `code`, `name`, `date`) |
| `order` | `asc` or `desc` | Sort direction (default: `asc`) |

#### Text search

| Parameter | Type | Description |
|-----------|------|-------------|
| `q` | string | Full-text search across code, name, and description fields |

#### Component-based filtering

For endpoints that return versioned entities, attribute-level filtering uses
the `c[...]` parameter pattern (following the SDMX component parameter):

```
GET /api/v1/structure/operation?c[type]=V&c[source]=EBA
```

| Operator | Meaning | Example |
|----------|---------|---------|
| *(none / eq)* | Equals (default) | `c[type]=V` |
| `ne` | Not equal | `c[type]=ne:C` |
| `co` | Contains | `c[code]=co:FINREP` |
| `sw` | Starts with | `c[code]=sw:v12` |
| `ew` | Ends with | `c[code]=ew:_IND` |

### 5.4 Examples

```bash
# Latest version of all releases (default: version=~)
GET /api/v1/structure/release

# All releases, all versions
GET /api/v1/structure/release/*/*/*

# All releases owned by EBA, latest version
GET /api/v1/structure/release/EBA

# All releases owned by EBA, all versions
GET /api/v1/structure/release/EBA/*/*

# Single release by code
GET /api/v1/structure/release/EBA/3.4

# Latest stable release (status=Final)
GET /api/v1/structure/release/*/*/+

# All tables, latest version, stubs only
GET /api/v1/structure/table?detail=allstubs

# All tables owned by EBA
GET /api/v1/structure/table/EBA

# Specific table, latest version
GET /api/v1/structure/table/EBA/C_01.00

# Specific table version
GET /api/v1/structure/table/EBA/C_01.00/3.2

# Multiple tables by code
GET /api/v1/structure/table/EBA/C_01.00,C_02.00

# Tables with their cells included
GET /api/v1/structure/table?references=children

# Tables in release 3.4, stubs only
GET /api/v1/structure/table?release=3.4&detail=allstubs

# All validation operations
GET /api/v1/structure/operation?c[type]=V

# A property with its items
GET /api/v1/structure/property/*/MI1?references=children

# Wildcard search across all structure types, release 3.4
GET /api/v1/structure/structure?release=3.4&detail=allstubs

# Paginated modules
GET /api/v1/structure/module?offset=0&limit=20

# Text search for tables
GET /api/v1/structure/table?q=balance+sheet
```

## 6. Response Format

All structure query responses use a consistent envelope.

### 6.1 Success Response (200)

```json
{
  "meta": {
    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "prepared": "2024-06-15T10:30:00+00:00",
    "contentLanguage": "en",
    "totalCount": 42,
    "offset": 0,
    "limit": 100
  },
  "data": {
    "releases": [
      {
        "id": 1,
        "code": "3.4",
        "date": "2024-06-01",
        "description": "EBA DPM 3.4",
        "status": "Final",
        "isCurrent": true,
        "conceptGuid": "..."
      }
    ]
  }
}
```

**Meta fields:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | string (UUID) | Unique identifier for this response |
| `prepared` | string (ISO 8601) | Timestamp when the response was generated |
| `contentLanguage` | string | Language of the returned content |
| `totalCount` | int | Total number of matching results (before pagination) |
| `offset` | int | Number of results skipped |
| `limit` | int | Maximum results returned |

**Data key naming:**

The key inside `data` uses the **singular** form when a single artefact is
returned (e.g. a specific code lookup) and the **plural** form for
collections:

| Scenario | Key |
|----------|-----|
| Single release | `"data": {"release": {...}}` |
| Collection of releases | `"data": {"releases": [...]}` |
| Single table | `"data": {"table": {...}}` |
| Collection of tables | `"data": {"tables": [...]}` |

### 6.2 Empty Response (204)

```
HTTP/1.1 204 No Content
```

No body. Following the SDMX convention, a query that matches no results
returns `204` — not `404`. This distinguishes "your query was valid but found
nothing" from "that endpoint does not exist".

### 6.3 Error Response (4xx / 5xx)

```json
{
  "meta": {
    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "prepared": "2024-06-15T10:30:00+00:00"
  },
  "errors": [
    {
      "code": 400,
      "title": "Bad Request",
      "detail": "Unknown artefact type: 'tablezz'. Valid types are: category, context, datatype, framework, module, operation, operator, organisation, property, release, table, tablegroup, variable"
    }
  ]
}
```

## 7. HTTP Status Codes

| Code | Meaning | When used |
|------|---------|-----------|
| **200** | OK | Query matched one or more results |
| **204** | No Content | Query was valid but matched nothing |
| **400** | Bad Request | Unknown artefact type, invalid path parameter, or malformed query parameter |
| **401** | Unauthorized | Authentication is enabled and credentials are missing or invalid |
| **403** | Forbidden | Authenticated but not authorised for this resource |
| **404** | Not Found | The endpoint itself does not exist (e.g. a typo in the base path) |
| **406** | Not Acceptable | The requested media type is not supported |
| **500** | Internal Server Error | Unexpected server-side failure |

## 8. Content Negotiation

### Request Headers

```
Accept: application/json              # Default (and currently only format)
Accept-Language: en                    # Language preference for translated fields
```

### Response Headers

```
Content-Type: application/json; charset=utf-8
Content-Language: en
```

The primary (and currently only) format is JSON. XML support
(`application/xml`) may be added in a future version.

## 9. Authentication

Authentication is **optional** and configurable per deployment:

| Mode | Description |
|------|-------------|
| **No auth** *(default)* | Open access — suitable for standalone or internal use |
| **API key** | Simple key-based auth via `X-API-Key` header |
| **OAuth2 / OIDC** | For enterprise deployments requiring delegated authorisation |

When running as a Django app, authentication delegates to Django's
authentication system.
