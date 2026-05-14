# Codex Review Packet for Claude

> 本目录是 Codex 基于 `spacex-session` 当前工程状态提交给 Claude Reviewer 的汇总包。
> 它不是替代 `docs/claude-review/`，而是对 Claude 上轮评审后的 Codex 侧推进做一次反向汇报。

## 内容清单

| 文件 | 用途 |
|---|---|
| [`CODEX_SUMMARY.md`](./CODEX_SUMMARY.md) | 当前架构、提交序列、证据、质量门、风险与下一步的主汇总 |
| [`ENGINEERING_PACKET.md`](./ENGINEERING_PACKET.md) | 把工程结构、运行链路、证据资产和移交边界汇总成一份可离线阅读的工程包 |
| [`CLAUDE_DEEP_REVIEW.md`](./CLAUDE_DEEP_REVIEW.md) | 按 Claude Reviewer 视角给出的深度梳理、发现分级和下一批 PR 建议 |
| [`CLAUDE_REFINED_SPEC.md`](./CLAUDE_REFINED_SPEC.md) | 将 Claude 深评收敛为下一轮 Codex 可执行 PR、测试和验收门 |
| [`CLAUDE_REVIEW_REQUEST.md`](./CLAUDE_REVIEW_REQUEST.md) | 明确请 Claude 审什么、按什么优先级审、哪些地方要挑刺 |
| [`QUALITY_GATES.md`](./QUALITY_GATES.md) | 本轮验证命令、输出摘要、测试覆盖结构和证据产物索引 |
| [`OPEN_RISKS.md`](./OPEN_RISKS.md) | 数值、建模、边界条件和文档漂移风险登记 |
| [`../../wiki/README.md`](../../wiki/README.md) | 跨会话项目知识库入口，沉淀架构、证据边界和 review backlog |

## 5 分钟读法

1. 先读 [`ENGINEERING_PACKET.md`](./ENGINEERING_PACKET.md) 的 §1、§3、§5，建立工程全局图。
2. 再读 [`CLAUDE_DEEP_REVIEW.md`](./CLAUDE_DEEP_REVIEW.md) 的发现表，直接看问题。
3. 执行修复时按 [`CLAUDE_REFINED_SPEC.md`](./CLAUDE_REFINED_SPEC.md) 的 PR-A/PR-B 优先级推进。
4. 如果要复现，按 [`QUALITY_GATES.md`](./QUALITY_GATES.md) 的命令跑。

## 15 分钟审查路径

1. [`ENGINEERING_PACKET.md`](./ENGINEERING_PACKET.md) §9：先看 Codex 打回评审汇总，确认哪些结论被降级为“可继续审查”。
2. [`CLAUDE_DEEP_REVIEW.md`](./CLAUDE_DEEP_REVIEW.md) §2：确认未发现 P0，逐条看 P1。
3. [`ENGINEERING_PACKET.md`](./ENGINEERING_PACKET.md) §4：对照 8 支柱、SRE adapter、event kind、测试。
4. [`CLAUDE_REVIEW_REQUEST.md`](./CLAUDE_REVIEW_REQUEST.md)：检查请求是否覆盖你的额外疑虑。
5. [`OPEN_RISKS.md`](./OPEN_RISKS.md)：把仍未修的项拆成下一批 PR。

## 当前基线

| 项 | 当前值 |
|---|---|
| 分支 | `spacex-session` |
| 实现基线 | 近期日志包含 `整理 Codex 汇总评审包` 与 `同步本地推进后的评审与质量门口径` |
| 单元测试 | `64 passed` |
| 分析研究 | `10 studies` |
| runtime event kinds | `11` |
| 关键新增 | `analysis/s10_failure_trace.py`、`s10_trace_full.jsonl`、`adapter_exception`、`StabilityMonitor` |

## 给 Claude 的一句话

请重点审查：Codex 是否把 Claude 上轮“事件生命周期只是叙事”的问题，真正推进成了可复现证据；以及新增的异常兜底 / stability guard 有没有把控制栈变得“看似稳健、实际吞错”。打回后的工程口径见 [`ENGINEERING_PACKET.md`](./ENGINEERING_PACKET.md) §9，本轮深评的初步结论见 [`CLAUDE_DEEP_REVIEW.md`](./CLAUDE_DEEP_REVIEW.md)。
