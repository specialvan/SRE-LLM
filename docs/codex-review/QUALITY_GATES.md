# Quality Gates

This page records the current reproducible gates for reviewer handoff. Timing
numbers may vary by machine; behavioral claims should remain stable. Older
review packets may mention smaller test counts and should be read as historical
snapshots.

## Required Commands

```bash
python -m pytest tests
python -m analysis.s10_failure_trace
python -m analysis.run_all
python -m analysis.evidence_manifest
python -m analysis.evidence_report
python -m scripts.control_center_browser_smoke --report-manifests --report-json analysis/artifacts/control-center-browser-evidence-report.json
python -m scripts.package_smoke
python -m scripts.control_center_integration_audit
python -m examples.demo_sre_loop
python -m examples.demo_powered_descent
python -m examples.demo_catch_phase
```

Current local result from this continuation pass:

```text
python -m pytest tests -q
477 passed

python -m analysis.s10_failure_trace
Section 10 full/sample trace exported

python -m analysis.run_all
All 12 studies finished

python -m analysis.evidence_manifest
writes event_evidence_manifest.json

python -m analysis.evidence_report
artifact_check ok studies=3 files=8

python -m scripts.control_center_browser_smoke --report-manifests --report-json analysis/artifacts/control-center-browser-evidence-report.json
writes control-center-browser-evidence-report.json from saved browser manifests, including normal, backend error, frontend_error evidence, manifest_paths, manifest_records, and contract_depth metadata (`top_level`, `object_groups`, `object_fields`, `array_item_groups`, `array_item_fields`, `timeline_fields`); console output also prints manifest_paths=, manifest_records=, and manifest_replay=normal+backend_error+frontend_error provenance lines for CI logs

python -m scripts.package_smoke
package smoke ok; control-center evidence report validates normal, backend error, frontend_error browser paths, manifest_paths, non-stale manifest_records, positive contract_depth counts, and replays the three source manifests through verify_evidence_manifest, verify_error_evidence_manifest, and verify_frontend_error_evidence_manifest. The summary line includes manifest_records=normal+backend_error+frontend_error and manifest_replay=normal+backend_error+frontend_error so outer quality gates can assert the replay evidence from logs.

python -m scripts.control_center_integration_audit
writes analysis/artifacts/control-center-integration-audit.json after validating the live backend payload contract, reading the browser evidence report, and reusing package-smoke evidence verification so frontend/backend integration proof is available as one machine-readable artifact.

python -m examples.demo_sre_loop
trace prints without error

python -m examples.demo_powered_descent
PDG terminal state prints without error

python -m examples.demo_catch_phase
catch lateral error prints without error
```

## Targeted Gate Families

| Gate | Coverage |
|---|---|
| `tests/test_event_schema.py` | Runtime event registry, markdown docs sync, counterexamples, adapter-exception cause fields |
| `tests/test_release_hygiene.py` | Package/spec version separation and release-hygiene invariants |
| `tests/test_synthetic_evidence_boundaries.py` | Scenario-evidence boundaries for Section 5/8/11/12 regressions plus live-doc overclaim wording lint |
| `tests/test_failure_trace.py` | Continuous Section 10 stack history, injection-window coverage, full JSONL evidence |
| `tests/test_evidence_manifest.py` | Cross-study S10/S11/S12 evidence manifest, stack-contract artifact export, manifest/docs sync, and reviewer report artifact parse/schema/count/event-kind validation |
| `tests/test_quality_gate_counts.py` | Pytest count generation, package smoke, and current quality-gate command drift checks |
| `tests/test_contracts.py` | Runtime degraded/state/event contracts, recoverable exception taxonomy, allocator fallback, stack data-contract export with stage event-kind bindings |
| `tests/test_ekf.py` | EKF Joseph covariance update, symmetry/PSD behavior, gated no-op behavior |
| `tests/test_sre_control.py` | SRE adapters, per-sensor gate thresholds, stack behavior |
| `tests/test_import_graph.py` | `starship/` and `sre_control/` dependency direction |
| `tests/test_package_smoke.py` | Installed-wheel package discovery/import smoke plus control-center evidence report validation; wheel build uses `--no-build-isolation` so the gate reuses the current environment instead of fetching build dependencies |
| `tests/test_control_center.py` | Localhost-only control-center route exposure policy |

