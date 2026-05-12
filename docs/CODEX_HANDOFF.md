# Codex Handoff

- 分支: `spacex-session`
- 更新时间: 2026-05-12
- 上一次编辑者: Codex triage (Claude review follow-up)
- 作用: 给下一位 Codex 的交接页，重点是当前状态、证据、风险和下一步

## 当前状态

这轮已经把 SpaceX 方案继续深挖成了**可审查、可交接、可复利**的 SRE 抽象层，核心脉络是：

- `starship/` 的 8 个数学支柱已经都落成可运行模块
- `sre_control/` 已经有同构适配层和端到端 `SREControlStack`
- `analysis/` 里有 8 组单主题 + 1 组端到端 + 1 组 failure-trace before/after 证据和总表
- `docs/` 里已经有架构、契约、运行态、事件 schema、知识库和审查入口
- `docs/claude-review/` 新增 Reviewer 移交包，并补了 Codex 二次 triage
- `docs/V2_Knowledge/` 新增一版面向跨 agent 协同的知识库快照（本轮新增）
- `tests/` 里已经补了模块级合同测试、堆栈级 trace 测试、event schema 测试、failure-trace 测试、stability monitor 测试和 import graph 护栏，共 51 passed

## 先读哪些

下一轮最值得先读的是：

1. [claude-review/README.md](./claude-review/README.md) — Reviewer 移交包导航（2 min）
2. [claude-review/HANDOFF_CHECKLIST.md](./claude-review/HANDOFF_CHECKLIST.md) — 环境核查 + 阅读预算（2 min）
3. [claude-review/CODEX_TRIAGE.md](./claude-review/CODEX_TRIAGE.md) — Codex 对 Claude 评审的二次梳理（5 min）
4. [claude-review/REVIEW_OF_CODEX_SESSION.md](./claude-review/REVIEW_OF_CODEX_SESSION.md) — 对上一 session 的评审与结论（5 min）
5. [claude-review/DETAILED_ARCHITECTURE.md](./claude-review/DETAILED_ARCHITECTURE.md) — 5 视图架构 + 依赖护栏（8 min）
6. [claude-review/EVENT_LIFECYCLE.md](./claude-review/EVENT_LIFECYCLE.md) — 单 tick 时序 + 3 场景逐帧追踪（5 min）
7. [claude-review/FAILURE_MODES.md](./claude-review/FAILURE_MODES.md) — 每模块 symptom/cause/degrade/recover
8. [V2_Knowledge/knowledge-base.html](./V2_Knowledge/knowledge-base.html) — 最新知识库快照（可视化入口）
9. [API_CONTRACTS.md](./API_CONTRACTS.md)
10. [RUNTIME_STATES.md](./RUNTIME_STATES.md)
11. [EVENT_SCHEMA.md](./EVENT_SCHEMA.md)
12. [ARCHITECTURE.md](./ARCHITECTURE.md)
13. [analysis/artifacts/SUMMARY.txt](../analysis/artifacts/SUMMARY.txt)

## 8 个支柱地图

| # | 支柱 | 能力 | SRE 映射 | Event kind |
|---|---|---|---|---|
| 1 | Lossless Convexification | 非凸下界的凸化 | `PoolCapacityPlanner` | `pool_capacity_clipped` |
| 2 | SCP | 线性化 + trust region 迭代 | `CanaryScheduler` | `rollout_rejected` |
| 3 | 6-DoF / SO(3) | 流形状态演化 | `TopologyState` | `topology_state_repaired` |
| 4 | Thrust cone | 方向锥 + 幅值硬护栏 | `SLOGuardrail` | `unsafe_proposal_projected` |
| 5 | EKF | 多源观测融合 | `SignalFusion` | `missing_sensor` |
| 6 | MPC | 预测式滚动优化 | `PredictiveAutoscaler` | `replica_bound_active` |
| 7 | Flip | 最短时间切换 | `FastTrafficSwitcher` | `deadline_exceeded` |
| 8 | Allocation | 有界最小二乘分配 | `WeightedLoadBalancer` | `bounded_ls_residual` |

8 个支柱 × 8 个核心 runtime event 已一一对应；另外 `outlier_rejected` 和 `stability_violation` 覆盖观测门控与稳定性红线。全部 kind 通过 `sre_control/events.py` 的 `EVENT_COUNTEREXAMPLES` 封闭命名空间。

## 三大不变量（继续守护）

1. **依赖方向单向**：`starship/` 绝不 import `sre_control/`（物理层不污染迁移层）
2. **事件 schema 封闭**：新 kind 必须同步 `EVENT_COUNTEREXAMPLES` + `EVENT_SCHEMA.md` + 测试
3. **降级路径对齐**：`runtime.degraded = True` 必然伴随 `DEGRADED_*` 状态和至少一条 event

## 本轮做了什么

### 契约与运行态（`43b58a9` / `4319a41`）
- 新增 [API_CONTRACTS.md](./API_CONTRACTS.md)、[RUNTIME_STATES.md](./RUNTIME_STATES.md)
- 修正 `sre_control/weighted_balancer.py` 里的 `numpy.bool_` 输出，保证 trace 可 JSON 序列化
- 给 `SREControlStack.step()` 增加 `runtime.states` / `runtime.events`，让降级路径进入 trace

### 事件下沉（`70c1d6a` / `5e0a94e` / `2c82861` / `d9cecb7`）
- 把 `missing_sensor`、`unsafe_proposal_projected`、`bounded_ls_residual` 下沉到 adapter 本地 events
- 把 `rollout_rejected`、`replica_bound_active`、`deadline_exceeded` 也补成 adapter 本地 events
- 把 `pool_capacity_clipped`、`topology_state_repaired` 补齐

