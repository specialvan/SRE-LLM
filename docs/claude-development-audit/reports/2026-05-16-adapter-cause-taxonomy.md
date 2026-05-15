# 2026-05-16 Adapter Cause Taxonomy Review

## Verdict

`WATCH-002` is resolved in the working tree. `adapter_exception.cause_type` now has one real non-speculative split: invalid or missing adapter input is routed as `adapter_input`, while other recoverable control-domain failures remain `control_domain`.

## Evidence

- `sre_control.exceptions.AdapterInputError` already existed as a concrete `RecoverableControlError` subclass for invalid or missing adapter input.
- `SREControlStack._adapter_exception_event()` now maps `AdapterInputError` to `cause_type="adapter_input"` and keeps generic `RecoverableControlError` on `cause_type="control_domain"`.
- `tests/test_contracts.py` covers both the existing generic recoverable failure route and the new adapter-input route through a real `SREControlStack.step()` execution.
- `tests/test_event_schema.py` accepts both machine-readable cause values for `adapter_exception` events.
- `docs/EVENT_SCHEMA.md`, V2 knowledge-base HTML, and V1 archive HTML describe the split without inventing additional categories.

## Verification

```text
python -m pytest tests/test_contracts.py::test_sre_stack_recovers_from_recoverable_adapter_error tests/test_contracts.py::test_sre_stack_classifies_adapter_input_error_as_adapter_input tests/test_event_schema.py::test_adapter_exception_event_includes_machine_readable_cause_fields -q
....                                                                     [100%]
```

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
[3/3] building benefit GIFs ...
done. open docs/V2_Knowledge/knowledge-base.html in a browser.
```

## Backlog Result

- `WATCH-002` moved to `RES-021`.
- Remaining watch items are synthetic-evidence boundaries and release tag hygiene.
