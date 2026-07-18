Model validation & variable generation
=======================================

dpmcore ports the modelling workflow of the EBA DPM development
database — the ``check_modelling_rules_tidy`` and
``variable_generation_tidy`` stored procedures — as two native,
**read-only** services. Results are returned as Python dataclasses
(serialisable with ``to_dict()``); nothing is written to the database.

Model validation
----------------

Runs the full DPM modelling-rule set (~120 rules across five families:
lifecycle, axes, headers, assignments, glossary) against an in-memory
snapshot of the model::

    from dpmcore import connect

    with connect("sqlite:///dpm.db") as db:
        result = db.services.model_validation.validate()

    print(result.is_valid, result.error_count, result.warning_count)
    for violation in result.violations:
        print(violation.rule_id, violation.severity, violation.message)
        for obj in violation.objects:
            print("   ", obj.kind, obj.id, obj.code)

By default the release flagged ``IsCurrent`` is validated. Pass
``release_code=...`` or ``release_id=...`` to validate another release
— passing the draft release id (9999) reproduces the old "playground"
behaviour with the complete rule set. ``rule_ids=[...]`` restricts the
run to specific rules, and ``include_warnings=False`` skips
warning-severity rules.

The rule catalogue is introspectable::

    for info in db.services.model_validation.list_rules():
        print(info.rule_id, info.family, info.severity, info.description)

A model full of violations is a *successful* validation run —
exceptions are reserved for operational failures (unknown release,
broken database).

Each rule carries a unique ``rule_id`` (e.g. ``3_5a``) plus the
original SQL ``ViolationCode`` as ``legacy_code`` (the SQL reused some
codes for distinct checks). ``isBlocking`` maps to severity:
blocking → ``error``, otherwise ``warning``.

Variable generation
-------------------

Computes — without persisting — the complete variable-generation plan
for a release: which ``Variable``/``VariableVersion`` each table cell
maps to, plus the supporting key variables, compound keys, filing
indicators, and contexts::

    with connect("sqlite:///dpm.db") as db:
        plan = db.services.variable_generation.generate()

    print(plan.status)  # completed / blocked_by_validation / ...
    for assignment in plan.cell_assignments:
        print(
            assignment.table_code,
            assignment.cell_code,
            assignment.outcome,       # unchanged / new_version / ...
            assignment.new_variable_ref,
        )
    for variable in plan.new_variables:
        print(variable.temp_id, variable.type, variable.aspect)

Model validation runs first as a gate (disable with
``validate_first=False``); any blocking violation returns a plan with
``status=blocked_by_validation`` and the attached validation result.
Generation-specific consistency errors (rules ``5_1``–``5_6``) return
``blocked_by_consistency``.

Proposed objects use deterministic plan-local temp ids (``"var:1"``,
``"vv:3"``, …) — allocating real database ids is a persistence concern
outside the service.

CLI
---

Both services are available from the command line::

    dpmcore validate-model --database sqlite:///dpm.db
    dpmcore validate-model --database sqlite:///dpm.db --json
    dpmcore validate-model --database sqlite:///dpm.db --rules 1_5,6_30

    dpmcore generate-variables --database sqlite:///dpm.db
    dpmcore generate-variables --database sqlite:///dpm.db --json \
        --summary-only

Exit code 0 means valid / completed; 1 otherwise.

REST
----

With the server extra installed::

    POST /api/v1/model/validation
        {"release_code": "4.0", "rule_ids": null,
         "include_warnings": true}
    GET  /api/v1/model/validation/rules
    POST /api/v1/model/variable-generation
        {"release_code": "4.0", "validate_first": true}

Responses are the ``to_dict()`` form of the corresponding result
objects.

Equivalence with the SQL procedures
-----------------------------------

The port is behavioural: same violations, same generated variables,
different architecture (in-memory snapshot + pure rule functions
instead of 119 SQL queries; a returned plan instead of table writes).
A parity harness compares both implementations on the same database —
see ``scripts/parity/README.md`` and
``specification/08-modelling-services.md`` §9.
