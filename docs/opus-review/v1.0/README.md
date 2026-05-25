# Opus 评审工程包 · v1.0

本目录是 Claude Opus 4.7 对当前 codex 开发进度（`spacex-session` 分支）的深度评审落地包。
按版本切片归档，便于后续多轮迭代复盘。

## 评审上下文

| 项 | 值 |
|---|---|
| 评审时间 | 2026-05-25 |
| 分支 | `spacex-session` |
| 主分支 | `attention-residuals-session` |
| 评审基线 commit | `8d8e064` (audit: enforce release hygiene) |
| 评审模型 | Claude Opus 4.7 (1M context) |
| 评审目标 | 深度复核 codex 在 `docs/codex-review/` 工程包内交付的工程态 |

## 文件清单

| 文件 | 用途 |
|---|---|
| [`DEEP_REVIEW_REPORT.md`](./DEEP_REVIEW_REPORT.md) | 主报告：架构、模块、证据边界、风险与建议 |
| [`QUALITY_GATE_VERIFICATION.md`](./QUALITY_GATE_VERIFICATION.md) | 质量门复跑结果（pytest / analysis / evidence 报告） |
| [`MODULE_INSPECTION.md`](./MODULE_INSPECTION.md) | 重点模块逐文件笔记（`sre_control/`, `starship/`, `analysis/`） |
| [`FOLLOWUP_BACKLOG.md`](./FOLLOWUP_BACKLOG.md) | 建议下一轮 codex 处理的优化项与潜在风险 |

## 阅读顺序

1. 先读 `DEEP_REVIEW_REPORT.md` 获得整体判断。
2. 想看具体跑通证据，看 `QUALITY_GATE_VERIFICATION.md`。
3. 关注单模块实现细节看 `MODULE_INSPECTION.md`。
4. 准备下一轮提单看 `FOLLOWUP_BACKLOG.md`。

## 与 codex 评审包的关系

- `docs/codex-review/` 是 codex 自评 + 历史评审包（保留为历史依据）。
- `docs/opus-review/v1.0/` 是本轮独立第三方评审。后续按版本号叠加（v1.1、v2.0 ……），不覆盖旧版。
- 与全局规则一致，结论性结论以 `wiki/review-backlog.md` 与 `OPEN_RISKS.md` 为准；本包仅提供观察 + 建议。
