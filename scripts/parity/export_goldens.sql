-- Parity golden-file generation for the dpmcore modelling services.
-- Run against a SQL Server restore of DPM_REFIT_EBA_DEV_260715.bacpac.
-- See scripts/parity/README.md for the full workflow.
--
-- Each SELECT below is one golden CSV. With sqlcmd, run the sections
-- separately with -o and -s"," -W, or use bcp for clean CSV output.

SET NOCOUNT ON;

------------------------------------------------------------------
-- 1. Model validation goldens
------------------------------------------------------------------

EXEC dbo.check_modelling_rules_tidy;

-- -> tests/fixtures/parity/model_violations.csv
SELECT ViolationCode,
       Violation,
       isBlocking,
       TableVID,
       OldTableVID,
       TableCode,
       HeaderID,
       HeaderCode,
       HeaderVID,
       OldHeaderVID,
       HeaderPropertyID,
       HeaderSubcategoryID,
       HeaderContextID,
       CategoryID,
       CategoryCode,
       ItemID,
       ItemCode,
       CellID,
       CellCode,
       Cell2ID,
       Cell2Code,
       VVEndReleaseID,
       NewAspect
FROM dbo.ModelViolations
ORDER BY ViolationCode, TableVID, HeaderID, ItemID, CellID;

------------------------------------------------------------------
-- 2. Variable generation goldens
--
-- NOTE: variable_generation_tidy MUTATES the model (creates
-- variables, closes versions, assigns cells). Snapshot/migrate the
-- database to SQLite BEFORE running this section — the Python
-- service must see the pre-generation state.
------------------------------------------------------------------

EXEC dbo.variable_generation_tidy;

-- -> tests/fixtures/parity/vargeneration_detail.csv
SELECT *
FROM dbo.VarGeneration_Detail
ORDER BY ModuleVID, TableVID, CellID;

-- -> tests/fixtures/parity/vargeneration_summary.csv
SELECT *
FROM dbo.VarGeneration_Summary
ORDER BY OutcomeID, OutcomeVID, ReportMsg;

-- -> tests/fixtures/parity/generated_variables.csv
-- Variables/versions created by the run: generated ids are allocated
-- from 1010000000 upward (see the procedure's ID allocation).
SELECT v.VariableID,
       v.Type,
       vv.VariableVID,
       vv.PropertyID,
       vv.ContextID,
       vv.KeyID,
       vv.Code,
       vv.StartReleaseID,
       vv.EndReleaseID
FROM dbo.Variable v
LEFT JOIN dbo.VariableVersion vv ON vv.VariableID = v.VariableID
WHERE v.VariableID >= 1010000000
   OR vv.VariableVID >= 1010000000
ORDER BY v.VariableID, vv.VariableVID;

-- -> tests/fixtures/parity/cell_variable_map.csv
SELECT tvc.TableVID,
       tv.Code AS TableCode,
       tvc.CellID,
       tvc.CellCode,
       tvc.IsVoid,
       tvc.IsExcluded,
       tvc.VariableVID,
       vv.VariableID,
       vv.KeyID,
       vv.PropertyID,
       vv.ContextID
FROM dbo.TableVersionCell tvc
JOIN dbo.TableVersion tv ON tv.TableVID = tvc.TableVID
LEFT JOIN dbo.VariableVersion vv
       ON vv.VariableVID = tvc.VariableVID
ORDER BY tvc.TableVID, tvc.CellID;
