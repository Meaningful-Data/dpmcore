# XBRL Taxonomy Import

`dpmcore.loaders.xbrl` imports XBRL taxonomies (structure only — no
validation rules) into the DPM 2.0 Refit schema. It targets
taxonomies for which no DPM database is published, initially the
National Bank of Belgium national taxonomies: B2P2, FIB, SEG
(2006-Eurofiling architecture) and TREP (EBA-DPM-1.0-style
architecture).

## Package layout

```
src/dpmcore/loaders/xbrl/
├── model.py                  # neutral intermediate model (frozen
│                             # dataclasses, no third-party deps)
├── arelle_engine.py          # lazy Arelle adapter: DTS loading,
│                             # offline/web-cache wiring
├── reader_eurofiling2006.py  # ModelXbrl -> TaxonomyModel (B2P2/FIB/SEG)
├── reader_dpm1.py            # lxml-based reader (TREP dict/fws trees)
├── rend_parser.py            # lxml parser for PWD-2013 table linkbases
├── seeds.py                  # reference data for fresh databases
├── mapper.py                 # TaxonomyModel -> ORM rows
└── service.py                # XbrlTaxonomyImportService facade
```

Readers reduce a taxonomy to the neutral `TaxonomyModel`; the mapper
turns it into ORM rows. Only `arelle_engine` and
`reader_eurofiling2006` import Arelle (optional extra
`dpmcore[xbrl]`); the `dpm1` reader is pure lxml because TREP's
dictionary schemas import the retired EBA CRR dictionary URLs, which
no longer resolve online.

## Conventions (verified against the EBA 4.2.1 database)

- **GUIDs** — every entity hangs off a `Concept` row; GUIDs are
  deterministic UUID5 values of the entity's stable key (framework
  code + qname / role URI / table code + release), formatted
  Access-style `{UPPERCASE}`. Re-imports are therefore idempotent.
- **IDs** — fresh databases allocate `max + 1`; existing databases
  allocate high-volume entities inside the owner's numeric range
  (`<org_id><6-digit seq>`; releases use
  `<id_prefix><7-digit seq>`).
- **Metrics and dimensions** — each becomes an `Item`
  (`IsProperty=1`) + `Property` pair. The counterpart item joins the
  `_PR` category under the global `<type-letter>i<seq>` code
  sequence (`mi1`, `ei4`, ...) where code == signature. Metrics set
  `IsMetric=1`, a `DataTypeID` (monetary=9, enumeration=8, ...) and
  `PeriodType` (`stock`/`flow`). Enumerated dimensions link to
  their domain category via `PropertyCategory`; open/typed
  dimensions link to `_NA`.
- **Members** — `Item` + `ItemCategory` whose `Signature` is the
  canonical XBRL qname (`eba_MC:x156`, `be_QD:x1`). The signature
  is the cross-taxonomy reuse key in existing-database mode.
- **Datapoints** — `Context` (signature `"<pid>_<iid>#..."`, pairs
  sorted by property id) + `ContextComposition` rows;
  `Variable(Type='fact')` + `VariableVersion(PropertyID=metric,
  ContextID=...)`; referenced from `TableVersionCell` with cell
  code `{<TableCode>, r<row>, c<col>[, s<sheet>]}`.
- **Versioning** — one `Release` per import run. Re-importing a
  table/module under a new release closes the open version
  (SCD-2: `EndRelease` set) and creates a new one.
- **Labels** — the best English label goes on the entity `Name`
  column; other languages (fr/nl) become `Translation` rows keyed
  by the seeded `DPMAttribute` for the entity's name attribute and
  `Language` rows (en=1, fr=2, nl=3).
- **Fresh databases** are seeded with `DPMClass`, `DPMAttribute`
  (translated attributes only), `DataType`, `Operator`, `Language`
  and the canonical `_PR`/`_NA` categories (GUIDs copied from EBA
  databases so contents stay merge-compatible), which satisfies
  `SchemaValidationService`.

## Mapping — 2006 Eurofiling architecture (B2P2/FIB/SEG)

