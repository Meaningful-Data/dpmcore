from dpmcore import connect

# A real REM_DBM 2.3.0 if-then validation (v22581_m).
EXPR = (
    "with {tR_22.01, c0010, interval: false}: "
    'if ( {r0040, default: ""} = [eba_BT:x28] '
    'or {r0050, default: ""} = [eba_BT:x28] '
    'or {r0060, default: ""} = [eba_BT:x28] '
    "or not ( isnull ({r0070, default: null}) ) ) "
    'then ( {r0020, default: ""} = [eba_BT:x28] ) endif'
)


with connect("sqlite:///dpm_4.2.1_20260624.db") as db:
    out = db.services.ast_generator.script(
        expressions=[(EXPR, "v22581_m")],
        module_code="REM_DBM",
        module_version="2.3.0",
    )
    print(out["success"], out["error"])
