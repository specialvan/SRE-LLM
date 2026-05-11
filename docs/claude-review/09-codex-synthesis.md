# Claude Review 深度梳理 · Codex 执行版

> 目的：把 `docs/claude-review/` 中的 Claude 打回评审，整理成下一轮 Codex 可直接开工的判断、优先级、风险边界和执行路线。  
> 适用范围：`auto-decide-session` 分支，当前 review pack + V2_Knowledge 状态。  
> 当前日期：2026-05-12

> **Codex 进展更新**：AI-01 / AI-02 / AI-03b 已在 2026-05-12 收口。当前 canonical benchmark：`collision_rate=0%`、`planner_emergency_rate=4.18%`、`cbf_fallback_rate=4.82%`，demo SLO 通过；新增观测项 `planner_best_effort_rate=63.76%`，作为下一轮生产化风险。

## 1. 一句话结论

Claude 没有否定 auto-decide 的工程方向。

相反，它的判断是：

> trace 契约、benchmark 契约、CBF 测试矩阵和文档体系已经合格；真正的问题是 benchmark 首次量化出了一个以前被“0 碰撞率”遮住的可用性 SLO 违约。

核心矛盾不是“系统不安全”，而是：

```text
结构化链路确实安全
  但安全主要靠 emergency_brake / fallback_brake 兜底
  说明 nominal policy 没有主动配合 CBF
  因此系统可用性不达标
```

这就是 P0 的根。

## 2. 当前状态校准

### 已稳定的部分

| 领域 | 状态 | 说明 |
| --- | --- | --- |
| 碰撞安全 | 通过 | canonical benchmark 中 structural collision_rate = 0 |
| trace 契约 | 通过 | `schema_version = 1.1`，JSONL 严格可解析；v1.1 仅扩展 status enum |
| benchmark metrics | 通过 | `benchmark.metrics.v1`，已有机器可读输出 |
| CBF 基础测试 | 通过 | 已覆盖 braking-distance 随速度和低摩擦膨胀 |
| 文档入口 | 基本通过 | README / V2_Knowledge / claude-review 已建立入口层 |
| 单元测试 | 通过 | `27 / 27` 绿（Codex AI-01/02/03b 后） |

### 已解除的 P0/P1 阻塞

| 阻塞 | 指标 | 当前值 | 目标 |
| --- | --- | --- | --- |
| AI-01 | `planner_emergency_rate` 红线测试 | ✅ 已固化，无 xfail | demo 阈值 `<= 10%` |
| AI-02 | nominal policy 可用性 | ✅ emergency = 4.18% | 降到 `<= 10%` 且碰撞率保持 0 |
| AI-03b | status 枚举 | ✅ 已封闭，含 `best_effort` | trace 中枚举常量 + 测试 |

### 新的剩余风险

| 风险 | 指标 | 当前值 | 下一步 |
| --- | --- | ---: | --- |
| Lyapunov 恢复态偏高 | `planner_best_effort_rate` | 63.76% | AI-12 后继续拆分状态组合与 recovery 原因 |
| CBF fallback 贴近生产阈值 | `cbf_fallback_rate` | 4.82% | AI-14 固化 artifact，后续优化 nominal 前瞻 |

### 已由 Claude 后处理的项

当前工作区 diff 显示 Claude 已经做了这些 P1/P2 易改项，但尚未提交：

| AI | 状态 | 文件 |
| --- | --- | --- |
| AI-03a | 已改 | `docs/architecture.html` title mojibake 修复 |
| AI-03c | 已改 | `.gitignore` 忽略 `.local-artifacts/`、`summaizer/`、`artifacts/` |
| AI-04 | 已改 | `docs/trace-schema.md`、`docs/benchmark-metrics.md` 增加 Schema Evolution |
| AI-09 | 已改 | `examples/compare_e2e_vs_structural.py` 标注 `_pure_e2e_step` 为 INV-G2 合法例外 |
| AI-10 | 部分已改 | README 已有 `Primary Entry` 段，但 V2 current-state 里仍把 AI-10 标 pending |

注意：这些改动在 `git status` 里仍是未提交状态。下一轮如果要提交，必须确认是否把整个 `docs/claude-review/` 和 `docs/V2_Knowledge/` 一起纳入同一个 docs commit。

## 3. Claude 的真实 critique

### 表层结论

表层上看，Claude 报了 12 个 findings：

- P0：2 个
- P1：3 个
- P2：7 个

但真正的主线只有一条：

> benchmark 指标告诉我们：结构化链路把“撞车”转化成了“频繁紧急刹停”。这是一种安全成功，但不是产品成功。

### 深层原因

`GradientPolicy` 是一个势能场名义策略，它只知道：

- 目标在哪；
- 势能往哪下降；
- 当前速度与目标速度的误差；
- 障碍物在 potential 里带来排斥项。

它不知道：

