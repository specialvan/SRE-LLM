# Codex Review Packet

This directory is a review handoff packet. It preserves historical review
context, but current source, tests, `wiki/review-backlog.md`, `OPEN_RISKS.md`,
and `QUALITY_GATES.md` control live execution order.

## Contents

| File | Purpose |
|---|---|
| [`CODEX_SUMMARY.md`](./CODEX_SUMMARY.md) | Historical architecture/evidence summary for Claude review |
| [`ENGINEERING_PACKET.md`](./ENGINEERING_PACKET.md) | Offline engineering packet and review context |
| [`CLAUDE_DEEP_REVIEW.md`](./CLAUDE_DEEP_REVIEW.md) | Historical deep review packet; now marked with current-status caveats |
| [`CLAUDE_REFINED_SPEC.md`](./CLAUDE_REFINED_SPEC.md) | Historical PR-A through PR-D execution spec and acceptance rationale |
| [`CLAUDE_REVIEW_REQUEST.md`](./CLAUDE_REVIEW_REQUEST.md) | Original review request and checklist |
| [`QUALITY_GATES.md`](./QUALITY_GATES.md) | Current reproducible command gates and evidence boundaries |
| [`OPEN_RISKS.md`](./OPEN_RISKS.md) | Current useful risk register and suggested next research slices |
| [`../../wiki/README.md`](../../wiki/README.md) | Cross-session project wiki entry |
| [`../../claude-review/docs/v2026-05-28/README.md`](../../claude-review/docs/v2026-05-28/README.md) | **Opus v2.1 continuation review (2026-05-28)** - F61-F81 and browser evidence / quality-gate follow-up |
| [`../../claude-review/docs/v2026-05-26/README.md`](../../claude-review/docs/v2026-05-26/README.md) | **Opus v2.0 深度评审报告（2026-05-26）** — quality gates 复跑、v1.0 resolved 项 spot-check、新发现 F50–F60、合并门禁判定 |

## Reading Order

1. Read [`../../wiki/review-backlog.md`](../../wiki/review-backlog.md) for the
   current completed/open state.
2. Read [`OPEN_RISKS.md`](./OPEN_RISKS.md) to choose the next research landing
   slice.
3. Run commands from [`QUALITY_GATES.md`](./QUALITY_GATES.md) before claiming a
   pass is complete.
4. Use the older review packets only as historical rationale and acceptance
   history.

## Current Baseline

| Item | Current value |
|---|---|
| Branch context | `spacex-session` |
| Unit/integration tests | `487 passed` |
| Analysis studies | `12 studies` |
| Runtime event kinds | `11` |
| Canonical HTML entry | `docs/V2_Knowledge/knowledge-base.html` |

## Current One-Line Handoff

The runnable control-stack research package is green locally. Section 10
bound-window coverage, Section 5 multi-source EKF evidence, StabilityGuard SRE
energy examples, the Catch/SRE wrapper boundary, and Section 12 replay evidence
have been tightened. Section 10/11/12 event evidence is also indexed by
`analysis/artifacts/event_evidence_manifest.json` and documented in
`docs/EVENT_EVIDENCE_MANIFEST.md`; `python -m analysis.evidence_report`
validates linked artifact keys and extensions, JSON/JSONL/PNG parseability,
runtime event schema, and key counts.

**Opus v2.0 评审（2026-05-26）状态**：quality gates 实测全过；v1.0 已宣称
resolved 项 18/19 HOLDS（F02 PARTIAL，边界缝隙）；独立审计新发现 11 项
（F50–F60），其中 4 项 P1 候选。当前工作区已修复 F50–F60 并增加回归测试；
G1 evidence manifest / PNG byte-identity process trap 也已通过
`quality_gate_counts` 的 manifest→report 自愈合顺序修复。详细原始评审包见
`claude-review/docs/v2026-05-26/`。
