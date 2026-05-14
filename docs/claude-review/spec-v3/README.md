# Spec v3 · 2026-07 轮可执行版

本目录是 2026-07 轮的展开版可执行层，来源于 Codex review 包中的
[`CLAUDE_REFINED_SPEC.md`](../../codex-review/CLAUDE_REFINED_SPEC.md)，并补齐
[`2026-06-codex-package-review.md`](../2026-06-codex-package-review.md) 的
P3 follow-up 与
[`../2026-06-spec-completion.md`](../2026-06-spec-completion.md) 的下一轮建议。

> Source of truth for the next Codex pass is
> [`docs/codex-review/CLAUDE_REFINED_SPEC.md`](../../codex-review/CLAUDE_REFINED_SPEC.md).
> 本目录用于把该 spec 展开成 EARS requirements、T-XXX task list 与 verification
> gate；如两边冲突，以 `CLAUDE_REFINED_SPEC.md` 为准。

## 本轮定位

2026-06 C+A2 已关闭 F-001 ~ F-010。v3 不再继续追旧 finding，而是把剩余
生产 readiness 风险拆成小而可验收的能力增量。

## 本轮覆盖范围（D+A2）

- **A-001** — Runtime hydration 与 replay validation 共用 retention rating-scaling compatibility rule。
- **B-001** — Modern fitted replay fixtures 必须携带 `rating_scaling_version` 并断言 trace status 为 `match`。
- **C-001** — Replay corpus 增加 artifact failure / guardrail short-circuit 事故叙事。
- **D-001** — Lease readiness boundary 文档化：`/healthz` process-only，`/readyz` 包含 lease health。
- **E-001** — 历史 tracker 状态收敛：旧 action / coverage 文档必须明确是归档，不再像当前 blocker。
- **E-002** — Latency gate：CI benchmark 必须能在 p99 超预算时失败。
- **E-003** — Replay naming hardening：fixture 文件名 suffix 必须等于 JSON `expected.kind`。
- **E-004** — Artifact import compatibility：`gan_matchmaking.sre.artifacts` public surface 有快照测试。
- **E-005** — Lease readiness HTTP boundary：真实 HTTP `/readyz` 失效路径有集成测试。

## 文件

| 文件 | 作用 |
|---|---|
| [`requirements.md`](requirements.md) | EARS-A2 acceptance criteria, R-701 ~ R-842 |
| [`tasks.md`](tasks.md) | T-701 ~ T-843 编码 / 文档任务清单 |
| [`verification.md`](verification.md) | 每个增量的验证命令 + 全局 gate |

## PR 编排

```
PR-A        — A-001 shared artifact compatibility helper (代码 + 测试)
PR-B        — B-001 modern fitted replay metadata        (fixture + 测试)
PR-C        — C-001 artifact/guardrail replay narratives (fixture + 测试)
PR-D        — D-001 lease readiness boundary docs        (文档)
PR-doc-03   — E-001 supersede historical trackers        (只改文档)
PR-ci-01    — E-002 enforce latency budget in CI         (CI + bench 契约)
PR-test-01  — E-003 replay expected-kind suffix check    (测试补强)
PR-test-02  — E-004 artifacts public import snapshot     (测试补强)
PR-test-03  — E-005 HTTP lease readiness integration     (测试补强)
```

推荐顺序：**PR-A → PR-B → PR-C/PR-D → doc/ci/test hardening 并行**。

理由：
- PR-A 对齐 runtime 与 replay 的 artifact compatibility，是 `CLAUDE_REFINED_SPEC.md` 的最高优先级。
- PR-B 依赖 PR-A 的 compatibility status 语义。
- PR-C/PR-D 扩 replay 与文档边界，互相独立。
- doc/ci/test hardening 是评审发现的额外 P3 补强，可与 PR-C/PR-D 并行。

## 完成标准（DoD）

1. Runtime hydration 与 replay validation 使用同一个 rating-scaling compatibility helper。
2. Replay validation 拒绝 runtime 会 downgrade 的 retention scaling mismatch。
3. Modern fitted replay fixture 至少一个断言 `trace.artifacts.rating_scaling_status == "match"`。
4. Legacy `unknown` retention scaling 行为必须显式命名 / 显式允许。
5. 至少新增两个 artifact failure / guardrail short-circuit replay narratives。
6. Lease readiness boundary 文档明确 `/healthz` 与 `/readyz` 分工。
7. 历史 tracker 顶部都有 superseded banner，并指向 2026-06 completion、Codex package review 与 spec-v3。
8. CI latency benchmark 在 p99 超过预算时返回非零。
9. Replay fixture naming 测试断言 suffix 等于 JSON `expected.kind`。
10. Artifacts public import surface 由显式 expected symbol set 保护。
11. HTTP-level `/readyz` lease-unhealthy 路径有测试覆盖，`/healthz` 仍保持 200。
12. `python -m pytest -q` 全绿。
13. `python -m bench.latency --quick --p99-ms 50` 返回 0。