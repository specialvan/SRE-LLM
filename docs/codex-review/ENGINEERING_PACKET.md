# Codex Engineering Packet

This packet is the current offline engineering handoff. Older, more verbose
review files remain in this directory as historical context, but this file
summarizes the state a reviewer should trust first.

## Boundary

- The project is a public-material research and engineering reproduction.
- It does not represent SpaceX official implementation.
- `starship/` is the mathematical/physical layer.
- `sre_control/` is the SRE migration layer.
- `analysis/` generates scenario evidence, not production benchmarks.

## Entry Points

| Entry | Use |
|---|---|
| `README.md` | Project overview and run commands |
| `wiki/README.md` | Cross-session wiki entry |
| `wiki/review-backlog.md` | Current completed/open review state |
| `docs/V2_Knowledge/knowledge-base.html` | Canonical current HTML knowledge base |
| `docs/API_CONTRACTS.md` | Adapter contracts |
| `docs/EVENT_SCHEMA.md` | Runtime event schema |
| `docs/RUNTIME_STATES.md` | Runtime state propagation |
| `docs/codex-review/OPEN_RISKS.md` | Current risk register |
| `docs/codex-review/QUALITY_GATES.md` | Current verification gates |
| `docs/opus-review/HANDOFF.md` | Current Opus first-read handoff and reviewer runbook |

Git review scope is delegated to `docs/opus-review/HANDOFF.md` ->
`Git Review Scope Snapshot`: refresh
`git status --short --branch --untracked-files=all` and
`git ls-files --others --exclude-standard`, then treat the dirty/untracked
surface as current review scope.

## Runtime Chain

```text
OBSERVE -> STABILITY -> PLAN -> GUARD -> ALLOCATE -> EXECUTE
```

Core mappings:

| Area | Implementation | Runtime evidence |
|---|---|---|
| Signal fusion | `sre_control/signal_fusion.py`, `starship/ekf.py` | `missing_sensor`, `outlier_rejected` |
| Stability guard | `sre_control/stability_guard.py`, `starship/stability_monitor.py` | `stability_violation` |
| Planning | `sre_control/predictive_autoscaler.py`, `sre_control/canary_scheduler.py` | `replica_bound_active`, `rollout_rejected` |
| Guardrail | `sre_control/slo_guardrail.py` | `unsafe_proposal_projected` |
| Allocation | `sre_control/weighted_balancer.py`, `sre_control/catch_adapter.py` | `bounded_ls_residual`, allocator fallback events |
| Stack lifecycle | `sre_control/stack.py`, `sre_control/events.py` | degraded states, `adapter_exception` |

## Current Verification

Current synchronized pytest count: `945`.

```bash
python -m pytest tests -q
python -m analysis.s10_failure_trace
python -m analysis.run_all
python -m analysis.evidence_manifest
python -m analysis.evidence_report
python -m scripts.control_center_browser_smoke --report-manifests --report-json analysis/artifacts/control-center-browser-evidence-report.json
python -m scripts.package_smoke
python -m scripts.control_center_integration_audit
python -m scripts.review_authority_lint
python -m scripts.evidence_boundary_lint
python -m examples.demo_sre_loop
python -m examples.demo_powered_descent
python -m examples.demo_catch_phase
python -u -m scripts.quality_gate_counts
python -m scripts.quality_gate_counts --check --skip-expensive
```

This block mirrors the Opus handoff command set. Targeted gates are listed in
`QUALITY_GATES.md`.

## Merge-Scope Checklist

The current green state spans tracked edits plus new files that may still show
as untracked in `git status`. A handoff or merge must include the core source,
tests, docs, and canonical generated evidence below; otherwise the verified
state is not reproducible from the checked-out tree.

For the exact current git review surface, use
`docs/opus-review/HANDOFF.md` -> `Git Review Scope Snapshot` before exporting
or merging. Re-run `git status --short --branch --untracked-files=all` and
`git ls-files --others --exclude-standard`; the `exact current untracked inventory`
lives in that handoff so split files are not silently omitted.

