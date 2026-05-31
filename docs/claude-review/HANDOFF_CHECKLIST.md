# Handoff Checklist · Historical Checklist

> Historical checklist from the 2026-05-12 Claude review packet; it is not the current handoff.
> Opus review should start from `docs/opus-review/HANDOFF.md`,
> then verify live status in `wiki/review-backlog.md`,
> `docs/codex-review/OPEN_RISKS.md`, and
> `docs/codex-review/QUALITY_GATES.md`.

> 目标：让下一个 Codex session 在开始写代码前 15 分钟内完成环境确认与评审预览。

## 1. 环境与代码分支

- [ ] 本地 checkout 的分支是 `spacex-session`
- [ ] `git log --oneline -8` 里至少包含 `e2658f6`、`59389ee`、`41cdea8` 三个关键交接 / 评审 commit；如果已有后续 triage commit，出现在它们上方也正常
- [ ] Python 解释器版本 ≥ 3.9（本地验证过 3.12）
- [ ] `pip install -r requirements.txt` 已执行（`numpy / scipy / pytest` + 生成资产需要 `matplotlib`、`pillow`）

## 2. 质量门（应全部绿）

| 命令 | 预期 | 大致耗时 |
|---|---|---|
| `python -m pytest tests -q` | historical snapshot; current count lives in `docs/codex-review/QUALITY_GATES.md` | ~1 s |
| `python -m analysis.run_all` | historical snapshot; current study set lives in `docs/codex-review/QUALITY_GATES.md` | ~3 s |
| `python -m examples.demo_sre_loop` | 打印 12 行 tick trace，无异常 | <1 s |
| `python -m examples.demo_powered_descent` | PDG 末态位置 ~2e-6 m | ~0.5 s |
| `python -m examples.demo_catch_phase` | 末态 lateral_error 稳定在窗口内 | ~1 s |
| `python -m scripts.build_kb` | 16 个 asset 重建完毕 | ~60 s |

## 3. 阅读顺序（20 分钟预算）

- [ ] 2 min · 本文件 `HANDOFF_CHECKLIST.md` 自己
- [ ] 5 min · `CODEX_TRIAGE.md`（Codex 二次梳理：已修 / 未修 / 口径漂移）
- [ ] 5 min · `REVIEW_OF_CODEX_SESSION.md` 的 §6（发现的缺陷）+ §8（评审结论）
- [ ] 8 min · `DETAILED_ARCHITECTURE.md` 的 §2（container view）+ §4（runtime view）+ §6（依赖方向护栏）

## 4. 必读文档（如果有 60 分钟）

按顺序：

1. `claude-review/README.md` ← 本包导航
2. `claude-review/HANDOFF_CHECKLIST.md` ← 你正在看的
3. `claude-review/CODEX_TRIAGE.md` ← Codex 对评审包的二次梳理
4. `claude-review/REVIEW_OF_CODEX_SESSION.md` ← 上一 session 的评审
5. `claude-review/DETAILED_ARCHITECTURE.md` ← 五视图架构
6. `claude-review/EVENT_LIFECYCLE.md` ← 事件时序
7. `claude-review/FAILURE_MODES.md` ← 失效与降级
8. `docs/EVENT_SCHEMA.md` ← Codex 上一轮写的 schema 指南
9. `docs/API_CONTRACTS.md` ← Codex 上一轮写的 API 契约
10. `docs/RUNTIME_STATES.md` ← Codex 上一轮写的状态机
11. `docs/knowledge-base.html` ← 主入口（可以放到浏览器看 GIF）

## 5. 本轮交接的三个 invariants（不能破坏）

### ✅ Invariant 1 · 依赖方向单向
- **`starship/` 不得 import `sre_control/`**
- 验证：`tests/test_import_graph.py` 必须通过

### ✅ Invariant 2 · 事件 schema 封闭
- 新增 event kind 必须同步更新 `EVENT_COUNTEREXAMPLES` + 测试 + `EVENT_SCHEMA.md`
- 验证：`test_all_runtime_events_follow_shared_schema` 必须 pass

