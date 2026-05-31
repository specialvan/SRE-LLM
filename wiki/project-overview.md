# Project Overview

## 一句话定位

本仓库用公开材料中可抽象出的 8 个数学支柱，构造一套可运行的 Starship 回收控制原型，再把这些控制原语迁移成 SRE 控制栈。

## 明确边界

- 不是 SpaceX 官方实现。
- `starship/` 是数学/物理层；`sre_control/` 是 SRE 迁移层。
- `analysis/` 是证据生成，不是生产 benchmark。
- before/after 只证明当前合成场景内的机制收益。
- 当前控制栈是研究型编排器，不是生产可用控制面。

## 目录责任

| 层 | 目录 | 职责 |
|---|---|---|
| 源材料层 | `DOC/spacex/` | 只读公开材料与原始叙述 |
| 数学实现层 | `starship/` | 凸化、SCP、SO(3)、EKF、MPC、分配器等控制原语 |
| 证据层 | `analysis/` | before/after studies、图像、SUMMARY |
| SRE 迁移层 | `sre_control/` | pool/canary/fusion/autoscaler/guardrail/allocation/stability adapters |
| 编排层 | `sre_control/stack.py` | `SREControlStack.step()` 端到端 tick |
| 场景层 | `examples/` | demo 脚本 |
| 文档层 | `docs/`, `wiki/` | 架构、契约、评审包和稳定知识库 |
| 质量层 | `tests/` | 单元、契约、schema、import graph 回归 |

## 控制栈主线

```text
OBSERVE -> STABILITY -> PLAN -> GUARD -> ALLOCATE -> EXECUTE
```

对应概念：

1. `SignalFusion` 融合观测。
2. `StabilityGuard` 监控 Lyapunov 候选函数。
3. `PredictiveAutoscaler` 与 `CanaryScheduler` 生成计划。
4. `SLOGuardrail` 将不安全动作投影回可行集。
5. `WeightedLoadBalancer` 做有界最小二乘分配。
6. `SREControlStack.step()` 汇总 runtime states、events 和 stage trace。

## Current Execution Authority

For the Opus handoff, use [`wiki/review-backlog.md`](./review-backlog.md),
[`docs/codex-review/OPEN_RISKS.md`](../docs/codex-review/OPEN_RISKS.md), and
[`docs/codex-review/QUALITY_GATES.md`](../docs/codex-review/QUALITY_GATES.md)
as the current completed/open-status, risk, and command-gate authorities. Start
from [`docs/opus-review/HANDOFF.md`](../docs/opus-review/HANDOFF.md), including
its `Git Review Scope Snapshot`, and refresh
`git status --short --branch --untracked-files=all` plus
`git ls-files --others --exclude-standard` so dirty/untracked files stay in the
review surface.
[`docs/codex-review/CLAUDE_REFINED_SPEC.md`](../docs/codex-review/CLAUDE_REFINED_SPEC.md)
is historical PR-A through PR-D execution rationale, not the current
implementation authority. Do not describe the branch as an official SpaceX
implementation or production-ready control stack.

## Maintenance Notes

Keep this overview aligned with `wiki/review-backlog.md`,
`docs/codex-review/OPEN_RISKS.md`, and `docs/codex-review/QUALITY_GATES.md`
when the current review handoff changes.