New source and verifier entry points:

- `analysis/evidence_artifacts.py`
- `analysis/evidence_manifest_checks.py`
- `analysis/evidence_consistency.py`
- `analysis/evidence_contracts.py`
- `analysis/evidence_manifest.py`
- `analysis/evidence_report.py`
- `analysis/s11_catch_sre_wrapper.py`
- `analysis/s12_sre_replay.py`
- `analysis/fixtures/sre_replay.jsonl`
- `scripts/control_center_browser_smoke.py`
- `scripts/control_center_integration_audit.py`
- `scripts/evidence_boundary_lint.py`
- `scripts/quality_gate_counts.py`
- `scripts/review_authority_lint.py`
- `sre_control/catch_adapter.py`
- `sre_control/stack_contract.py`

New tests that lock those contracts:

- `tests/test_analysis_common.py`
- `tests/test_analysis_run_all.py`
- `tests/test_catch_adapter.py`
- `tests/test_control_center_browser_dom.py`
- `tests/test_control_center_browser_smoke.py`
- `tests/test_control_center_browser_manifest.py`
- `tests/test_control_center_browser_error_manifest.py`
- `tests/test_control_center_browser_report.py`
- `tests/test_control_center_integration_audit.py`
- `tests/test_evidence_artifacts.py`
- `tests/test_evidence_manifest_checks.py`
- `tests/test_evidence_consistency.py`
- `tests/test_evidence_contracts.py`
- `tests/test_evidence_manifest_generation.py`
- `tests/test_evidence_manifest.py`
- `tests/test_evidence_report_manifest_shape.py`
- `tests/test_evidence_report_study_shape.py`
- `tests/test_evidence_report_contract_shape.py`
- `tests/test_evidence_report_artifact_paths.py`
- `tests/test_evidence_contract_report.py`
- `tests/test_evidence_contract_fallback_report.py`
- `tests/test_evidence_contract_trace_report.py`
- `tests/test_evidence_contract_boundary_report.py`
- `tests/test_evidence_trace_report.py`
- `tests/test_evidence_wrapper_report.py`
- `tests/test_evidence_replay_report.py`
- `tests/test_evidence_replay_consistency_report.py`
- `tests/test_evidence_replay_artifacts_report.py`
- `tests/test_quality_gate_counts.py`

New handoff and contract docs:

- `PR-REQUIREMENTS.md`
- `wiki/README.md`
- `wiki/review-backlog.md`
- `wiki/evidence-ledger.md`
- `docs/codex-review/CODEX_SUMMARY.md`
- `docs/codex-review/README.md`
- `docs/codex-review/QUALITY_GATES.md`
- `docs/codex-review/ENGINEERING_PACKET.md`
- `docs/claude-development-audit/backlog.md`
- `docs/CONTROL_CENTER_HANDOFF.md`
- `docs/EVENT_EVIDENCE_MANIFEST.md`
- `docs/STACK_DATA_CONTRACT.md`
- `docs/superpowers/plans/README.md`
- `docs/superpowers/specs/README.md`
- `docs/opus-review/HANDOFF.md`
- `docs/opus-review/OPUS_REVIEW_PACKET.md`
- `docs/opus-review/README.md`

`scripts.quality_gate_counts.QUALITY_GATE_TARGETS` updates synchronized
pytest-count lines, and `QUALITY_GATE_COMMAND_DOCS` enforces required command
coverage plus stale non-quiet full-suite command rejection in the current docs
above. Carry those docs together with `scripts/quality_gate_counts.py` and
`tests/test_quality_gate_counts.py`; a partial packet can leave review-facing
counts or required command lists stale.

Superpowers plan/spec inventories live in `docs/superpowers/plans/README.md`
and `docs/superpowers/specs/README.md`. Reviewers should use those inventory
sections to confirm every dated plan or spec artifact in the dirty/untracked
surface is either carried into the packet or intentionally excluded with a
separate reason.

