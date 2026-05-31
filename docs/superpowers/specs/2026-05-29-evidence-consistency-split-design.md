# Evidence Consistency Split Design

> Historical planning artifact; it is not the current handoff.
> Opus review should start from `docs/opus-review/HANDOFF.md`, then verify
> live status in `wiki/review-backlog.md`,
> `docs/codex-review/OPEN_RISKS.md`, and
> `docs/codex-review/QUALITY_GATES.md`.

## Context

The current live ledgers show no active P0/P1 defect. The clearest follow-up is maintainability: `analysis/evidence_report.py` still owns the S10/S11/S12 study consistency checks, while manifest shape, artifact validation, and stack-contract checks have already been extracted into focused modules.

## Goal

Move study-level consistency validation out of `analysis/evidence_report.py` into a focused module without changing the reviewer-facing CLI behavior or error strings.

## Design

Create `analysis/evidence_consistency.py` with one public entry point:

```python
def study_consistency_errors(entry: dict, root: Path) -> list[str]
```

The module owns the study-specific invariants currently implemented by `_consistency_errors`: S10 trace count/background/sample-prefix checks, S11 diagnostics case-count and visibility checks, and S12 trace/diagnostics/fixture consistency including operator-action, recovery, multi-signal, and visibility diagnostics.

`analysis/evidence_report.py` remains the CLI orchestrator. It reads and shape-validates the manifest, calls artifact checks, calls `study_consistency_errors` for each study, calls `contract_consistency_errors` for contracts, and prints the same compact output as before. For compatibility with existing private-helper tests, `evidence_report.py` may import and re-export the strict-JSON recovery helper names during this pass.

## Testing

Add `tests/test_evidence_consistency.py` with direct tests for the new module:

- generated S10/S11/S12 study entries produce no consistency errors;
- S10 sample trace drift reports `sample_trace_prefix_mismatch`;
- S12 diagnostics drift reports the same `inconsistent_artifact ... <field>_mismatch` error currently produced through the full report.

Keep existing `tests/test_evidence_manifest.py` report-path coverage unchanged so CLI output and failure summaries remain locked.

## Acceptance

- `analysis/evidence_report.py` no longer contains the study consistency implementation body.
- `python -m pytest tests/test_evidence_consistency.py -q` passes.
- Existing evidence-report tests still pass.
- `python -m analysis.evidence_report` still prints `artifact_check ok studies=3 files=8` on current artifacts.
