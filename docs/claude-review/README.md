# Claude Review Pack

> Reviewer：Claude Opus 4.7
> Review 范围：`auto-decide-session` 分支 `f0070c0..f7eae3f`（5 commits / 14 files / +1675/-36）
> Review 日期：2026-05-12
> 目的：为下一轮 Codex 提供可执行的 review 反馈 + 更深的架构参考

> Codex 更新：AI-01 / AI-02 / AI-03b / AI-11 / AI-12 / AI-13 / AI-14 已于 2026-05-12 收口。最新状态见 [09-codex-synthesis.md](./09-codex-synthesis.md) 与 [08-benchmark-log.md](./08-benchmark-log.md) 顶部记录。

## TL;DR

**评级**：APPROVED WITH FOLLOW-UPS · 不阻塞合入
**主要结论**：工程纪律非常到位（trace 契约、benchmark 契约、测试全绿），但 benchmark 同时把系统**真实存在的可用性风险**暴露出来；最初是 emergency/fallback 违约，AI-02 后转为 best_effort 恢复态偏高。

## 本包目录

| 文件 | 用途 | 目标读者 |
| --- | --- | --- |
| [00-executive-summary.html](./00-executive-summary.html) | 带图的执行摘要 · 含 before/after 对比 | 所有 |
| [01-findings.md](./01-findings.md) | P0/P1/P2 findings · 每条带证据与修复方案 | Codex 按清单推进 |
| [02-architecture-deep.html](./02-architecture-deep.html) | 更深的架构：类型流 / 失败决策树 / 时间预算 / 场景-模块矩阵 | 架构理解 |
| [03-invariants-catalog.md](./03-invariants-catalog.md) | 全部全局与模块不变式 · 带证明草图与测试锚点 | PR 评审 guardrail |
| [04-contracts-catalog.md](./04-contracts-catalog.md) | 9 模块 + trace 的 pre/post/invariant 完整合约 | 接口变更评审 |
| [05-action-items.md](./05-action-items.md) | 带 ID 的任务清单 · 每条有验收标准 | Codex 作为 sprint log |
| [06-suggested-patches/](./06-suggested-patches/) | 可直接 cherry-pick 的补丁骨架 | Codex 按 patch 执行 |
| [07-codex-directives.md](./07-codex-directives.md) | 明确的 do / don't 清单 | 下一轮 Codex 必读 |
| [08-benchmark-log.md](./08-benchmark-log.md) | canonical benchmark 历史基线 | Reviewer / Codex |
| [09-codex-synthesis.md](./09-codex-synthesis.md) | Claude 评审深度梳理与执行路线 | 下一轮 Codex 开工 |

## 阅读顺序

- **只有 5 分钟**：[00-executive-summary.html](./00-executive-summary.html)
- **准备下一轮开工**：[05-action-items.md](./05-action-items.md) → [06-suggested-patches/](./06-suggested-patches/) → [07-codex-directives.md](./07-codex-directives.md)
- **想直接执行**：[09-codex-synthesis.md](./09-codex-synthesis.md) → [05-action-items.md](./05-action-items.md)
- **想理解架构**：[02-architecture-deep.html](./02-architecture-deep.html) → [03-invariants-catalog.md](./03-invariants-catalog.md) → [04-contracts-catalog.md](./04-contracts-catalog.md)

## 关键数字一眼看懂

| 指标 | 承诺 SLO | 实测 | 差距 |
| --- | --- | --- | --- |
| 碰撞率（结构化链路） | &lt; 10⁻⁶/mile | 0%（20 场景） | ✅ 达标 |
| `planner_emergency_rate` | &lt; 0.5% | **4.82%**（post-AI-12） | ✅ demo pass / ⚠️ prod fail |
| `planner_best_effort_rate` | &lt; 5%（生产观测项） | **63.76%** | ⚠️ 恢复态偏高 |
| `cbf_fallback_rate` | &lt; 5%（告警线） | **4.82%** | ✅ 贴线通过 |
| 单步时延 P99 | &lt; 15 ms | ~1.83 ms mean | ✅ |
| 测试覆盖 | — | 32 / 32 绿 | ✅ |
| trace 契约 | schema_version 稳定 | ✅ v1.1，JSONL 严格可解析 | ✅ |

最关键的洞察写在这里：**AI-02 已把硬刹停显著压低，但大量帧仍处于 best_effort 恢复态**。这不是 bug——这是 benchmark 契约继续把"安全 vs 可用性 vs 稳定恢复"的真实权衡量化出来。下一轮必须把 best_effort 纳入 CI / 回归分析，而不是只看 emergency 是否过线。

## 给 Codex 的一句话交接

> 不要为了让 `planner_emergency_rate` 变低而放宽 `cbf_alpha` 或 `game.base_buffer`。
> 要做的是把 `GradientPolicy` 换成能理解 barrier 的 MPC 或 barrier-aware policy。
> 硬约束是结果，不是调优对象。

详见 [07-codex-directives.md](./07-codex-directives.md)。
