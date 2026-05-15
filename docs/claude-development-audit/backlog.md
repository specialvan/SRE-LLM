# Audit Backlog

Status values:

- `Active`: current risk or confirmed defect.
- `Resolved`: implemented in current code, but kept for history.
- `Watch`: not broken now, but easy to regress.

## Active

| ID | Priority | Area | Issue | Next action |
|---|---|---|---|---|
| AUDIT-003 | P1 | Canonical spec | `PR-REQUIREMENTS.md` still contains historical `stability_violation` wording for adapter exceptions and stale 51-test gates. | Refresh I-5 and quality gates with UTF-8-safe editing. |
| AUDIT-005 | P2 | HTML knowledge base | V1 and V2 HTML entries still compete; V2 has stale quality/event summary text. | Promote one canonical page or label V2/V1 roles clearly. |
| AUDIT-006 | P2 | Math docs | `SPECIAL_SOLUTIONS_DERIVATIONS.md` still contains misleading Joseph-form shorthand. | Replace with full Joseph form using encoding-safe edit. |
| AUDIT-007 | P2 | Versioning | Spec version and package version semantics are not explicitly separated in the canonical spec. | Add a version policy block. |
| AUDIT-010 | P2 | Quality gates | Current test collection is 83, but several current-facing docs still say 51/64 or stale event-kind counts. | Generate or safely refresh quality-gate counts. |

## Resolved

| ID | Area | Resolution evidence |
|---|---|---|
| RES-001 | Per-sensor gate | `Signal.gate_threshold`, `_resolve_threshold()`, trace `threshold_used`, and tests for mixed accept/reject are present. |
| RES-002 | Allocator zero fallback | `SREControlStack` now reuses last-good shares when the allocator signature is valid, and falls back to zero only on bootstrap/no valid history. |
| RES-003 | EKF Joseph update | `starship/ekf.py` uses Joseph form and symmetrizes covariance; `tests/test_ekf.py` covers symmetry, PSD, and gated no-op behavior. |
| RES-004 | Programmer-error swallowing | Stack catches `RecoverableControlError` only; programmer errors propagate by design. |
| RES-005 | Allocator topology fingerprint | Current `_allocator_signature()` includes `Instance.zone_vector`, and `tests/test_contracts.py` adds a topology-only mutation regression. Pending commit. |
| RES-006 | Docs/schema sync tests | `tests/test_event_schema.py` now parses `docs/EVENT_SCHEMA.md` and `docs/RUNTIME_STATES.md` against `EVENT_COUNTEREXAMPLES`. Pending commit. |
| RES-007 | Package discovery | `pyproject.toml` includes both `starship*` and `sre_control*`. Pending commit. |
| RES-008 | Review package created | `docs/claude-development-audit/` contains reports, evidence snapshots, git timeline, backlog, and completion audit. Pending commit. |

## Watch

| ID | Area | Watch condition |
|---|---|---|
| WATCH-000 | Packaging | Source imports are covered; installed-wheel smoke testing is still a release-level follow-up. |
| WATCH-001 | Synthetic evidence | Keep section 5 `pos_p95` regression and section 8 residual non-improvement visible in reports. |
| WATCH-002 | Cause taxonomy | `adapter_exception.cause_type` is currently coarse (`control_domain`). Split only when a real routing need appears. |
| WATCH-003 | Control center | Server is local-host restricted; keep it this way unless auth and static-file policy are added. |
| WATCH-004 | Git release hygiene | Add tags only if package/spec versions become release promises. |
