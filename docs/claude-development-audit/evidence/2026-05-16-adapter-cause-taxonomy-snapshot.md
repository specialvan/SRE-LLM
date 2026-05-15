# 2026-05-16 Adapter Cause Taxonomy Evidence

## Repository State

```text
git status --short
 M PR-REQUIREMENTS.md
 M docs/EVENT_SCHEMA.md
 M docs/V2_Knowledge/knowledge-base.html
 M docs/claude-development-audit/README.md
 M docs/claude-development-audit/backlog.md
 M docs/knowledge-base.html
 M sre_control/stack.py
 M tests/test_contracts.py
 M tests/test_event_schema.py
?? docs/claude-development-audit/evidence/2026-05-16-adapter-cause-taxonomy-snapshot.md
?? docs/claude-development-audit/reports/2026-05-16-adapter-cause-taxonomy.md
```

## Focused Verification

```text
python -m pytest tests/test_contracts.py::test_sre_stack_recovers_from_recoverable_adapter_error tests/test_contracts.py::test_sre_stack_classifies_adapter_input_error_as_adapter_input tests/test_event_schema.py::test_adapter_exception_event_includes_machine_readable_cause_fields -q
....                                                                     [100%]
```

## Full Verification

```text
python -m pytest tests -q
........................................................................ [ 70%]
..............................                                           [100%]
```

```text
python -m scripts.quality_gate_counts
quality gate pytest count: 102
```

```text
python -m scripts.build_kb
[1/3] updating quality gate counts ...
[2/3] building mechanism diagrams ...
mechanism diagrams written to: D:\workspace\SRE-LLM\spacex\docs\assets
[3/3] building benefit GIFs ...
benefit GIFs written to: D:\workspace\SRE-LLM\spacex\docs\assets
done. open docs/V2_Knowledge/knowledge-base.html in a browser.
```

```text
html.parser smoke check
docs\control-center.html: ok
docs\V2_Knowledge\knowledge-base.html: ok
docs\knowledge-base.html: ok
```

```text
git diff --check
warning: LF will be replaced by CRLF warnings only; no whitespace errors.
```

## Schema Drift Check

```text
adapter_exception cause taxonomy
AdapterInputError -> cause_type=adapter_input
RecoverableControlError -> cause_type=control_domain
```
