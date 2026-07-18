# Parity harness — modelling services vs SQL stored procedures

The Python `ModelValidationService` and `VariableGenerationService`
(see `specification/08-modelling-services.md` §9) are ports of the EBA
stored procedures `check_modelling_rules_tidy` and
`variable_generation_tidy`. This harness verifies **result
equivalence**: for the same input database, the Python services must
find the same violations and generate the same variables as the SQL.

## One-time golden-file generation (requires SQL Server)

1. Restore `input/DPM_REFIT_EBA_DEV_260715.bacpac` to a SQL Server
   instance (SSMS → *Import Data-tier Application*, or `sqlpackage
   /Action:Import`).
2. Run the stored procedures and export the goldens:

   ```bash
   sqlcmd -S <server> -d <database> -i export_goldens.sql
   ```

   The script executes `check_modelling_rules_tidy`, exports
   `ModelViolations`, then executes `variable_generation_tidy` and
   exports `VarGeneration_Detail`, `VarGeneration_Summary`, the
   generated `Variable`/`VariableVersion` rows, and the final
   `TableVersionCell` → `VariableVID` map. Redirect each SELECT to a
   CSV (sqlcmd `-o`, or run per-query with `bcp`), producing:

   - `tests/fixtures/parity/model_violations.csv`
   - `tests/fixtures/parity/vargeneration_detail.csv`
   - `tests/fixtures/parity/vargeneration_summary.csv`
   - `tests/fixtures/parity/generated_variables.csv`
   - `tests/fixtures/parity/cell_variable_map.csv`

3. Migrate the **same** database (state as of *before* running
   `variable_generation_tidy` — restore the bacpac again if needed)
   to the SQLite fixture:

   ```bash
   dpmcore update-db --target sqlite:///tests/fixtures/parity_dpm.db \
       <source options>
   ```

   or export the tables to CSV and use
   `MigrationService.migrate_from_csv_dir`.

4. Run the parity tests:

   ```bash
   pytest tests/integration/validation/test_model_validation_parity.py -v
   ```

Like `tests/fixtures/test_data.db`, the parity fixture and goldens are
**not committed** (size, licensing); the tests auto-skip when absent.

## What is compared

- **Validation parity**: the multiset of `(legacy_code, primary object
  business key)` must match. Message text is NOT compared (the Python
  port fixes SQL typos); the blocking flag must match the severity
  mapping (`isBlocking=1` ⇔ `error`).
- **Generation parity**: per `(table_vid, cell_id)`, the outcome class
  and the new aspect signature must match; new variables are compared
  by `(type, aspect signature, code)` — never by id (the Python plan
  uses temp ids; see spec §5.5).
- Known-acceptable differences live in
  `tests/fixtures/parity/allowlist.yaml` with a justification each. An
  empty allowlist is the goal.
