# Opus Review Packet

> Engineering packet that was submitted for Opus v2.0 re-review.
> Historical Opus v1.0 review artifacts remain under `docs/opus-review/v1.0/`.

## v2.0 Review Status

Opus v2.0 review has been returned and is now a historical external review
record for F50-F60/G1: `claude-review/docs/v2026-05-26/`. The latest
continuation review is Opus v2.1: `claude-review/docs/v2026-05-28/`.

This packet remains useful as the engineering snapshot that Opus reviewed, but
it is no longer the live open-risk ledger. F50–F60 have since been remediated
in the current workspace with regression tests; G1 has also been remediated by
the `quality_gate_counts` manifest→report self-healing gate. Use
`docs/codex-review/OPEN_RISKS.md` before submitting another review or merge
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

## 0. Review Position

This packet is the engineering snapshot that Opus v2.0 reviewed, not the live
open-risk ledger and not a claim that every low-priority advisory has been
exhausted.

Use these as the authoritative current-state documents:

| Purpose | Entry |
|---|---|
| Current completed/open state | `wiki/review-backlog.md` |
| Current risk register | `docs/codex-review/OPEN_RISKS.md` |
| Current quality gates | `docs/codex-review/QUALITY_GATES.md` |
| Current engineering handoff | `docs/codex-review/ENGINEERING_PACKET.md` |
| Event evidence manifest contract | `docs/EVENT_EVIDENCE_MANIFEST.md` |
| Stack data contract | `docs/STACK_DATA_CONTRACT.md` |
| Historical Opus findings | `docs/opus-review/v1.0/LINE_LEVEL_FINDINGS.md` |

Boundary statement:

- This repository is a public-material research and engineering reproduction.
- It does not claim SpaceX official implementation details.
- `analysis/` evidence is synthetic scenario evidence, not production proof.
- `starship/` remains the math/physical layer; `sre_control/` is the SRE
  migration layer.

## 1. Verification Snapshot For Current Handoff

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
python -m examples.demo_sre_loop
python -m examples.demo_powered_descent
python -m examples.demo_catch_phase
python -u -m scripts.quality_gate_counts
```

Observed outputs from the current workspace:

```text
quality gate pytest count: 613
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
- `tests/test_evidence_manifest.py` locks the manifest/report contract.
- `scripts.quality_gate_counts` fails if `analysis.evidence_manifest` or
  `analysis.evidence_report` drops out of the documented quality gates.

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
| B1/B2 | B1 is underway: stack-contract/trace-routing checks now live in `analysis/evidence_contracts.py`, artifact path/identity/parse/schema checks live in `analysis/evidence_artifacts.py`, and manifest shape checks live in `analysis/evidence_manifest_checks.py`, all with direct tests. Remaining refactor budget is the broader study-consistency split and B2's `tests/test_evidence_manifest.py` split. |

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
python -m analysis.evidence_manifest
python -m analysis.evidence_report
python -m scripts.control_center_browser_smoke --report-manifests --report-json analysis/artifacts/control-center-browser-evidence-report.json
python -m scripts.package_smoke
python -m scripts.control_center_integration_audit
python -m scripts.review_authority_lint
python -m examples.demo_sre_loop
python -m examples.demo_powered_descent
python -m examples.demo_catch_phase
python -u -m scripts.quality_gate_counts
```

Targeted evidence commands:

```powershell
python -m pytest tests/test_sre_control.py tests/test_ekf.py tests/test_contracts.py tests/test_event_schema.py -q
python -m pytest tests/test_failure_trace.py tests/test_synthetic_evidence_boundaries.py tests/test_evidence_manifest.py -q
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
- Do not treat old Opus v1.0 line-level artifacts as current truth; they are
  reproduction and historical review evidence. Current status is in
  `wiki/review-backlog.md` and `docs/codex-review/OPEN_RISKS.md`.
- The packet has already received Opus v2.0 review. Use
  `claude-review/docs/v2026-05-26/` and `docs/codex-review/OPEN_RISKS.md`
  before making a new review submission claim.
