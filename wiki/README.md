# SpaceX → SRE Project Wiki

> 本 wiki 是当前工程知识库入口。它沉淀稳定上下文、审查边界、运行链路和后续 PR 规格；具体代码和测试仍以仓库当前状态为准。

## 快速读法

| 你想知道 | 先读 |
|---|---|
| 工程做什么、边界是什么 | [Project Overview](./project-overview.md) |
| 控制链路如何运行 | [Runtime Lifecycle](./runtime-lifecycle.md) |
| 8 个数学支柱如何迁移到 SRE | [Pillar Mapping](./pillar-mapping.md) |
| 当前证据能证明什么、不能证明什么 | [Evidence Ledger](./evidence-ledger.md) |
| 下一轮 Codex / Claude 应推进什么 | [Review Backlog](./review-backlog.md) |

## 当前推荐入口

| 文档 | 用途 |
|---|---|
| [`docs/codex-review/CLAUDE_REFINED_SPEC.md`](../docs/codex-review/CLAUDE_REFINED_SPEC.md) | 下一轮实现的执行规格，优先级最高 |
| [`docs/codex-review/ENGINEERING_PACKET.md`](../docs/codex-review/ENGINEERING_PACKET.md) | 可离线阅读的工程包 |
| [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) | 分层、依赖方向、运行链路 |
| [`docs/API_CONTRACTS.md`](../docs/API_CONTRACTS.md) | adapter 输入/输出/状态契约 |
| [`docs/EVENT_SCHEMA.md`](../docs/EVENT_SCHEMA.md) | runtime event schema 和 counter-example |
| [`docs/RUNTIME_STATES.md`](../docs/RUNTIME_STATES.md) | stack/module runtime 状态与降级传播 |

## 当前基线

- 分支：`spacex-session`
- 工程定位：公开材料学习/工程复现，不代表 SpaceX 官方实现。
- 质量门口径：最近 review packet 记录为 `python -m pytest tests -q` 通过 51 个测试，`python -m analysis.run_all` 完成 10 个 studies。
- 当前主要风险：质量门绿色，但 PR-A 至 PR-D 的语义风险仍是 P1。

## 维护规则

1. wiki 记录跨会话稳定知识，不替代源码。
2. 若 wiki 与当前代码冲突，以当前代码和测试为准，并更新 wiki。
3. 不把合成 before/after 证据写成生产保证。
4. 不宣称 SpaceX 内部实现细节。
