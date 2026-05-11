# Claude 评审资料

本目录存放 Claude 对 codex 分支的评审输出，按时间线和关注点归档。codex
在拿回仓库后，应该按以下顺序阅读并消化：

## 当前轮（2026-06 C+A2，进行中）

1. [`2026-06-session-review.md`](2026-06-session-review.md) — 2026-06 轮入口
2. [`spec-v2/README.md`](spec-v2/README.md) — 本轮可执行 spec，覆盖
   F-005 / F-006 / F-007 / F-008 / F-009 / F-010
3. [`spec-v2/tasks.md`](spec-v2/tasks.md) — 按 PR 排序的 T-XXX 编码任务；
   [`spec-v2/verification.md`](spec-v2/verification.md) — 验证命令 + 契约快照
4. [`patches/F-005-rating-scaling-contract.md`](patches/F-005-rating-scaling-contract.md)、
   [`patches/F-007-release-context-from-dict.md`](patches/F-007-release-context-from-dict.md)、
   [`patches/F-008-sqlite-migration.md`](patches/F-008-sqlite-migration.md) — 核心补丁草案

## 上一轮（2026-05 B+A2，已完成 ✅）

1. [`2026-05-session-review.md`](2026-05-session-review.md) — 首次
   `gan-session` 分支的整体评审
2. [`2026-05-spec-completion.md`](2026-05-spec-completion.md) — 收尾报告
   （F-001 / F-002 / F-003 / F-004 全部 resolved）
3. [`spec/README.md`](spec/README.md) — 上轮 spec（已完成，保留作为 codex 使用约定范例）
4. [`patches/F-001-lease-refresh.md`](patches/F-001-lease-refresh.md)、
   [`patches/F-002-shadow-metric.md`](patches/F-002-shadow-metric.md)、
   [`patches/F-003-trace-allowlist.md`](patches/F-003-trace-allowlist.md) — 上轮补丁

## 跨轮参考

- [`findings.md`](findings.md) — 带严重度、影响面、修复建议的问题清单。
  按 P1 / P2 / P3 / P4 分级，可直接当作 PR tracker。
- [`action-items.md`](action-items.md) — 建议开的 follow-up PR 列表
- [`test-coverage-gaps.md`](test-coverage-gaps.md) — 现有测试未覆盖的风险场景

## 使用约定

- 一次评审写一个 `YYYY-MM-session-review.md`，永远不回改历史评审。
- 一轮闭环后写一个 `YYYY-MM-spec-completion.md` 归档。
- 新的 findings 可以追加到现有 `findings.md`，但已存在的条目只能
  标 `status: resolved` / `status: deferred`，不得删除。
- codex 处理完一条 finding 后，在对应 PR 描述里贴上 finding id，
  便于审计"评审提出 → 修复落地"的闭环。
- V2 快照 `docs/V2_Knowledge/` 冻结于 2026-05 结束；V3
  `docs/V3_Knowledge/` 冻结于 2026-06 结束；下一轮开 V4。

## 相关文档

- 架构深度文档：[`docs/architecture/`](../architecture/)
- 开发路线：[`docs/implementation-roadmap.md`](../implementation-roadmap.md)
- 设计决策：[`docs/adr/`](../adr/)
