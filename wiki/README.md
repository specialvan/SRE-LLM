# SpaceX to SRE Project Wiki

This wiki is the cross-session knowledge entry for the current project. It
records stable context, evidence boundaries, runtime chains, and review backlog
state. Current code, tests, and generated artifacts are authoritative when they
conflict with historical review packets.

## Quick Reading Map

| If you need | Read first |
|---|---|
| Project purpose and boundaries | [Project Overview](./project-overview.md) |
| Runtime control-loop behavior | [Runtime Lifecycle](./runtime-lifecycle.md) |
| How the 8 math pillars map to SRE | [Pillar Mapping](./pillar-mapping.md) |
| What current evidence proves and does not prove | [Evidence Ledger](./evidence-ledger.md) |
| What the next Codex / Claude pass should pursue | [Review Backlog](./review-backlog.md) |

## Current Recommended Entries

| Document | Purpose |
|---|---|
| [`docs/V2_Knowledge/knowledge-base.html`](../docs/V2_Knowledge/knowledge-base.html) | Canonical current HTML knowledge-base entry |
| [`docs/codex-review/ENGINEERING_PACKET.md`](../docs/codex-review/ENGINEERING_PACKET.md) | Offline engineering packet and review context |
| [`claude-review/docs/v2026-05-26/README.md`](../claude-review/docs/v2026-05-26/README.md) | Opus v2.0 深度评审报告（2026-05-26）— 已验证 quality gates、复核 v1.0 resolved 项、新发现 F50–F60 |
| [`docs/control-center.html`](../docs/control-center.html) | Control-center frontend consuming real Python control-stack JSON payloads |
| [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) | Layering, dependency direction, and runtime chain |
| [`docs/API_CONTRACTS.md`](../docs/API_CONTRACTS.md) | Adapter input/output/state contracts |
| [`docs/EVENT_SCHEMA.md`](../docs/EVENT_SCHEMA.md) | Runtime event schema and counterexamples |
| [`docs/RUNTIME_STATES.md`](../docs/RUNTIME_STATES.md) | Stack/module runtime states and degraded-state propagation |
| [`docs/claude-development-audit/backlog.md`](../docs/claude-development-audit/backlog.md) | Current audit ledger with resolved/watch state |

`docs/codex-review/CLAUDE_REFINED_SPEC.md` remains useful historical rationale,
but some sections describe work that is already implemented. Use the review
backlog and current tests to decide what is actually open.

## Current Baseline

- Branch context: `spacex-session`.
- Project boundary: public-material learning and engineering reproduction, not
  SpaceX official implementation.
- Current verified local gates: `python -m pytest tests -q` passes with 276
  tests; `python -m analysis.run_all` completes 12 studies.
  （历史 118 测试数为 v1.0 评审基线；当前为 v2.0 评审复核值，2026-05-26 实测。）
- Control-center entry: `python -m scripts.control_center_server`, then open
  `http://127.0.0.1:8765/control-center`.
- Current primary risk: no active P1 defect from v1.0 review is open; **Opus
  v2.0 评审（2026-05-26）独立发现 4 项 P1 候选**（F50 autoscaler MPC 单位错配、
  F51 stability_monitor 反向差分滞后、F53 `stability_violation` 仅装饰、
  F54 NaN proposal 静默放过），详见 `claude-review/docs/v2026-05-26/03-new-findings.md`，
  尚未登记到 `docs/codex-review/OPEN_RISKS.md`。Section 10 injection coverage、
  Section 5 multi-source EKF evidence、StabilityGuard SRE energy examples 与
  Catch/SRE wrapper boundary 已收紧。

## Maintenance Rules

1. The wiki records stable cross-session knowledge; it does not replace source
   code or tests.
2. If wiki text conflicts with current code or tests, trust the current code and
   tests, then update the wiki.
3. Do not turn synthetic before/after studies into production guarantees.
4. Do not claim SpaceX internal implementation details.
5. Mark old review packets as historical when their findings are resolved, so
   future agents do not re-open closed work.
