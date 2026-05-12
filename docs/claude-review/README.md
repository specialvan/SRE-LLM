# Claude Review · 移交包

> 本文件夹是 Claude Reviewer 将工程包移交给 Codex 下一轮 session 的**一份独立、可
> 离线阅读**的评审包，不依赖 `docs/` 根目录任何其他文档。

## 内容清单

| 文件 | 作用 |
| --- | --- |
| [`REVIEW_OF_CODEX_SESSION.md`](./REVIEW_OF_CODEX_SESSION.md) | 对 Codex 上一 session 的六个 commit 的逐 commit 评审、质量门、P0/P1/P2 发现 |
| [`DETAILED_ARCHITECTURE.md`](./DETAILED_ARCHITECTURE.md) | 五视图架构：context / container / component / runtime / deployment，带 mermaid |
| [`EVENT_LIFECYCLE.md`](./EVENT_LIFECYCLE.md) | 一个 tick 的事件时序图 + 3 种典型场景（正常/brown-out/surge）的逐帧追踪 |
| [`FAILURE_MODES.md`](./FAILURE_MODES.md) | 每个模块的失效模式、检测手段、降级路径、恢复条件 |
| [`HANDOFF_CHECKLIST.md`](./HANDOFF_CHECKLIST.md) | Codex 接手前逐项检查表（读文件顺序 / 复现命令 / 预期输出 / 已知不阻塞项） |
| [`CODEX_TRIAGE.md`](./CODEX_TRIAGE.md) | Codex 对本评审包的二次梳理：打回点、已修事实、漂移口径、下一步队列 |

## 阅读顺序

**Codex 只有 25 分钟预算怎么读？**

1. [`HANDOFF_CHECKLIST.md`](./HANDOFF_CHECKLIST.md) — 2 分钟，看跑哪几条命令应该看到什么
2. [`CODEX_TRIAGE.md`](./CODEX_TRIAGE.md) — 5 分钟，看哪些打回点已修、哪些仍是 backlog
3. [`REVIEW_OF_CODEX_SESSION.md`](./REVIEW_OF_CODEX_SESSION.md) 第 6、8 节 — 5 分钟，看原始发现和结论
4. [`DETAILED_ARCHITECTURE.md`](./DETAILED_ARCHITECTURE.md) §2/§4 — 8 分钟，看 container + runtime 两个视图
5. [`EVENT_LIFECYCLE.md`](./EVENT_LIFECYCLE.md) §3 — 5 分钟，看 brown-out 场景逐帧事件

**有 60 分钟全读？** 按上面顺序 1→2→3→4→5→[`FAILURE_MODES.md`](./FAILURE_MODES.md)。

## 本轮移交的主要结论

| 维度 | 状态 |
| --- | --- |
| 质量门 | 51 passed / 10 studies / HTML well-formed / JSON OK |
| 架构方向 | ✅ 依赖方向正确，starship 不反向依赖 sre_control |
| 可观测性 | ✅ 10 种 runtime event 已覆盖 8 个核心 adapter + gating / stability |
| 评审发现 | 1 中等（已修）+ 3 非阻塞建议 |
| Codex triage | ✅ 已补 [`CODEX_TRIAGE.md`](./CODEX_TRIAGE.md)，标注已修项、未修项和评审包口径漂移 |
| 依赖护栏 | ✅ 已补 `tests/test_import_graph.py` 固化 `starship/` 不反向依赖 `sre_control/` |
| 下轮建议 | 给 s10 增加全量 JSONL / dashboard 查询样例，并继续细化 stability fallback |

## Claude Reviewer 的关注点（给 Codex）

**在下一轮动任何东西之前**，请先读完 [`DETAILED_ARCHITECTURE.md §6 依赖方向护栏`](./DETAILED_ARCHITECTURE.md) 和 [`FAILURE_MODES.md §失效传播矩阵`](./FAILURE_MODES.md)。本轮评审最容易被无意破坏的两条约束是：

1. **`starship/` 不得 import `sre_control/`**（物理层不能反向依赖迁移层）
2. **stack 的 `runtime.degraded` 总开关必须对齐 `DEGRADED_*` 状态**——任何 adapter 进入降级必须同时更新 `runtime_states` 和 `runtime_events`（本轮评审发现 `DEGRADED_GUARD` 曾漏掉，已补）

如果新增模块或事件，请同时更新：

- `sre_control/events.py::EVENT_COUNTEREXAMPLES`
- `docs/EVENT_SCHEMA.md`
- `docs/claude-review/DETAILED_ARCHITECTURE.md`（的组件视图和降级矩阵）
- `tests/test_event_schema.py`（真实触发新 kind）
- `tests/test_contracts.py`（栈级传播）
