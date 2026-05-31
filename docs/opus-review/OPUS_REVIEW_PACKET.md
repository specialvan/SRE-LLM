# Opus Review Packet

> Current Opus re-entry packet for reviewing the live `spacex-session`
> workspace. Historical Opus v1.0/v2.0/v2.1 and v2026-05-31 returned review
> artifacts remain linked below for traceability, but they are not the current
> completed/open ledger.

## 0. How To Review This Packet Now

Start from the live handoff and ledgers, then use this packet as the command and
evidence map:

1. Read `docs/opus-review/HANDOFF.md` first for the current reviewer runbook,
   dirty-worktree caveats, content partitions, and focused review areas.
   If you opened this packet directly, run the handoff's
   `Git Review Scope Snapshot` commands first:
   `git status --short --branch --untracked-files=all`,
   `git diff --name-status`, `git ls-files --others --exclude-standard`, and
   `git diff --check`; keep dirty/untracked files in the review scope, or if
   the packet has already been committed, review the content-split commits in
   the partition order recorded there.
2. Read `wiki/review-backlog.md`, `docs/codex-review/OPEN_RISKS.md`, and
   `docs/codex-review/QUALITY_GATES.md` before historical findings. These are
   the current completion, risk, and command-gate sources of truth.
3. Run the verification commands in Section 1 and the targeted commands in
   Section 5 before making pass/fail claims.
4. Treat `claude-review/docs/v2026-05-26/`,
   `claude-review/docs/v2026-05-28/`, `claude-review/docs/v2026-05-31/`, and
   `docs/opus-review/v1.0/` as historical review inputs for traceability only.

Current synchronized pytest count: `943`.

Boundary statement:

- This repository is a public-material research and engineering reproduction.
- It does not claim SpaceX official implementation details.
- `analysis/` evidence is synthetic scenario/replay evidence, not production
  proof.
- `starship/` remains the math/physical layer; `sre_control/` is the SRE
  migration layer.

## Historical Context

Opus v1.0, v2.0, and v2.1 are historical review inputs. Their findings are
useful for traceability, but current completed/open status and command
authority live in `wiki/review-backlog.md`,
`docs/codex-review/OPEN_RISKS.md`, and
`docs/codex-review/QUALITY_GATES.md`.

The v2026-05-31 returned review packet is also historical context. It found
M1 pytest-count documentation drift and M2 an incomplete reviewer-side
`quality_gate_counts` capture. Current status must be checked through the live
handoff, quality gates, and fresh command output rather than the packet-time
871/873 snippets recorded in that review.

### v2.0/v2.1 Review Status

Opus v2.0 review has been returned and is now a historical external review
record for F50-F60/G1: `claude-review/docs/v2026-05-26/`. The latest
continuation review is Opus v2.1: `claude-review/docs/v2026-05-28/`.

The old v2.0 packet remains useful as the engineering snapshot that Opus
reviewed, but it is no longer the live open-risk ledger. F50-F60 have since
been remediated in the current workspace with regression tests; G1 has also
been remediated by the `quality_gate_counts` manifest/report self-healing gate.
Use `wiki/review-backlog.md`, `docs/codex-review/OPEN_RISKS.md`, and
`docs/codex-review/QUALITY_GATES.md` before submitting another review or merge
request.

Continuation review note:

- A follow-up independent reviewer pass was run in this workspace after the
  v2.0 packet. It found two code/process issues that are now fixed here:
  allocator fallback traces no longer emit non-standard JSON `NaN`, and
  `scripts.quality_gate_counts` validates quality-gate command presence across
  PR, V2 HTML, Codex quality gates, and this Opus packet.
- The v2.1 continuation findings F61-F81 are now remediated in the current
  workspace; use the live ledgers for current status rather than treating this
  packet as the sole truth source.
- The unrelated nested `LLM-WIKI/` workspace is now ignored so normal
  `git ls-files --others --exclude-standard` review sweeps do not include it.
- The remaining merge-scope risk is git hygiene: the current green state spans
  modified and untracked source, tests, generated evidence, and review docs.
  Any handoff/merge must include the new core files named by `git status`, not
  only the previously tracked edits.

## Current Authority Map

This packet is a current re-entry map, not a claim that every low-priority
advisory has been exhausted.

Use these as the authoritative current-state documents:

