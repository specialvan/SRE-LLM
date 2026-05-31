# 2026-05-15 Deep Review

> Historical audit artifact; it is not the current handoff.
> Opus review should start from `docs/opus-review/HANDOFF.md`, then verify
> live status in `wiki/review-backlog.md`,
> `docs/codex-review/OPEN_RISKS.md`, and
> `docs/codex-review/QUALITY_GATES.md`.

## Verdict

No P0 blocker found. The current branch runs: 77 collected tests pass and all 10 analysis studies complete. The main risk has shifted from "does the code work?" to "will the next reviewer or installed package see the same system the source tree currently has?"

Several earlier Claude/Codex findings are now implemented in code but still appear as active in older review packets. This report treats those as documentation and process drift, not code failures.

## Findings

### [P1] Installable package excludes the SRE control surface

Evidence:

- `pyproject.toml:20-22` only includes `starship*`.
- `README.md:186-191` documents `scripts/control_center_server.py` and `analysis/control_center_data.py` as part of the front-end control center.
- `README.md:220-239` presents `sre_control.SREControlStack` and `examples.demo_sre_loop` as supported entry points.
- `sre_control/__init__.py:22-61` exports the full SRE API surface.

Impact:

An installed `starship-recovery` distribution would ship the physical `starship` package while omitting the SRE adapters that the README, wiki, tests, and review packets now treat as first-class engineering output. This is a release/package correctness issue, not just a docs issue.

Suggested fix:

Update `pyproject.toml` to include `sre_control*` and decide whether `analysis` / `scripts` are package modules, optional extras, or source-only tooling. Add an installation smoke test that imports `starship`, `sre_control`, and the documented server entry point from an installed wheel or isolated target directory.

### [P1] Allocator last-good fallback does not fingerprint `zone_vector`

Evidence:

- `sre_control/stack.py:89-107` builds the allocator reuse signature from instance name and min/max only.
- `sre_control/weighted_balancer.py:30-35` makes `zone_vector` part of each `Instance`.
- `sre_control/weighted_balancer.py:50-57` uses `zone_vector` to build the actual allocation matrix.

Impact:

If instance topology or zone weights change while names and bounds remain stable, `_can_reuse_last_good_alloc()` may reuse an allocation computed for a different allocation matrix. That undermines the "validated fallback" claim for `WeightedLoadBalancer` recoverable errors.

Suggested fix:

Include `zone_vector` shape and values in `_allocator_signature()`. Add a regression test that mutates only `zone_vector` after a successful allocation, forces a recoverable balancer failure, and expects `bootstrap_zero_fallback` or another explicit fail-closed path rather than stale reuse.

### [P1] Canonical PR spec contradicts the current event taxonomy

Evidence:

- `PR-REQUIREMENTS.md:13-18` still says adapter exceptions must become `stability_violation` events.
- `sre_control/stack.py:23-36` says recoverable adapter failures emit `adapter_exception`, while programmer errors propagate.
- `docs/EVENT_SCHEMA.md:37-46` documents `adapter_exception` and its required cause fields.
- `docs/codex-review/CLAUDE_REFINED_SPEC.md:5` says live focus remains allocator fallback and EKF hardening, but current code and tests already include last-good allocator fallback and Joseph covariance update.

Impact:

`PR-REQUIREMENTS.md` is positioned as a PR-level functional requirements source, so this stale invariant can direct future agents to reintroduce the older `stability_violation` catch-all behavior that the code intentionally removed.

Suggested fix:

Revise I-5 to distinguish `adapter_exception` from `stability_violation`, refresh quality-gate counts, and add a short "superseded by commits" table for PR-D/PR-E/EKF hardening so the next pass does not chase already-shipped work.

### [P2] Docs/schema sync is described as required but not enforced against docs

Evidence:

- `docs/codex-review/CLAUDE_REFINED_SPEC.md:248-254` requires a docs/schema sync check.
- `tests/test_event_schema.py:184-211` checks that generated local events match `EVENT_COUNTEREXAMPLES`, and that every counterexample is specific.
- There is no test matching `docs/EVENT_SCHEMA.md` or `docs/RUNTIME_STATES.md` against `EVENT_COUNTEREXAMPLES`.

Impact:

The registry is well tested, but the reviewer-facing docs can still drift. Because this project relies heavily on cross-session review packets, docs drift is a real engineering defect.

Suggested fix:

Add a test that parses the event-kind table in `docs/EVENT_SCHEMA.md` and the emitter table in `docs/RUNTIME_STATES.md`, then compares those kinds with `sre_control.events.EVENT_COUNTEREXAMPLES`.

### [P2] Knowledge-base HTML has two competing canonical entries

Evidence:

- `README.md:175-183` points readers to `docs/knowledge-base.html` and `docs/assets/`.
- `docs/knowledge-base.html:173` labels itself `Knowledge Base · v0.1`.
- `docs/V2_Knowledge/knowledge-base.html:942` says V2 should be used to re-layout the V1 `docs/knowledge-base.html`.
- `docs/codex-review/OPEN_RISKS.md:11` already records this as knowledge-base drift.

