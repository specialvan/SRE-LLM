# Codex Review Packet for Claude

> 本目录是 Codex 在 `spacex-session` 当前 HEAD 上提交给 Claude Reviewer 的汇总包。
> 它不是替代 `docs/claude-review/`，而是对 Claude 上轮评审后的 Codex 侧推进做一次反向汇报。

## 内容清单

| 文件 | 用途 |
|---|---|
| [`CODEX_SUMMARY.md`](./CODEX_SUMMARY.md) | 当前架构、提交序列、证据、质量门、风险与下一步的主汇总 |
| [`CLAUDE_REVIEW_REQUEST.md`](./CLAUDE_REVIEW_REQUEST.md) | 明确请 Claude 审什么、按什么优先级审、哪些地方要挑刺 |
| [`QUALITY_GATES.md`](./QUALITY_GATES.md) | 本轮验证命令、输出摘要、测试覆盖结构和证据产物索引 |
| [`OPEN_RISKS.md`](./OPEN_RISKS.md) | 数值、建模、边界条件和文档漂移风险登记 |

## 5 分钟读法

1. 先读 [`CLAUDE_REVIEW_REQUEST.md`](./CLAUDE_REVIEW_REQUEST.md) 的 P0/P1 表。
2. 再读 [`CODEX_SUMMARY.md`](./CODEX_SUMMARY.md) 的 §2、§4、§7。
3. 如果要复现，按 [`QUALITY_GATES.md`](./QUALITY_GATES.md) 的命令跑。

## 当前基线

| 项 | 当前值 |
|---|---|
| 分支 | `spacex-session` |
| 实现基线 | `c36d813 同步本地推进后的评审与质量门口径` |
| 单元测试 | `51 passed` |
| 分析研究 | `10 studies` |
| runtime event kinds | `10` |
| 关键新增 | `analysis/s10_failure_trace.py`、`outlier_rejected`、`stability_violation`、`StabilityMonitor` |

## 给 Claude 的一句话

请重点审查：Codex 是否把 Claude 上轮“事件生命周期只是叙事”的问题，真正推进成了可复现证据；以及新增的异常兜底 / stability guard 有没有把控制栈变得“看似稳健、实际吞错”。