| Purpose | Entry |
|---|---|
| Current completed/open state | `wiki/review-backlog.md` |
| Current risk register | `docs/codex-review/OPEN_RISKS.md` |
| Current quality gates | `docs/codex-review/QUALITY_GATES.md` |
| Current engineering handoff | `docs/codex-review/ENGINEERING_PACKET.md` |
| Event evidence manifest contract | `docs/EVENT_EVIDENCE_MANIFEST.md` |
| Stack data contract | `docs/STACK_DATA_CONTRACT.md` |
| Current Opus handoff | `docs/opus-review/HANDOFF.md` |
| Historical Opus findings | `docs/opus-review/v1.0/LINE_LEVEL_FINDINGS.md`, `claude-review/docs/v2026-05-26/`, `claude-review/docs/v2026-05-28/`, `claude-review/docs/v2026-05-31/` |

## 1. Current Verification Snapshot

Current handoff commands:

```powershell
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

Observed outputs from the current workspace:

```text
quality gate pytest count: 943
artifact_check ok studies=3 files=8
```

Reviewer note: `analysis.evidence_manifest` should be run before
`analysis.evidence_report` when generated artifacts have been refreshed, because
the manifest stores SHA-256 and byte-size identity for evidence artifacts.

## 2. Evidence Assets Under Review

Machine-readable evidence:

| Artifact | Purpose |
|---|---|
| `analysis/artifacts/event_evidence_manifest.json` | Stable index for Section 10/11/12 event evidence plus stack contract |
| `analysis/artifacts/s10_trace_full.jsonl` | Full Section 10 runtime event trace |
| `analysis/artifacts/s10_trace_sample.jsonl` | Section 10 sample trace for inspection |
| `analysis/artifacts/s11_catch_sre_wrapper_diagnostics.json` | Catch/SRE wrapper diagnostics |
| `analysis/artifacts/s12_replay_trace.jsonl` | Fixed replay trace output |
| `analysis/artifacts/s12_replay_diagnostics.json` | Replay metrics and recovery diagnostics |
| `analysis/artifacts/sre_stack_data_contract.json` | Exported research-stage stack contract |

Visual evidence:

| Artifact | Purpose |
|---|---|
| `analysis/artifacts/s10_event_density.png` | Section 10 event-density visualization |
| `analysis/artifacts/s11_catch_sre_wrapper.png` | Section 11 wrapper residual/capacity visualization |
| `docs/V2_Knowledge/knowledge-base.html` | Canonical HTML knowledge-base entry |

Verifier coverage:

- `analysis.evidence_report` checks manifest shape, study/contract identity,
  path portability, repo containment, artifact existence, SHA-256/byte-size
  identity, JSON/JSONL/PNG parseability, event schema validity, stack-contract
  scope, stage-event routing, and count consistency.
- Split report-path tests lock the manifest/report contract: residual smoke and
  byte-identity coverage in `tests/test_evidence_manifest.py`, top-level
  manifest rejection paths in `tests/test_evidence_report_manifest_shape.py`,
  study-entry manifest paths in `tests/test_evidence_report_study_shape.py`,
  contract-entry manifest paths in `tests/test_evidence_report_contract_shape.py`,
  artifact path/key/extension paths in `tests/test_evidence_report_artifact_paths.py`,
  S10 trace paths in `tests/test_evidence_trace_report.py`, S11 wrapper paths in
  `tests/test_evidence_wrapper_report.py`, S12 replay diagnostics field paths
  in `tests/test_evidence_replay_report.py`, S12 replay consistency paths in
  `tests/test_evidence_replay_consistency_report.py`, S12 replay
  trace/fixture/schema paths in `tests/test_evidence_replay_artifacts_report.py`,
  stack-contract artifact scope/route/stage-interface report paths in
  `tests/test_evidence_contract_report.py`, fallback field/map report paths in
  `tests/test_evidence_contract_fallback_report.py`, trace-route fallback,
  adapter-family, fault-family, exception-cause, and recoverability paths in
  `tests/test_evidence_contract_trace_report.py`, and split-boundary plus
  trace-event routing paths in `tests/test_evidence_contract_boundary_report.py`.
- `scripts.quality_gate_counts` fails if `analysis.evidence_manifest` or
  `analysis.evidence_report` drops out of the documented quality gates.
- `scripts.evidence_boundary_lint` now has a reviewer-facing CLI and fails if
  any public prose doc under `docs/`, `claude-review/`, or `wiki/` is outside
  boundary-lint coverage, or if covered prose makes unqualified production or
  SpaceX-internal claims. The dynamic coverage guard lives in
  `tests/test_synthetic_evidence_boundaries.py`.

## 3. Opus v1.0 Findings Resolved In This Packet

Blocking/high-priority slice:

| Finding | Status | Evidence |
|---|---|---|
| F01 | Resolved | `FastTrafficSwitcher.plan()` preserves terminal share under `safety_margin`; unit regression in `tests/test_sre_control.py` |
| F02 | Resolved | `WeightedLoadBalancer.allocate()` wraps solver failures as `RecoverableControlError` |
| F03 | Resolved | `starship.EKF.update()` gates singular innovation covariance as a no-op |
| F04/F25 | Resolved | `adapter_exception.adapter_family` derives from `stack_data_contract().event_stage_routes` |
| F05 | Resolved by contract | `safe_action` is explicitly L2 demand magnitude; `zone_target` remains placement |
| F11/F12 | Resolved | strict per-kind event schemas for all runtime kinds |

Numerical / validator / data-contract slice:

| Finding | Status | Evidence |
|---|---|---|
| F06 | Resolved | Section 10 now feeds back `replicas_next` directly; the nominal recovery forecast is explicit and tested |
| F13 | Resolved | `evidence_manifest` passes artifact directories explicitly instead of monkey-patching globals |
| F15 | Resolved | `quality_gate_counts.py` uses a data-driven replacement target table with path-qualified errors |
| F07 | Resolved | `SignalFusion` uses exact OU exponential discretization |
| F08 | Resolved | `CanaryScheduler` refits slope after rejected rollout observations |
| F09 | Resolved | Section 10 and evidence-report empty visibility semantics are aligned |
| F10 | Resolved | `PoolCapacityPlanner.plan()` uses true `math.ceil()` |
| F14 | Resolved | S10 JSONL artifacts use sorted keys |
| F16 | Resolved | evidence-boundary lint checks suffix negation window |
| F17 | Resolved | `SREControlStack` passes cumulative elapsed time to stability monitoring under variable `dt` |
| F18 | Resolved | load balancer validates empty/mismatched zone vectors at construction |
| F19 | Resolved | gate thresholds must be positive when set |
| F20 | Resolved | `SignalFusion` caps consecutive rejection counters and surfaces saturated trace state |
| F21 | Resolved | Section 11 regime-count test no longer hard-codes `40/40/40` |
| F22 | Resolved | `starship.EKF` now defaults to a `1e-12` covariance eigenvalue floor while explicit `0.0` remains an opt-out |
| F23 | Resolved | S10 trace-time validation uses tick-scaled tolerance |
| F32 | Resolved | `PoolCapacityPlanner.rps_per_conn` is configurable and used consistently |
| F33 | Resolved | `FastTrafficSwitcher` rejects non-positive `rate_max` |
| F31 | Resolved | `analysis.evidence_report` now collects multiple JSONL, trace-shape, fixture-shape, and schema errors instead of stopping at the first row |
| F37 | Resolved | unrecovered replay diagnostics use JSON `null`, not `Infinity` |
| F39 | Resolved | SHA-256 shape validation accepts uppercase hex while byte identity remains strict |
| F41 | Resolved | `analysis.run_all` records per-study failures in `SUMMARY.txt`, continues later studies, then exits nonzero |
| F42 | Resolved | replay operator-action tests check coverage/non-empty strings, not exact prose |

Evidence-ledger slice:

- Section 10/11/12 evidence is now indexed by
  `analysis/artifacts/event_evidence_manifest.json`.
- `docs/EVENT_EVIDENCE_MANIFEST.md` documents that manifest.
- `analysis.evidence_report` provides a reviewer-facing CLI and fails on stale
  artifact identity, malformed evidence, invalid runtime events, or contract
  drift.
- `sre_control.stack_data_contract()` exports non-production research metadata
  and stage event routing.

## 4. Current Known Remaining Work

These remain useful follow-up items. They are not blockers for this re-review
packet unless Opus wants the scope expanded.

| Finding / Backlog | Current stance |
|---|---|
| F24/F28/F36/F38/F40 | maintainability/refactor advisories remain non-blocking |
| B1/B2 | B1 has advanced: stack-contract/trace-routing checks now live in `analysis/evidence_contracts.py`, artifact path/identity/parse/schema checks live in `analysis/evidence_artifacts.py`, manifest shape checks live in `analysis/evidence_manifest_checks.py`, and S10/S11/S12 study consistency checks live in `analysis/evidence_consistency.py`, all with direct tests. B2 has split direct artifact-validator helper tests into `tests/test_evidence_artifacts.py`, manifest-check helpers into `tests/test_evidence_manifest_checks.py`, consistency-helper diagnostics into `tests/test_evidence_consistency.py`, manifest generation/docs tests into `tests/test_evidence_manifest_generation.py`, top-level manifest report-path tests into `tests/test_evidence_report_manifest_shape.py`, study-entry report-path tests into `tests/test_evidence_report_study_shape.py`, contract-entry report-path tests into `tests/test_evidence_report_contract_shape.py`, artifact path/key/extension report-path tests into `tests/test_evidence_report_artifact_paths.py`, stack-contract artifact report-path tests into `tests/test_evidence_contract_report.py`, stack-contract fallback report-path tests into `tests/test_evidence_contract_fallback_report.py`, stack-contract trace-route report-path tests into `tests/test_evidence_contract_trace_report.py`, stack-contract split-boundary report-path tests into `tests/test_evidence_contract_boundary_report.py`, S10 trace report-path checks into `tests/test_evidence_trace_report.py`, S11 catch-wrapper report-path checks into `tests/test_evidence_wrapper_report.py`, S12 replay diagnostics field checks into `tests/test_evidence_replay_report.py`, S12 replay consistency checks into `tests/test_evidence_replay_consistency_report.py`, and S12 replay trace/fixture artifact checks into `tests/test_evidence_replay_artifacts_report.py`. The residual report orchestrator cleanup has landed; remaining work is future review-ledger hygiene when new packets arrive. |

Recommended Opus focus for this re-review:

1. Re-run the quality gates and evidence report from Section 1.
2. Inspect `wiki/review-backlog.md` for completed-item evidence.
3. Inspect `docs/codex-review/OPEN_RISKS.md` for current risk framing.
4. Spot-check resolved high-priority findings F01-F05/F11/F12.
5. Review whether the remaining open items should block merge or be scheduled
   as follow-up research slices.

## 5. Review Commands

Minimum review command set:

```powershell
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