| XBRL artefact | DPM Refit target |
|---|---|
| Explicit domain (target of dimension-domain arcs) | `Category` (code synthesised from the domain qname's capitals, collision-safe), `IsEnumerated=1` |
| Domain members (usable domain-member closure) | `Item` + `ItemCategory(code=x<seq>, signature=qname)` |
| Dimension (`xbrldt:dimensionItem`) | `Item(IsProperty)` + `Property`; open when its domain has no usable members |
| Concrete primary items (`p-*.xsd`) | metric `Item` + `Property(IsMetric=1)` |
| Domain-member closure tree | one `SubCategory`/`SubCategoryVersion`/`SubCategoryItem` hierarchy per domain |
| `t-*.xsd` entry point | `Table` + `TableVersion` (code from the file name, name from the presentation role definition) and one `Module`/`ModuleVersion` (the 2006 architecture has no module concept; NBB collects these tables individually) |
| Presentation tree of the primary schema | Y-axis headers (abstract "...Presentation" items become abstract headers) |
| Closed dimensions of the row hypercubes | X-axis columns = cartesian member product; dimensions exceeding `max_enumerated_columns` are demoted to key dimensions |
| Open dimensions (currency, scope heads) | Z-axis key headers (`IsKey=1`, `HasOpenSheets`) |
| row × column where the row's hypercubes cover the column dims | `Cell` + `Context` + `Variable`/`VariableVersion` + `TableVersionCell` |

`all` arcs are inherited down the primary-item domain-member tree;
per-row hypercube coverage filters the cell grid (sparse tables).

## Mapping — dpm1 architecture (TREP)

| XBRL artefact | DPM Refit target |
|---|---|
| `dict/dom/exp.xsd` heads + `dom/<code>/mem.xsd` + `mem-def.xml` | `Category` per domain (codes from element names) + member `Item`s |
| `dom/<code>/hier-def.xml` | `SubCategory` hierarchy tree |
| `dict/dim/dim.xsd` (+`dim-def.xml`) | dimension `Property`s; `xbrldt:typedDomainRef` marks typed (open) dimensions |
| `dict/met/met.xsd` | metric `Property`s (codes `mi1`, `pi3`, ... already in DPM form) |
| `fws/**/mod/*.xsd` (`model:moduleType` element) | `Module` + `ModuleVersion`; compositions from the schema's `xs:import`s of table namespaces |
| `tab/*/-rend.xml` (PWD 2013-05-17 table linkbase) | `Table`/`TableVersion`; breakdowns per `axis` become header trees; rule-node codes come from the `-lab-codes.xml` rc-code labels; `table:aspectNode` becomes an open (key) axis |
| rule-node aspects (`formula:concept`, `formula:explicitDimension`) | merged leaf-to-root along each axis chain into the cell's metric and context |

Qnames are canonicalised to the DPM signature convention
(`<owner>_<domain>:<name>` — `eba_BA:x17`, `be_met:mi1`). Concepts
in EBA namespaces are not resolved (the EBA no longer serves the
DPM 1.x dictionary); in existing-database mode they are reused via
`ItemCategory.Signature`, otherwise imported as NBB-owned shadow
rows with a warning.

## Modes

- **Fresh (default)** — `drop_all`/`create_all`, seed, map, commit,
  then relocate SQLite files to `<stem>_<release>_<YYYYMMDD>.db`
  (shared with `MigrationService` via `loaders/_sqlite_output.py`).
- **Existing (`into_existing=True`)** — target pre-validated with
  `SchemaValidationService`; single transaction with rollback on
  error; dedup order: deterministic GUID, dictionary signature,
  framework code, context signature. `IsCurrent` of existing
  releases is never touched.

## CLI

```
dpmcore import-xbrl --source <dir|zip>
    --framework-code B2P2 [--framework-name "..."]
    --release-code 2008-01-01 [--release-date 2008-01-01]
    (--database sqlite:///new.db [--output final.db]
     | --into sqlite:///existing.db)
    [--entry <glob>]... [--architecture auto|eurofiling2006|dpm1]
    [--offline] [--cache-dir DIR]
    [--owner-acronym NBB] [--owner-name "..."] [--max-columns 512]
```

## Out of scope (v1)

- Validation rules (formula/assertion linkbases; TREP's
  `*_val.zip`) — the DPM `Operation` layer is not populated.
- Calculation weights on 2006 presentation trees
  (`SubCategoryItem.ArithmeticOperatorID` is left empty).
- Open-axis instance keys (`CompoundKey`/`KeyComposition`).