Canonical generated evidence to carry with the packet:

- `analysis/artifacts/event_evidence_manifest.json`
- `analysis/artifacts/s11_catch_sre_wrapper.png`
- `analysis/artifacts/s11_catch_sre_wrapper_diagnostics.json`
- `analysis/artifacts/s12_replay_trace.jsonl`
- `analysis/artifacts/s12_replay_diagnostics.json`
- `analysis/artifacts/sre_stack_data_contract.json`
- `analysis/artifacts/control-center-browser-smoke-api.json`
- `analysis/artifacts/control-center-browser-smoke-manifest.json`
- `analysis/artifacts/control-center-browser-error-smoke-manifest.json`
- `analysis/artifacts/control-center-browser-frontend-error-smoke-manifest.json`
- `analysis/artifacts/control-center-browser-evidence-report.json`
- `analysis/artifacts/control-center-integration-audit.json`

Browser screenshots and DOM dumps referenced by those manifests are evidence
artifacts, not source. Keep the manifest-referenced desktop/mobile success,
backend-error, and frontend-error PNG/HTML files with the packet if reviewers
need offline replay. Treat local inspection/cache artifacts such as
`analysis/artifacts/control-center-review.png`, legacy
`control-center-browser-smoke.png`, or ad hoc `control-center-browser-smoke.html`
should not be treated as authoritative unless a manifest references them.

## Resolved Review Items

- Section 10 failure trace now uses continuous stack history and exports full
  evidence.
- Section 10 `replica_bound_active` now covers every tick in its injection
  window under a bounded-capacity demand surge forecast.
- Section 5 now includes radar + near-field fiducial updates and reports
  source-use / near-field metrics.
- StabilityGuard now includes `sre_error_budget_V`, a concrete latency/error
  burn energy helper, and a stack-level `StabilityGuard/error_budget` event
  regression.
- `CatchLoadAdapter` now lands the Catch/SRE wrapper boundary in the SRE layer
  while preserving `starship/` import direction and residual visibility.
- Section 12 replay evidence now covers a 19-tick synthetic replay with a
  3-tick compound multi-signal incident and window-level operator action.
- Cross-study event evidence is indexed by
  `analysis/artifacts/event_evidence_manifest.json`, with Section 10/11/12
  JSON/JSONL/PNG artifacts referenced by repo-relative paths and
  `artifact_metadata` byte-identity records containing SHA-256 digests and byte
  size values.
- `docs/EVENT_EVIDENCE_MANIFEST.md` documents that manifest contract and is
  checked by `tests/test_evidence_manifest_generation.py`.
- `analysis.evidence_report` prints a compact manifest summary and validates
  the top-level manifest shape, closed study/contract ID sets, required
  study/contract entry sets, required generic and entry-specific fields plus
  their value types, documented fixed values, bounded numeric ranges, artifact
  key sets, artifact metadata key parity, SHA-256 digests, byte size values,
  expected artifact extensions, repo-contained relative string artifact paths,
  file existence, JSON/JSONL/PNG parseability, runtime event payloads, stack
  data contract consistency, and key manifest counts.
- `scripts.quality_gate_counts` treats the manifest and report commands as
  required current quality gates.
- Programmer errors are not swallowed by recoverable fallback handling.
- StabilityMonitor latch semantics are explicit and tested.
- Per-sensor innovation gate thresholds are implemented and traced.
- Allocator fallback reuses last-good shares when topology/signature is valid.
- EKF Joseph covariance update and symmetrization are implemented and tested.
- Docs/schema sync, package smoke, release hygiene, and control-center exposure
  policy have tests.

## Remaining Useful Review Questions

- If replay-style SRE evidence expands, does it remain labeled as replay or
  synthetic evidence rather than production proof?
- Should release-pipeline automation be added if this repository starts
  publishing versioned artifacts?