- CBF 在未来几步会不会拦它；
- braking-distance barrier 何时会变负；
- 低摩擦会怎样放大停车距离；
- T_inv 的 Lyapunov 检查会不会把它打成 emergency。

因此链路经常变成：

```text
GradientPolicy 输出还想加速 / 不够早减速
  -> CBF 一开始可能认为 nom_ok
  -> 等 barrier 逼近时 QP 找不到温和可行解
  -> fallback_brake
  -> T_inv emergency_brake
```

这解释了为什么 `nom_ok` 可以很高，同时 `emergency_brake` 也很高。
`nom_ok` 高不代表策略聪明，只代表“当前一阶 barrier 条件暂时没拦住它”。

## 4. Finding 分组

### P0：必须先做

#### F-P0-01 / AI-01：benchmark SLO 红线断言

本质：把 Claude 发现的 emergency/fallback 违约变成测试守门。

为什么先做：

- 没有测试，下一轮可能“优化数字”时把问题调没。
- 有 xfail 后，P0 会在 CI 里持续发声，但不阻塞当前已知坏状态。
- AI-02 一旦真修好，`strict=True` 会触发 XPASS，强制去掉 xfail。

正确做法：

1. 在 `tests/test_benchmark_metrics.py` 加 strict xfail 测试。
2. 断言：
   - `collision_rate == 0`
   - `planner_emergency_rate <= 0.10`
   - `cbf_fallback_rate <= 0.10`
3. 文档加 SLO 阈值参考表。

不要做：

- 不要 skip。
- 不要降低测试规模到“刚好 pass”。
- 不要先调参数让 xfail 过。

#### F-P0-02 / AI-02：升级 nominal policy

本质：把名义策略从“只会沿势能走”升级成“知道前方 barrier 会变坏时提前减速”。

Claude 推荐的最小方案：

```text
GradientPolicy
  -> PredictiveBrakePolicy wrapper
  -> short rollout
  -> check barrier.h(predicted)
  -> if risk: clamp jerk downward
```

为什么这是正路：

- 不改变硬约束；
- 不缩小 safety buffer；
- 不放松 CBF；
- 让上游策略主动减少下游 fallback。

验收标准：

- default benchmark `n=50 seed=0 horizon=100 dt=0.1`
- `collision_rate == 0`
- `planner_emergency_rate <= 10%`
- `cbf_fallback_rate <= 10%`
- 新增 policy 单测证明障碍前 nominal 自己会预刹。

### P1：P0 前后都可以做，但不能抢主线

#### AI-03b：status 枚举封闭

本质：trace contract 里 `status` / `cbf_status` 不能靠口头约定。

需要做：

- `auto_decide/trace.py` 增加：
  - `PLANNER_STATUS_VALUES`
  - `CBF_STATUS_VALUES`
  - `_validate_status()`
- `build_trace_record(..., strict=True)` 默认校验；
- `tests/test_trace.py` 增加 enum 内容和非法值拒绝测试；
- `docs/trace-schema.md` 明列 5 个 planner status 和 3 个 CBF status；
- `docs/codex-handoff.md` 不再维护副本，统一指向 trace-schema。

风险：

- 如果直接 assert，可能破坏某些手工构造 trace 的测试；建议按 patch 04 加 `strict=True` 参数，并确保现有测试输入使用合法值。

### P2 / P3：后续增强

| AI | 主旨 | 何时做 |
| --- | --- | --- |
| AI-05 | architecture.html 消费 metrics JSON | AI-01 后 |
| AI-06 | `_jsonable` debug logging | 可独立 |
| AI-07 | architecture 补失败树 / 场景矩阵 | 文档批次 |
| AI-08 | deep-dive 给 trace.py 独立一节 | 文档批次 |
| AI-10 | hub 文档 primary entry | 目前部分已做，需状态对齐 |
| AI-11 | grep invariant scanner | AI-03b / AI-09 后 |
| AI-12 | 禁止 status 组合测试 | AI-03b 后 |
| AI-13 | graph EPS cutoff | 独立小测试 |
| AI-14 | benchmark JSON CI artifact | AI-01 后 |

## 5. 执行顺序建议

Claude 给出的 PR 序列很长，但结合当前工作区状态，建议收敛成三轮：

### Round A：把 review pack 本身收口

目标：把 Claude 已生成的评审资产和已做的小修提交干净。

包含：

1. `docs/claude-review/`
2. `docs/V2_Knowledge/`
3. `.gitignore`
4. `README.md`
5. `docs/architecture.html`
6. `docs/trace-schema.md`
7. `docs/benchmark-metrics.md`
8. `docs/codex-handoff.md`
9. `examples/compare_e2e_vs_structural.py` 的 AI-09 注释

提交前要做：

- `pytest -q`
- `git status --short --branch`
- 确认 `.local-artifacts/`、`summaizer/`、`artifacts/` 不入仓

建议 commit：

