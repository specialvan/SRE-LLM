# Claude Review · Rounds 7–9 Handback

> ✅ **STATUS: CLOSED (2026-05-12)** — All 7 follow-up items (AI-1 through AI-7) are
> implemented, tested, and documented. State.json has been refreshed to reflect this.
> See [`04-midflight-review.md`](./04-midflight-review.md) for the close-out report.
>
> If you are opening Round 11, archive this folder into `round-10-archive/` and start a
> fresh `claude-review/` with a new README. Do not re-open items here.

> Review package originally generated for codex to pick up after Rounds 7–9.
> Author: Claude (reviewing). Review date: 2026-05-12.
> Subject of review: commits `ba8fad8` → `3dbfd50` on `attention-residuals-session`.

---

## 1. What's in this folder

| File | Purpose | Audience |
| --- | --- | --- |
| [`00-review-report.md`](./00-review-report.md) | Full verdict + per-commit assessment + design concerns | Tech lead / codex |
| [`01-detailed-architecture.md`](./01-detailed-architecture.md) | 7-layer architecture, data flow diagrams, API contracts, invariant enforcement sequences | Codex (for deep changes) |
| [`02-action-items.md`](./02-action-items.md) | Numbered action list with acceptance criteria. **All 7 closed as of 2026-05-12.** | Codex (immediate work) |
| [`03-handoff-summary.md`](./03-handoff-summary.md) | One-page executive summary for offline handoff | PM / tech lead |
| [`04-midflight-review.md`](./04-midflight-review.md) | Delta assessment after codex implemented 6/7 AIs within hours (added 2026-05-12). **Read before pushing the in-progress commits**. | Codex (before final push) |
| [`05-round-11-opening.md`](./05-round-11-opening.md) | Reviewer checklist template for when Round 10 commits land. Archive protocol + review deliverable shape + backlog seeds. | Next reviewer (Round 11) |

---

## 2. Quick verdict

**Approve · all follow-ups closed (2026-05-12).** Original verdict: "Approve with notes"; all 7 AIs shipped in the same day. Merge blockers: none. For the next review cycle, start with [`05-round-11-opening.md`](./05-round-11-opening.md).

## 3. How codex should consume this

**你从哪里来，就从哪里开始读**：

| 你是… | 先读 | 再读 | 然后做 |
| --- | --- | --- | --- |
| 刚接手，没看过 CODEX-HANDOFF | [`03-handoff-summary.md`](./03-handoff-summary.md) | [`00-review-report.md`](./00-review-report.md) | 按 [`02-action-items.md`](./02-action-items.md) 开工 |
| 已读过 `docs/CODEX-HANDOFF.md` | [`00-review-report.md`](./00-review-report.md) | [`02-action-items.md`](./02-action-items.md) AI-1 | 动手 |
| 只想改代码、不想读评审 | [`02-action-items.md`](./02-action-items.md) 挑一条 | [`01-detailed-architecture.md`](./01-detailed-architecture.md) 对应章节 | 动手 |
| **Codex 已经在本地做过 AI-1~7** | [`04-midflight-review.md`](./04-midflight-review.md) | 按 §7 Codex-side TODO 清单 | 修 AI-4 的 `max_dead_letters` + 补一行 RLock 注释 + 按建议的 commit 切分推送 |
| **准备开 Round 11 新评审** | [`05-round-11-opening.md`](./05-round-11-opening.md) | 执行 pre-flight | 照模板写 06/07 |
| 想 review codex 的后续 PR | 当前目录所有 6 份 | diff against `3dbfd50` | 新一轮 review（参考 `05-round-11-opening.md`） |

### 详细执行流（适合第一次接手的新 agent）

1. **Read [`03-handoff-summary.md`](./03-handoff-summary.md)** first — 2 分钟了解整体健康度。
2. **Read [`00-review-report.md`](./00-review-report.md)** — 10 分钟理解每个 commit 的评审和 7 条设计关切。
3. **Execute [`02-action-items.md`](./02-action-items.md)** one P1 at a time:
   - Each item has acceptance criteria and a test specification.
   - Complete P1 → run full pytest → commit → move on.
   - **Do not batch** P1 items in one commit — atomic commits make review easier.
4. **Keep [`01-detailed-architecture.md`](./01-detailed-architecture.md) open** as reference while changing code — especially the invariant-enforcement sequences and the API contract tables.

## 4. Guardrails while executing

These were the invariants that made Round 6–9 safe. Codex should preserve them.

> **这 7 条 guardrails 是 13 条 invariants 的 PR-review 快速子集**。
> 完整 13 条权威定义在 [`../V2_Knowledge/state.json`](../V2_Knowledge/state.json) 的 `hard_invariants` 字段。
> 这里列的 7 条是"PR 合入前一眼检查"的常用集（对应 `state.json.pr_review_guardrails`）。

1. **Hard bounds are never breached by automatic code paths** (maps to `I-07`)
   (`LearnedSafetyEnvelope.fit`, `ContractionAwareEnvelope.apply`).
2. **`relax()` is the only API that widens the envelope.** (maps to `I-06`)
3. **Σ a = 1 is a hard invariant, never a soft loss term.** (maps to `I-01` / `I-03`)
4. **Audit trail is append-only; records never mutate after write.** (maps to `I-09`)
5. **External transports (HTTP, file I/O) are always injectable** for tests. (convention)
6. **Public API signatures are stable** — prefer adding optional kwargs over breaking changes. (convention)
7. **Every new feature has: module + test + demo + doc entry.** (convention)

## 5. Escape hatch

If codex finds an action item that requires breaking any of the 7 guardrails above, **stop and write an ADR** in [`../adr/`](../adr/) explaining the tradeoff before implementing. Use [`../adr/_template.md`](../adr/_template.md) as a starting point. Do not unilaterally weaken safety invariants.

**Reference**: [`../adr/0001-contraction-wrapper-uses-rlock.md`](../adr/0001-contraction-wrapper-uses-rlock.md) is an example of an ADR written ex-post to document a design choice found during review (Lock vs RLock on `ContractionAwareEnvelope`).
