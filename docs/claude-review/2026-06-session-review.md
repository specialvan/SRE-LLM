# 2026-06 Session Review · 下一轮评审入口

本文档是 2026-06 轮评审的**入口**。2026-05 轮（B+A2）已闭环，见
[`2026-05-spec-completion.md`](2026-05-spec-completion.md)。

## 本轮起点

- 分支：`gan-session`（继续沿用，不再 fork）
- 基线：`123 passed`, bench p99 = 1.03 ms
- 已 resolved：F-001 / F-002 / F-003 / F-004
- 待处理：F-005 / F-006 / F-007 / F-008（P3，工程整洁度与长期可维护性）
  + F-009 / F-010（P4，文档与命名洁癖）

## 本轮范围 · 方案 **C+A2**

- **C** = F-005 + F-007 为主攻（"artifact 稳定性合同" + "公共 API 提升"），
  F-006 / F-008 / F-009 / F-010 配套收尾
- **A2** = 继续使用 EARS-A2 简化句式
- **禁止改动**本轮范围外的现有 `trace["stages"]["*"]` 字段、
  `Decision` 对外字段、`/v1/*` HTTP API 路径

## 可执行 Spec 入口

- Spec v2：[`spec-v2/README.md`](spec-v2/README.md)
- 需求（R-305 ~ R-710）：[`spec-v2/requirements.md`](spec-v2/requirements.md)
- 设计：[`spec-v2/design.md`](spec-v2/design.md)
- 任务 checkbox：[`spec-v2/tasks.md`](spec-v2/tasks.md)
- 验证命令：[`spec-v2/verification.md`](spec-v2/verification.md)
- 补丁草案：
  [`patches/F-005-rating-scaling-contract.md`](patches/F-005-rating-scaling-contract.md)、
  [`patches/F-007-release-context-from-dict.md`](patches/F-007-release-context-from-dict.md)、
  [`patches/F-008-sqlite-migration.md`](patches/F-008-sqlite-migration.md)
  （F-006 / F-009 / F-010 为机械拆分 / 文档去重 / fixture rename，
  在 `tasks.md` 的 T-605~T-613 / T-905~T-907 / T-1005~T-1008 中直接列出，
  无需独立 patch 文档）

## 评分回顾（延续 2026-05）

| 维度 | 2026-05 | 目标 2026-06 |
|---|---|---|
| 交付度 | ★★★★★ | 保持 |
| 测试质量 | ★★★★☆ | 冲 ★★★★★（F-005 合同测试 + F-007 反向依赖测试） |
| 契约清晰度 | ★★★★★ | 保持 + 新增 ADR-0008「Artifact rating scaling compatibility」 |
| 抽象迁移能力 | ★★★★★ | 保持 |
| 生产鲁棒性 | ★★★☆☆ | 冲 ★★★★☆（artifact 加载版本契约 + 模块结构清晰度） |
| 文档结构 | ★★★☆☆ | 冲 ★★★★☆（F-009 去重 + F-010 命名统一） |

## 交接顺序

1. 新成员先读 [`2026-05-spec-completion.md`](2026-05-spec-completion.md)（了解上轮做了什么）
2. 再读本文件（了解这轮要做什么）
3. 进入 [`spec-v2/README.md`](spec-v2/README.md) 看 DoD
4. 按 `spec-v2/tasks.md` 的 T-XXX 执行
5. PR merge 后归档：`findings.md` 把 F-005~F-010 翻 `resolved`，
   新建 `docs/claude-review/2026-06-spec-completion.md`，
   冻结 V3 快照（`docs/V3_Knowledge/`）。