### Schema 统一（`1ee8ae5`）
- 新增 [EVENT_SCHEMA.md](./EVENT_SCHEMA.md)，统一 runtime event schema 与 counter-example registry
- 新增 `sre_control/events.py`，固定 `make_event`、`validate_event` 和 `EVENT_COUNTEREXAMPLES`
- 新增 `tests/test_event_schema.py`，确保每种 event kind 都真实生成、满足 schema、带 counter-example

### 评审补强（`41cdea8` / `59389ee`）
- 修 `SREControlStack.step()` 的 guardrail 分支缺失 `DEGRADED_GUARD` 状态对齐问题
- 新增 2 条 contract 测试覆盖 guardrail 与 allocator 的事件上浮
- 动态化 `analysis/run_all.py` 的 `"All X studies"` 文案
- 建立 [`docs/claude-review/`](./claude-review/) 六件套移交包（REVIEW + DETAILED_ARCHITECTURE + EVENT_LIFECYCLE + FAILURE_MODES + HANDOFF_CHECKLIST + README）

### Claude review triage（本轮）
- 新增 [claude-review/CODEX_TRIAGE.md](./claude-review/CODEX_TRIAGE.md)，逐项标注 Claude 发现的已修 / 未修 / 口径漂移
- 修正 [claude-review/HANDOFF_CHECKLIST.md](./claude-review/HANDOFF_CHECKLIST.md) 和 [V2_Knowledge/knowledge-base.html](./V2_Knowledge/knowledge-base.html) 里固定旧 commit 的说法
- 新增 `tests/test_import_graph.py`，固化 `starship/` 不得 import `sre_control/`，并守住 `sre_control/events.py` 不依赖 `starship`
- 放宽 `tests/test_event_schema.py` 的 counter-example 文案签名，允许 `Do not` / `Avoid` 前缀

### 可观测性与稳定性补强（后续本地提交）
- 新增 `analysis/s10_failure_trace.py` 和 `tests/test_failure_trace.py`，把 event lifecycle 变成可复现 before/after 证据
- `analysis.run_all` 已扩展到 10 studies，`SUMMARY.txt` 包含 `§10 · Failure trace`
- `SignalFusion` 增加 innovation gating，新增 `outlier_rejected` event，防止异常观测污染 posterior
- `SREControlStack.step()` 增加 adapter 异常兜底，异常转 `stability_violation` event 并继续 tick
- 新增 `starship/stability_monitor.py` 与 `sre_control/stability_guard.py`，用 Lyapunov `dV/dt` 监视稳定性红线

## 关键证据

最新总表里，最值得记住的几组数是：

- `pos_err 148.3 -> 2.125e-6` （§1 PDG）
- `angle_rmse 0.0558 rad -> 5.715e-7 rad` （§3 刚体动力学）
- `cone_violations 97.4% -> 0%` （§4 硬护栏）
- `vel_rmse 481.1 -> 51.07` （§5 EKF 融合）
- `final_err 0.01192 -> 3.463e-7` （§6 MPC）
- `saturation_violation 33.75% -> 0%` （§8 有界分配）
- SRE 栈：`slo_violation_pct 25 -> 10`, `mean_replicas 18.43 -> 26.5` （§9 端到端）
- Failure trace：`0 events / 0 kinds -> 83 events / 4 kinds` （§10 事件级证据）

这些数说明的是"场景内可复利"，不是"官方内部实现"，也不是跨场景普适定理。

## 已验证

```bash
python -m pytest tests -q          # 51 passed
python -m analysis.run_all         # 10 studies finished in ~3s
python -m examples.demo_sre_loop   # 12-tick trace printed
python -m examples.demo_powered_descent
python -m examples.demo_catch_phase
python -m scripts.build_kb         # 16 assets rebuilt (~60s)
```

## 风险与坑

- 这些 before/after 结果是合成场景证据，不要直接泛化成所有 SRE 场景
- `SREControlStack` 只是编排骨架，不是生产控制平面
- `WeightedLoadBalancer`、`SLOGuardrail`、`SCP`、`TopologyState` 这类模块最容易被边界条件打坏
- `CatchController` 的残差属于物理层 trace；要迁移成 SRE 事件时应包一层 adapter，不要让 `starship/` import `sre_control/`
- `analysis/artifacts/SUMMARY.txt` 里的运行时间类数字会随机器略微波动
- HTML 知识库和图像资产要一起看，否则很容易只看见文字没看见证据

## 下一步（按优先级）

### 小（非阻塞）
1. `ARCHITECTURE.md` 与本 handoff 都提到 CatchController wrapper 建议，未来收敛到一处

### 中（单 commit 可完成）
1. 给 `SREControlStack` 的 try/except fallback 增加更细的 stage-specific rollback 策略
2. 给 `analysis/s10_failure_trace.py` 增加 event JSONL 全量导出与 dashboard 查询示例
3. 把 `docs/knowledge-base.html` 按 `V2_Knowledge/knowledge-base.html` 的新模板整体重排

### 大（跨 session）
1. 给 `StabilityMonitor` 增加更真实的能量函数样例（例如 kinetic + potential + attitude error）
2. 给 `SignalFusion` 的 gating 增加分传感器阈值和恢复策略

## 备注

这份 handoff 的目标不是复述所有实现，而是让下一位 Codex 一眼看懂：

- 现在做到哪一步了
- 哪些文件是入口
- 哪些数值是证据
- 哪些地方最容易出坑
- 哪些约束绝不能破坏

请在接手的第一个 commit 的 message 末尾写一行 `Acknowledged: docs/claude-review/README.md`，
证明你是正式接过的手，而不是跳过了前一 session 的评审报告。
