# Architecture Deep Dives

> 🧭 顶层概览在 [`../architecture.md`](../architecture.md)。本目录存放
> 比 top-level 架构更细的专题文档，每一份聚焦一个工程维度。

SRE 自迭代决策系统的核心矛盾是：

> **决策要算法化、证据要可审计、状态要可复现、失败要可恢复。**

这四条任何一条单独做都不难，难的是四条同时成立并在同一条代码路径里被尊重。
本目录的文档就是为了把这四条拆成可验证的契约。

## 文档地图

| 文档 | 关注的问题 |
|---|---|
| [01-system-context.md](01-system-context.md) | 谁在调用我们？我们在调用谁？数据从哪进、哪出？ |
| [02-decision-flow.md](02-decision-flow.md) | `decide(ctx)` 一次调用的完整生命周期、每个 stage 的输入输出 |
| [03-trace-schema.md](03-trace-schema.md) | Trace 的 JSON schema、每个字段的来源和语义、向后兼容契约 |
| [04-state-and-failure-domains.md](04-state-and-failure-domains.md) | 什么状态持久化、什么只在内存、各类故障的 blast radius |
| [05-artifact-lifecycle.md](05-artifact-lifecycle.md) | Retention / Cox artifact 的训练 → 打包 → 部署 → 运行 → 回滚全链路 |
| [06-concurrency-and-leases.md](06-concurrency-and-leases.md) | 线程锁、进程锁、跨节点锁各自解决什么问题 |
| [07-observability-contract.md](07-observability-contract.md) | 日志事件目录、指标目录、trace 字段和告警的映射关系 |
| [08-rollout-and-governance.md](08-rollout-and-governance.md) | Shadow → Advisory → Enforce 的推进规则、ADR 归档规则 |

## 阅读顺序建议

- **第一次接手**：01 → 02 → 04 → 07
- **评审 PR 时**：02 + 03（看行为是否符合契约）+ 05（如果动 artifact）
- **做容量 / 多副本改造**：04 + 06
- **要改决策策略（加新规则）**：02 + 08

## 与 ADR / runbook / claude-review 的关系

```
架构文档（本目录）  ——  描述 "系统当前是什么形状"
ADR（../adr/）      ——  描述 "为什么当时这么选"
Runbook（../runbooks/） —— 描述 "遇到 X 时怎么操作"
Claude Review       ——  描述 "某次交付的评审结论和改进项"
```

四份文档相互引用但职责互不覆盖。架构文档变更不一定立 ADR（小修可以），
但 ADR 的结论必须反映回架构文档；runbook 只能引用架构文档里定义的术语，
禁止发明新概念。