```text
docs: 纳入 Claude review pack 与 V2 知识库
```

### Round B：契约守门

目标：先把“不能继续漂移”的契约钉住。

包含：

1. AI-03b status enum
2. AI-01 benchmark SLO strict xfail
3. 可选 AI-11 invariant scanner 初版

为什么 AI-01 放在 AI-02 前：

- 它应该先失败，作为待修红线；
- 否则 AI-02 没有明确度量目标；
- 它会防止“调硬约束参数”伪修复。

建议 commit：

```text
test: 锁定 trace status 与 benchmark SLO 红线
```

### Round C：真正修 P0 可用性

目标：实现 PredictiveBrakePolicy，使 nominal policy 主动配合 CBF。

包含：

1. 新增 `auto_decide/policies/`
2. 新增 `PredictiveBrakePolicy`
3. `StructuralPlanner.__post_init__` 自动 wrap 默认 `GradientPolicy`
4. 新增 `tests/test_policies.py`
5. 去掉 AI-01 的 xfail
6. 更新 benchmark log

建议 commit：

```text
feat: 引入 PredictiveBrakePolicy 降低 emergency rate
```

## 6. 风险边界

### 绝对不能用来“修”P0 的手段

这些做法会让指标变好看，但破坏系统意义：

| 禁止手段 | 为什么错 |
| --- | --- |
| 调小 `game.base_buffer` | 缩小安全冗余，背离 worst-case game |
| 调松 `cbf_alpha` | 改变硬屏障收敛性质 |
| 调小 `BrakingDistanceBarrier.reaction` / `safety` | 低估 jerk latency / 摩擦不确定性 |
| 调大 `invariant.tol` | 把不稳定误标成稳定 |
| 把距离项塞回 Lyapunov V | 已知会让系统前进时假性不稳定 |
| 把 CBF 改成 loss | 失去前向不变性语义 |

### 可以合理调的手段

这些属于 nominal policy 层，方向正确：

| 可调项 | 作用 |
| --- | --- |
| `PredictiveBrakePolicy.t_lookahead` | 提前多远感知 barrier 风险 |
| `PredictiveBrakePolicy.brake_jerk` | 预刹强度 |
| 前瞻 rollout 步长 | 计算量和前瞻精度权衡 |
| 只检查 terminal state 还是整条 trajectory | 更精确但更贵 |

## 7. Review Pack 文件职责重整

| 文件 | 应怎么用 |
| --- | --- |
| `README.md` | 确认包的范围和阅读顺序 |
| `00-executive-summary.html` | 5 分钟读懂结论 |
| `01-findings.md` | 问题源，按 finding ID 追溯 |
| `02-architecture-deep.html` | 架构深图，尤其场景矩阵和失败树 |
| `03-invariants-catalog.md` | 每次改代码前扫守护不变式 |
| `04-contracts-catalog.md` | 改接口前看 pre/post/invariant |
| `05-action-items.md` | 真实 sprint log |
| `06-suggested-patches/` | 可复制的实现骨架 |
| `07-codex-directives.md` | 硬规则，不是建议 |
| `08-benchmark-log.md` | benchmark 历史基线 |
| `09-codex-synthesis.md` | 本文件：把评审翻译成执行路线 |

## 8. 下一步操作清单

如果下一条指令是“继续”，建议按这个顺序做：

1. 跑 `pytest -q`，确认 27 tests 全绿。
2. 跑 canonical benchmark：
   ```bash
   python -m examples.compare_e2e_vs_structural --n 50 --seed 0 --horizon 100 --dt 0.1 --metrics-out .local-artifacts/benchmark-metrics-seed0-n50.json
   ```
3. 做 AI-11：CI invariant scanner。
4. 做 AI-12：T_inv / CBF 非法组合测试，包含 `(best_effort, fallback_brake)`。
5. 做 AI-14：benchmark JSON 固化为 CI artifact。
6. 把结果追加到 `docs/claude-review/08-benchmark-log.md`。

## 9. 最小验收线

下一轮真正算“过 Claude 这次打回”的最低线：

```text
AI-01 done
AI-02 done
AI-03b done
pytest 全绿
canonical benchmark:
  collision_rate == 0
  planner_emergency_rate <= 0.10
  cbf_fallback_rate <= 0.10
docs/claude-review/08-benchmark-log.md 追加 post-AI-02 记录
```

这条线已经达到。下一轮的最低线变成：AI-11 / AI-12 / AI-14 至少完成其一，并保持上述 benchmark demo SLO 不回退。

## 10. 给下一轮 Codex 的提醒

不要把 Claude review 当作文档要求。
它实际是在保护一个工程原则：

> 智能层可以变聪明，但安全层不能变松。

如果一个修复让 emergency rate 降了，但同时让 hard gate 更松，那不是修复，是把报警器拆掉。

正确方向是让 nominal policy 提前看见硬边界，并主动给硬边界留余量。