Impact:

Reviewers can enter through the older V1 HTML while newer evidence lives in V2 and review packets. This creates "which page is canonical?" friction and makes HTML review less trustworthy.

Suggested fix:

Pick one public HTML entry. Either promote V2 into `docs/knowledge-base.html` or mark V1 as an archive with a visible redirect-style note. Add a lightweight build/test check that fails if both pages claim to be current.

### [P2] Joseph covariance documentation contains stale incorrect snippets

Evidence:

- `starship/ekf.py:91-97` correctly uses Joseph form plus covariance symmetrization.
- `docs/SPECIAL_SOLUTIONS_DERIVATIONS.md:44-45` shows the simple `(I-KH)P` form and labels it Joseph before adding the correct equation on the next line.
- `docs/SPECIAL_SOLUTIONS_DERIVATIONS.md:826` again labels `P_new = (I - K @ H) @ P_pred` as Joseph form.

Impact:

The implementation is fixed, but the derivation document can teach the old numerically weaker update. This matters because EKF stability has been one of the recurring reviewer concerns.

Suggested fix:

Replace the simple covariance update snippets with the full Joseph expression and add a short note that `(I-KH)P` is the legacy simplified form, not the current implementation.

### [P2] Quality-gate counts and version metadata are inconsistent

Evidence:

- `PR-REQUIREMENTS.md:3` declares version `0.3.7`.
- `pyproject.toml:7`, `starship/__init__.py:76`, and `sre_control/__init__.py:63` remain `0.1.0`.
- `PR-REQUIREMENTS.md:19-20` still records `pytest tests -q # 51 passed`.
- `docs/codex-review/QUALITY_GATES.md:13-32` records `64 passed` and older per-file counts.
- Current collection is 77 tests across 13 test files, including `tests/test_control_center.py`.

Impact:

The repository has functional progress without a matching release/version model. Reviewers cannot tell whether `v0.3.x` is a spec version only, a package version, or a release candidate.

Suggested fix:

Introduce a small version policy: spec version may remain independent, but package version, `__version__`, and quality-gate evidence need explicit labels and refresh automation.

### [P3] Review packets mix active findings with resolved findings

Evidence:

- `docs/codex-review/CLAUDE_DEEP_REVIEW.md:15-18` lists per-sensor gate, allocator fallback, and EKF Joseph form as active findings.
- `docs/codex-review/ENGINEERING_PACKET.md:122-124` repeats those as reviewer priorities.
- `docs/codex-review/ENGINEERING_PACKET.md:136-139` later says allocator fallback, per-sensor gate, and Joseph hardening have been implemented.

Impact:

The packet is useful historically, but without a status overlay, the first table can send a reviewer toward solved issues.

Suggested fix:

Add a `Finding status` block to old packets or move stale findings into an "implemented since this packet" appendix. This audit package uses `Active`, `Resolved`, and `Watch` to avoid the same failure mode.

## Resolved Since Earlier Review

| Earlier concern | Current evidence | Status |
|---|---|---|
| Per-sensor innovation gates | `sre_control/signal_fusion.py:94-100`, `tests/test_sre_control.py:216-330` | Resolved for minimal P1 slice |
| Allocator recoverable fallback always returns zero shares | `sre_control/stack.py:277-294`, `tests/test_contracts.py:391-498` | Resolved, with new `zone_vector` signature gap above |
| EKF covariance update lacks Joseph form | `starship/ekf.py:91-97`, `tests/test_ekf.py:34-88` | Resolved in code; docs still stale |
| Programmer errors swallowed by stack | `sre_control/stack.py:23-36`, `tests/test_contracts.py` programmer-error coverage | Resolved by taxonomy |

## Git Review

The commit history shows a coherent review loop: initial backup, architecture/docs, runtime events, review packets, PR-M/PR-L implementation, then analysis/docs refreshes. The history is linear and pushed to `origin/spacex-session`.

Risks:

- No git tags exist, despite spec versions up to `0.3.7`.
- All 72 commits in the available history are attributed to one local author, so authorship cannot distinguish Claude, Codex, and human edits.
- Some docs use "see git log" rather than a stable evidence table, which is acceptable for handoff notes but weak for long-lived audit.

## Next Review Route

1. Fix package metadata and add install smoke test.
2. Add allocator fallback test for `zone_vector` mutation.
3. Refresh `PR-REQUIREMENTS.md` I-5, quality-gate counts, and shipped/deferred status.
4. Add docs/schema sync test for `EVENT_SCHEMA.md` and `RUNTIME_STATES.md`.
5. Decide the canonical HTML knowledge-base entry.
6. Clean Joseph-form snippets in `SPECIAL_SOLUTIONS_DERIVATIONS.md`.