### ✅ Invariant 3 · 降级路径对齐
- `runtime.degraded = True` 必然伴随至少一个 `DEGRADED_*` 状态和至少一条 event
- 验证：`test_sre_stack_*_upward` 系列的 5 个测试必须 pass

## 6. 已知不阻塞项（下轮候选）

来自 `REVIEW_OF_CODEX_SESSION.md §6`：

- [小] `test_event_schema.py` 里 `"Do not" in counterexample` 字符串签名脆（已改为允许 `Do not` / `Avoid` 前缀）
- [小] `API_CONTRACTS.md §2.9 CatchController` 曾容易误导；主文档已补物理层边界，后续只需清理旧 open-list 口径
- [小] `ARCHITECTURE.md` 与 `CODEX_HANDOFF.md` 都提到 CatchController wrapper 建议，后续可收敛到一处

来自 `DETAILED_ARCHITECTURE.md §8 演化蓝图`：

- [中] 加 `starship/stability_monitor.py`（§2.1 Lyapunov）（已完成）
- [中] 加 `tests/test_import_graph.py` 护栏住依赖方向（已完成）
- [中] 加 `analysis/s10_failure_trace.py` 把事件本身变成 before/after 图（已完成）
- [中] 加 `innovation_gating` 到 `SignalFusion` 防 outlier 污染 posterior（已完成）

来自 `FAILURE_MODES.md §哨兵测试`：

- [中] 加 `tests/test_sentinels.py` 三条哨兵
- [大] 给 `SREControlStack.step()` 加 try/except 把 adapter 异常转成 stability 事件（已完成；后续可细化 fallback 策略）

## 7. 如果要动 API，请先做这三件事

1. **写 `RFC` 注释**（代码或 PR 描述中）说明为什么要改
2. **更新 `API_CONTRACTS.md`** 对应小节
3. **同步 `DETAILED_ARCHITECTURE.md`** 的 container view / runtime view

这个顺序保证文档不会滞后于代码。

## 8. 如果要改 events，请先做这四件事

1. 改 `EVENT_COUNTEREXAMPLES`
2. 改产生 event 的 adapter 代码路径
3. 改 `tests/test_event_schema.py` 让新 kind 被真实触发
4. 改 `EVENT_SCHEMA.md` 和 `DETAILED_ARCHITECTURE.md §3.3` 的索引表

这个顺序保证 schema/实现/测试/文档四点对齐，不会 drift。

## 9. 与本轮评审相关的 commit 摘要

```
e2658f6 docs: refresh CODEX_HANDOFF and ship V2_Knowledge snapshot
59389ee review: ship claude-review handoff package with detailed architecture
41cdea8 review: align DEGRADED_GUARD + cover guardrail/allocator event propagation
d9cecb7 补齐静态 SRE 原语事件追踪
1ee8ae5 统一 SRE runtime event schema
2c82861 补齐剩余 SRE adapter 本地事件
5e0a94e 下沉 SRE adapter 本地 failure trace
70c1d6a 补齐 SRE 控制栈运行态追踪
4319a41 完善 SpaceX→SRE 交接与契约文档
43b58a9 文档：补齐 SpaceX→SRE 架构交接与审查材料
```

**最近一个 reviewer 修复 commit（`41cdea8`）**：
- 修复 `stack.step()` 的 guardrail 分支没加 `DEGRADED_GUARD` 的问题
- 补 `test_sre_stack_carries_guardrail_events_upward`、`test_sre_stack_carries_allocator_events_upward`
- 动态化 `run_all.py` 里的 `"All X studies"` 文案

**后续包装 commit**：
- `59389ee` 建立 `docs/claude-review/` 评审包
- `e2658f6` 刷新 `CODEX_HANDOFF.md` 并新增 `docs/V2_Knowledge/`

## 10. 交接最后一步

当你读完本包、跑通所有质量门、理解了 3 个 invariants，请在你**第一个 commit** 的
message 末尾加一行：

旧的 commit-message acknowledgment 已废弃；当前接手确认以
`docs/opus-review/HANDOFF.md` 和 live ledgers 为准。