Targeted evidence commands:

```powershell
python -m pytest tests/test_sre_control.py tests/test_ekf.py tests/test_contracts.py tests/test_event_schema.py -q
python -m pytest tests/test_failure_trace.py tests/test_synthetic_evidence_boundaries.py tests/test_evidence_manifest.py tests/test_evidence_artifacts.py tests/test_evidence_manifest_checks.py tests/test_evidence_consistency.py tests/test_evidence_contracts.py tests/test_evidence_manifest_generation.py tests/test_evidence_report_manifest_shape.py tests/test_evidence_report_study_shape.py tests/test_evidence_report_contract_shape.py tests/test_evidence_report_artifact_paths.py tests/test_evidence_trace_report.py tests/test_evidence_wrapper_report.py tests/test_evidence_replay_report.py tests/test_evidence_replay_consistency_report.py tests/test_evidence_replay_artifacts_report.py tests/test_evidence_contract_report.py tests/test_evidence_contract_fallback_report.py tests/test_evidence_contract_trace_report.py tests/test_evidence_contract_boundary_report.py -q
python -m pytest tests/test_control_center_browser_smoke.py tests/test_control_center_browser_dom.py tests/test_control_center_browser_manifest.py tests/test_control_center_browser_error_manifest.py tests/test_control_center_browser_report.py tests/test_control_center_integration_audit.py -q
python -m pytest tests/test_quality_gate_counts.py -q
python -m analysis.run_all
```