## Analysis Evidence

`python -m analysis.run_all` should complete all 12 studies and refresh
`analysis/artifacts/SUMMARY.txt`.

The most important current evidence boundaries:

- Section 10 reports `event_visible_fraction`, `true_degraded_fraction`,
  `background_event_fraction`, and `injected_window_coverage`.
- Section 10 `replica_bound_active` expected-kind coverage should remain `1.0`
  in its injection window.
- Section 10 full trace evidence lives in
  `analysis/artifacts/s10_trace_full.jsonl`.
- Cross-study event/replay/contract evidence lives in
  `analysis/artifacts/event_evidence_manifest.json`, which references Section
  10/11/12 artifacts plus `sre_stack_data_contract.json` with repo-relative
  paths. Its markdown contract lives in `docs/EVENT_EVIDENCE_MANIFEST.md`, and
  `python -m analysis.evidence_report` validates the top-level manifest shape,
  closed study/contract ID sets, required study/contract entry sets, required
  generic and entry-specific fields plus their value types, documented fixed
  values, bounded numeric ranges, artifact key sets, expected artifact
  extensions, repo-contained relative string paths, file existence,
  artifact metadata key parity, byte-identity SHA-256 digests, byte size values,
  JSON/JSONL/PNG parseability, valid runtime event payloads, stack contract
  non-production scope, stage event-kind registry membership, trace-event
  routing, and key manifest counts.
  `scripts.quality_gate_counts` fails if the manifest/report commands drop out
  of the current gate docs.
- Section 5 now includes radar + near-field fiducial evidence with source-use
  metrics; it is still synthetic and should not be described as production
  sensor integrity proof.
- Section 8 bounded allocation removes saturation violations, but residuals can
  remain; safe projection does not mean demand is fully satisfied.
- Section 11 Catch/SRE wrapper evidence should cover feasible quiet solves,
  total overload, and placement-infeasible residuals while preserving zero
  capacity violations after the bounded solve.
- Section 12 replay evidence should stay labeled as synthetic replay evidence,
  keep nominal background rows quiet, and surface expected event kinds including
  `stability_violation`; replay incident windows should recover to event-clean
  rows with bounded recovery ticks, each expected event row should carry an
  operator-action annotation, and the compound multi-signal window should retain
  full event-kind coverage plus a window-level operator action.
- Public/review entry points in
  `scripts.evidence_boundary_lint.PUBLIC_EVIDENCE_BOUNDARY_DOCS` are linted for
  unqualified production-readiness, official SpaceX implementation, and
  production-proof wording. Negated boundary wording such as "not production
  proof" remains allowed.
- `sre_control.stack_data_contract()` exposes the single-process research
  stack's stage inputs/outputs, direct event kinds, and route prefixes with
  `production_claim=false`; `analysis.evidence_report` checks generated trace
  events against those stage routes. This narrows the single-stack
  orchestration risk without claiming a distributed production control plane.

## HTML / Asset Entry

| Entry | Current status |
|---|---|
| `docs/V2_Knowledge/knowledge-base.html` | Canonical current HTML knowledge-base entry |
| `docs/knowledge-base.html` | V1 archive snapshot |
| `docs/assets/*` | Shared generated assets |
| `docs/V2_Knowledge/assets/*` | V2 HTML assets |

## Current Quality Conclusion

- Unit/integration tests: passing in the current workspace.
- Analysis studies: passing in the current workspace.
- Runtime event kinds: closed by registry/docs/counterexample tests.
- Dependency direction: guarded by import-graph tests.
- Remaining useful work is evidence-strengthening, not a known "cannot run"
  blocker.
