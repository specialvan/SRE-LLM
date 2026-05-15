# Audit Backlog

Status values:

- `Active`: current risk or confirmed defect.
- `Resolved`: implemented in current code, but kept for history.
- `Watch`: not broken now, but easy to regress.

## Active

| ID | Priority | Area | Issue | Next action |
|---|---|---|---|---|
| AUDIT-005 | P2 | HTML knowledge base | V1 and V2 HTML entries still compete; V2 has stale quality/event summary text. | Promote one canonical page or label V2/V1 roles clearly. |
| AUDIT-006 | P2 | Math docs | `SPECIAL_SOLUTIONS_DERIVATIONS.md` still contains misleading Joseph-form shorthand. | Replace with full Joseph form using encoding-safe edit. |
| AUDIT-010 | P2 | Quality gates | Current test collection is 83, and counts remain hand-edited in several docs. | Generate quality-gate counts from pytest collection. |

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

## Watch

| ID | Area | Watch condition |
|---|---|---|
| WATCH-000 | Packaging | Source imports are covered; installed-wheel smoke testing is still a release-level follow-up. |
| WATCH-001 | Synthetic evidence | Keep section 5 `pos_p95` regression and section 8 residual non-improvement visible in reports. |
| WATCH-002 | Cause taxonomy | `adapter_exception.cause_type` is currently coarse (`control_domain`). Split only when a real routing need appears. |
| WATCH-003 | Control center | Server is local-host restricted; keep it this way unless auth and static-file policy are added. |
| WATCH-004 | Git release hygiene | Add tags only if package/spec versions become release promises. |
