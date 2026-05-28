# Opus 评审入口

本目录是给 Opus 重新介入复审的入口。先读 `HANDOFF.md`，再按需进入工程包和历史评审记录；当前事实以源码、测试输出和已提交证据产物为准。

## 首读文件

| 文件 | 用途 | 读取方式 |
| --- | --- | --- |
| [`HANDOFF.md`](./HANDOFF.md) | 当前交接入口，按内容域拆分近期提交、质量门和复审重点 | Opus 第一份首读 |
| [`../codex-review/OPEN_RISKS.md`](../codex-review/OPEN_RISKS.md) | 当前开放风险台账 | 判断是否仍有 blocker |
| [`../../wiki/review-backlog.md`](../../wiki/review-backlog.md) | 跨会话完成状态和证据索引 | 对照长期 ledger |
| [`OPUS_REVIEW_PACKET.md`](./OPUS_REVIEW_PACKET.md) | 复审命令、证据资产、历史 finding 对照 | 用于命令复跑和抽查 |

## 历史输入

| 文件 | 语义 |
| --- | --- |
| [`../../claude-review/docs/v2026-05-28/README.md`](../../claude-review/docs/v2026-05-28/README.md) | 最近一轮外部评审上下文 |
| [`../../claude-review/docs/v2026-05-26/README.md`](../../claude-review/docs/v2026-05-26/README.md) | Opus v2.0 历史评审上下文 |
| [`v1.0/`](./v1.0/) | 更早的 Opus 包，保留作追溯材料 |

## 权威顺序

1. 当前源码、测试和已提交证据产物。
2. `docs/codex-review/OPEN_RISKS.md`。
3. `wiki/review-backlog.md`。
4. `docs/opus-review/HANDOFF.md`。
5. `claude-review/docs/v2026-05-28/README.md`。
6. `claude-review/docs/v2026-05-26/README.md`。
7. `docs/opus-review/OPUS_REVIEW_PACKET.md`。
8. `docs/opus-review/v1.0/` 历史文件。

## 边界

- 旧评审文件只提供历史上下文，不是当前 completed/open 状态台账。
- 本仓库是公开材料研究复现，不代表 SpaceX 内部实现。
- 分析产物是 synthetic scenario evidence；新摘要和评审结论必须继续保留这个边界。
