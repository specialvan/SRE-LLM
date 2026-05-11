# Spec v2 · 2026-06 轮可执行版

本目录是 2026-06 轮的"可执行"层。入口详见
[`../2026-06-session-review.md`](../2026-06-session-review.md)。

## 本轮覆盖范围（C + A2）

- **F-005**（主攻）—— `rating_scaling` 常数做成显式契约，artifact 交叉验证
- **F-007**（主攻）—— `cli._ctx_from_dict` 晋升为 `ReleaseContext.from_dict`
- **F-006**（配套）—— `sre/artifacts.py` 488 行按职责拆包
- **F-008**（配套）—— SQLite migration v5 特判理顺
- **F-009**（配套）—— `codex-handoff.md` 与 `implementation-roadmap.md` 去重
- **F-010**（配套）—— replay fixture 命名统一 + README

## 文件

| 文件 | 作用 |
|---|---|
| [`requirements.md`](requirements.md) | EARS-A2 acceptance criteria, R-305 ~ R-710 |
| [`design.md`](design.md) | 组件变更 + 模块拆分图 + 不做的事 |
| [`tasks.md`](tasks.md) | T-400 ~ T-790 编码任务清单 + 依赖矩阵 + 反查表 |
| [`verification.md`](verification.md) | 每个 PR 的验证命令 + 快照 |

## PR 编排

```
PR-fix-05  — F-005 rating scaling contract       (最高价值,artifact 稳定性)
PR-fix-06  — F-006 artifacts 包结构拆分           (机械拆分,零行为变更)
PR-fix-07  — F-007 ReleaseContext.from_dict      (公共 API,影响 5 个调用点)
PR-fix-08  — F-008 SQLite migration idempotent   (消 special-case)
PR-fix-09  — F-009 文档去重                       (只改 .md)
PR-fix-10  — F-010 fixture rename                 (只改测试夹具命名)
```

推荐顺序：**07 → 06 → 05 → 08 → 09 → 10**

理由：
- 07 (ReleaseContext.from_dict) 是纯加法 + 替换，先做避免后续 PR 冲突
- 06 (拆 artifacts.py) 是机械拆分，在加新逻辑前完成
- 05 (rating scaling contract) 基于 06 的新结构写
- 08/09/10 互相独立，可并行

## 完成标准（DoD）

1. R-305 ~ R-710 全部有测试覆盖
2. `pytest -q` 全绿（目标 ≥ 135 passed）
3. `bench p99 < 2.5 ms`（预算保持）
4. `findings.md` 中 F-005 ~ F-010 全标 `resolved`
5. 新建 ADR-0008 「Artifact rating scaling compatibility」
6. 新建 `docs/claude-review/2026-06-spec-completion.md`
7. V3 Knowledge 快照（`docs/V3_Knowledge/knowledge-base.html`）生成
