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
| [`docs/codex-review/OPEN_RISKS.md`](../docs/codex-review/OPEN_RISKS.md) | Current live risk register and next research-slice boundary |
| [`wiki/review-backlog.md`](./review-backlog.md) | Current completed/open review state and evidence index |
| [`docs/V2_Knowledge/knowledge-base.html`](../docs/V2_Knowledge/knowledge-base.html) | Canonical current HTML knowledge-base entry |
| [`docs/codex-review/ENGINEERING_PACKET.md`](../docs/codex-review/ENGINEERING_PACKET.md) | Offline engineering packet and review context |
| [`docs/control-center.html`](../docs/control-center.html) | Control-center frontend consuming real Python control-stack JSON payloads |
| [`docs/CONTROL_CENTER_HANDOFF.md`](../docs/CONTROL_CENTER_HANDOFF.md) | Locked black-gold OpenDesign control-center style and interaction handoff |
| [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) | Layering, dependency direction, and runtime chain |
| [`docs/API_CONTRACTS.md`](../docs/API_CONTRACTS.md) | Adapter input/output/state contracts |
| [`docs/EVENT_SCHEMA.md`](../docs/EVENT_SCHEMA.md) | Runtime event schema and counterexamples |
| [`docs/RUNTIME_STATES.md`](../docs/RUNTIME_STATES.md) | Stack/module runtime states and degraded-state propagation |
| [`docs/claude-development-audit/backlog.md`](../docs/claude-development-audit/backlog.md) | Current audit ledger with resolved/watch state |
| [`claude-review/docs/v2026-05-28/README.md`](../claude-review/docs/v2026-05-28/README.md) | Historical Opus v2.1 continuation review context |
| [`claude-review/docs/v2026-05-26/README.md`](../claude-review/docs/v2026-05-26/README.md) | Historical Opus v2.0 review context |

`docs/codex-review/CLAUDE_REFINED_SPEC.md` remains useful historical rationale,
but some sections describe work that is already implemented. Use the review
backlog and current tests to decide what is actually open.

## Current Baseline

- Branch context: `spacex-session`.
- Project boundary: public-material learning and engineering reproduction, not
  SpaceX official implementation.
- Current verified local gates: `python -m pytest tests -q` passes with 594
  tests; `python -m analysis.run_all` completes 12 studies. Historical review
  packets mention smaller pytest counts; treat those as packet-time snapshots.
- Control-center entry: `python -m scripts.control_center_server`, then open
  `http://127.0.0.1:8765/control-center`.
- Current primary risk: no active P1 defect from v1.0, Opus v2.0, or Opus v2.1
  review is open in the current workspace. F50-F60/G1 and F61-F81 are
  remediated with regression tests, evidence gates, or explicit current-doc
  boundary updates. The latest review packet is under
  `claude-review/docs/v2026-05-28/`, and the live risk ledger is
  `docs/codex-review/OPEN_RISKS.md`.

## Maintenance Rules

1. The wiki records stable cross-session knowledge; it does not replace source
   code or tests.
2. If wiki text conflicts with current code or tests, trust the current code and
   tests, then update the wiki.
3. Do not turn synthetic before/after studies into production guarantees.
4. Do not claim SpaceX internal implementation details.
5. Mark old review packets as historical when their findings are resolved, so
   future agents do not re-open closed work.