Manifest sanity outputs to expect:

```text
evidence_scope synthetic_sre_event_evidence
s10_failure_trace section=10 events=16
s11_catch_sre_wrapper section=11 visible=1.0
s12_sre_replay section=12 events=11.0 ticks=19
artifact_check ok studies=3 files=8
```

## 6. Submission Caveats

- The worktree is intentionally large because this packet spans code, tests,
  docs, generated evidence artifacts, and new review-support scripts.
- Superpowers plan/spec inventories live in
  `docs/superpowers/plans/README.md` and
  `docs/superpowers/specs/README.md`. Before treating dated execution traces or
  design notes as review evidence, confirm every dated plan or spec artifact in
  the dirty/untracked surface is either carried into this packet's review scope
  or intentionally excluded with a separate reason.
- Do not treat old Opus v1.0 line-level artifacts as current truth; they are
  reproduction and historical review evidence. Current status and command
  authority are in `wiki/review-backlog.md`,
  `docs/codex-review/OPEN_RISKS.md`, and
  `docs/codex-review/QUALITY_GATES.md`.
- The packet has already received Opus v2.0 review. Use
  `wiki/review-backlog.md`, `docs/codex-review/OPEN_RISKS.md`,
  `docs/codex-review/QUALITY_GATES.md`, and
  `claude-review/docs/v2026-05-26/` before
  making a new review submission claim.
