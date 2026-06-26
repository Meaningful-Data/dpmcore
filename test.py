from dpmcore import connect

with connect("sqlite:///dpm_4.2.1_20260624.db") as db:
    result = db.services.semantic.validate(
        """
with {tR_22.01, c0010, interval: false}:
        if ( {r0040, default: ""} = [eba_BT:x28] or {r0050, default: ""} = [eba_BT:x28] or {r0060, default: ""} = [eba_BT:x28] or not ( isnull ({r0070, default: null}) ) ) then ( {r0020, default: ""} = [eba_BT:x28] ) endif
""",
        release_code="4.2.1",
    )
    print(result)
    print(result.is_valid)
    print(result.warning)
