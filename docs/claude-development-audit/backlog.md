# Audit Backlog

Status values:

- `Active`: current risk or confirmed defect.
- `Resolved`: implemented in current code, but kept for history.
- `Watch`: not broken now, but easy to regress.

## Active

| ID | Priority | Area | Issue | Next action |
|---|---|---|---|---|
| — | — | — | No active audit items after this pass. | Continue watch-list review and add new findings as evidence appears. |

## Resolved

| ID | Area | Resolution evidence |
|---|---|---|
| RES-001 | Per-sensor gate | `Signal.gate_threshold`, `_resolve_threshold()`, trace `threshold_used`, and tests for mixed accept/reject are present. |
| RES-002 | Allocator zero fallback | `SREControlStack` now reuses last-good shares when the allocator signature is valid, and falls back to zero only on bootstrap/no valid history. |
| RES-003 | EKF Joseph update | `starship/ekf.py` uses Joseph form and symmetrizes covariance; `tests/test_ekf.py` covers symmetry, PSD, and gated no-op behavior. |
| RES-004 | Programmer-error swallowing | Stack catches `RecoverableControlError` only; programmer errors propagate by design. |
| RES-005 | Allocator topology fingerprint | Current `_allocator_signature()` includes `Instance.zone_vector`, and `tests/test_contracts.py` adds a topology-only mutation regression; committed in `72e960c`. |
| RES-006 | Docs/schema sync tests | `tests/test_event_schema.py` parses `docs/EVENT_SCHEMA.md` and `docs/RUNTIME_STATES.md` against `EVENT_COUNTEREXAMPLES`; committed in `72e960c`. |
| RES-007 | Package discovery | `pyproject.toml` includes both `starship*` and `sre_control*`; committed in `72e960c`. |
| RES-008 | Review package created | `docs/claude-development-audit/` contains reports, evidence snapshots, git timeline, backlog, and completion audit; committed in `72e960c`. |
| RES-009 | Audit package status finalized | Completion-audit status was reconciled after commit; committed in `93e85ab`. |
| RES-010 | Historical event-count wording clarified | Historical 8/10/11-kind references were clarified in review docs; committed in `6000034`. |
| RES-011 | Quality-gate count aligned | V2 and audit report count were aligned back to the verified 83-test suite; committed in `2fc5b5e`. |
| RES-012 | Analysis summary refreshed | `analysis/artifacts/SUMMARY.txt` was regenerated after final verification; committed in `0785d9e`. |
| RES-013 | Final analysis evidence synced | Completion audit reflects the final `analysis.run_all` timing; committed in `0b2292f`. |
| RES-014 | Adapter exception taxonomy docs | Canonical spec, handoff docs, architecture notes, and V1 event table now route recoverable adapter failures to `adapter_exception`; committed in `c1dc48d`. |
| RES-015 | Version policy documented | `PR-REQUIREMENTS.md` now separates spec/review-ledger version from Python package release version in NFR-7. |
| RES-016 | Joseph-form derivation docs | `docs/SPECIAL_SOLUTIONS_DERIVATIONS.md` now separates standard covariance form from full Joseph form in formulas and code snippets; verified with `pytest tests/test_ekf.py tests/test_event_schema.py -q`. |
| RES-017 | Generated quality-gate counts | `scripts/quality_gate_counts.py` updates current-facing pytest counts after a real full-suite pytest pass, pass/collection parity check, and installed-wheel smoke with subprocess timeouts; current generated count is 99. |
| RES-018 | HTML canonical entry | `README.md`, V1 HTML, and V2 HTML now identify `docs/V2_Knowledge/knowledge-base.html` as the canonical current entry and `docs/knowledge-base.html` as a V1 archive snapshot. |
| RES-019 | Installed wheel smoke | `scripts/package_smoke.py` builds the wheel, verifies `starship` and `sre_control` are present, imports both from the wheel path, and is covered by `tests/test_package_smoke.py`. |

## Watch

| ID | Area | Watch condition |
|---|---|---|
| WATCH-001 | Synthetic evidence | Keep section 5 `pos_p95` regression and section 8 residual non-improvement visible in reports. |
| WATCH-002 | Cause taxonomy | `adapter_exception.cause_type` is currently coarse (`control_domain`). Split only when a real routing need appears. |
| WATCH-003 | Control center | Server is local-host restricted; keep it this way unless auth and static-file policy are added. |
| WATCH-004 | Git release hygiene | Add tags only if package/spec versions become release promises. |
