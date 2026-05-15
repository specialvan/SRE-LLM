# 2026-05-15 Continuation Evidence Snapshot

## Repository State

Command:

```bash
git status --short --branch
```

Observed during the continuation pass:

```text
## spacex-session...origin/spacex-session
 M PR-REQUIREMENTS.md
 M README.md
 M docs/CODEX_HANDOFF.md
 M docs/RUNTIME_STATES.md
 M docs/SPECIAL_SOLUTIONS_DERIVATIONS.md
 M docs/V2_Knowledge/knowledge-base.html
 M docs/claude-review/README.md
 M docs/codex-review/CLAUDE_DEEP_REVIEW.md
 M docs/codex-review/ENGINEERING_PACKET.md
 M docs/codex-review/QUALITY_GATES.md
 M docs/codex-review/README.md
 M docs/knowledge-base.html
 M pyproject.toml
 M sre_control/stack.py
 M tests/test_contracts.py
 M tests/test_event_schema.py
?? docs/claude-development-audit/
?? docs/superpowers/
```

Interpretation:

- The audit package exists on disk but is not yet tracked.
- Multiple tracked files already contain local hardening work that changes the status of the first audit report.
- The implementation fixes include `pyproject.toml` package discovery and `sre_control/stack.py` allocator signatures.
- The docs fixes include `README.md`, `PR-REQUIREMENTS.md`, `docs/CODEX_HANDOFF.md`, `docs/RUNTIME_STATES.md`, `docs/SPECIAL_SOLUTIONS_DERIVATIONS.md`, `docs/knowledge-base.html`, `docs/V2_Knowledge/knowledge-base.html`, `docs/claude-review/README.md`, and several `docs/codex-review/` files.

## Current Git Head

Command:

```bash
git log --date=iso-strict --pretty=format:"%h%x09%ad%x09%an%x09%s" -n 1
```

Observed head:

```text
13e534e  2026-05-14T21:17:52+08:00  yangqidog  chore: 鍚屾鏈€鏂板垎鏋愮粨鏋?SUMMARY.txt
```

## Test Collection

Command:

```bash
python -m pytest --collect-only -q
```

Observed collection:

```text
tests/test_allocation.py: 1
tests/test_contracts.py: 19
tests/test_control_center.py: 4
tests/test_ekf.py: 4
tests/test_event_schema.py: 5
tests/test_failure_trace.py: 10
tests/test_import_graph.py: 2
tests/test_mpc.py: 1
tests/test_quaternion.py: 3
tests/test_rigid_body.py: 2
tests/test_sre_control.py: 21
tests/test_stability_monitor.py: 8
tests/test_thrust_constraints.py: 3
```

Total: 85 collected tests.

Command:

```bash
python -m pytest tests -q
```

Observed result:

```text
Exit code 0 over 85 collected tests.
```

The quiet pytest output was dot-only:

```text
........................................................................ [ 87%]
..........                                                               [100%]
```

## Evidence Reconciliation

The first report said `pyproject.toml` only included `starship*`; the current file includes both packages:

```text
[tool.setuptools.packages.find]
include = ["starship*", "sre_control*"]
exclude = ["tests*", "examples*"]
```

The first report said `_allocator_signature()` ignored `zone_vector`; the current implementation fingerprints zone values:

```text
inst.name,
tuple(float(value) for value in inst.zone_vector),
float(inst.rps_min),
float(inst.rps_max),
```

The current working tree also adds a regression test named:

```text
test_sre_stack_refuses_stale_alloc_history_when_only_zone_vector_changes
```

The first report said docs/schema sync was not enforced; the current working tree adds:

```text
test_event_schema_doc_kinds_match_registry
test_runtime_states_doc_emitters_match_registry
```

These are working-tree facts, not committed-release facts until the modified tests and audit package are committed.

The first report said the canonical PR spec still used the old adapter-exception invariant; the current working tree rewrites I-5 to use `adapter_exception` for `RecoverableControlError` and reserve `stability_violation` for Lyapunov/stability red lines.

The first report said Joseph-form snippets were misleading; the current working tree replaces the simplified covariance update with the full Joseph expression in `docs/SPECIAL_SOLUTIONS_DERIVATIONS.md`.

The current working tree changes quality-gate docs to say `85 passed`, matching the command evidence above.

The current working tree also clarifies HTML knowledge-base entry points: `README.md` and V2 HTML identify `docs/V2_Knowledge/knowledge-base.html` as canonical, while V1 `docs/knowledge-base.html` is labeled as an archive snapshot.

The current working tree refreshes the V2 HTML event index to 11 kinds, adds `adapter_exception`, and keeps `stability_violation` scoped to `StabilityGuard` / Lyapunov violations.

## Remaining Watch Anchors

| Area | Anchor |
|---|---|
| Local-only review state | `git status --short --branch` modified/untracked files |
| Quality-gate count remains hand-edited | Current-facing docs now say 85 tests, but there is still no generated quality-gate source of truth. |
