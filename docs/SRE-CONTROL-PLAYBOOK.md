# SRE Control Playbook · 从 Attention Residuals 抽出的控制原语

> 目标：把《Attention Residuals》里真正有工程复利价值的原语剥出来，落成与深度学习无关的控制器，
> 在 SRE 控制工程（扩缩容、限流、流量调度、故障注入、容量规划、错误预算）里直接复用。

参考实现：[`attention_residuals/sre_control.py`](../attention_residuals/sre_control.py)
Demo：[`examples/demo_sre_autoscaler.py`](../examples/demo_sre_autoscaler.py)

---

## 0. 出发点：深度学习和 SRE 在结构上是同一个问题

在 Transformer 里：每一层面对"我该从历史层中抽取哪些信息、以什么比重"的问题。
在 SRE 里：每一个控制环面对"我该从哪些信号里（SLI / 错误预算 / 排队深度 / 成本）抽取多少权重，决定下一步动作"的问题。

两者的共同点：

- 输入是**异构信号集**，不是单一度量；
- 输出必须**归一化**（预算守恒、不能超发）；
- 某些输入**必须被关注**（错误预算烧穿 / P0 告警）；
- 必须**可审计**（事后解释"为什么扩容了"或"为什么没扩容"）；
- 必须有**快慢两条回路**（请求级节流 vs 天/小时级容量规划）；
- 必须**分段**以保住成本（全量相关的策略计算在规模上不可持续）。

Attention Residuals 恰好把这些约束都明面化了。把它抽成不依赖深度学习的 7 条原语，就是下文。

---

## 1. 七条原语 · 从论文机制到 SRE 控制器

| # | 论文机制 | 抽象出的原语 | SRE 落地类 | 典型场景 |
| --- | --- | --- | --- | --- |
| 1 | `AttnRes_l = Σ_k a_{l,k} · x_k`, `Σ a=1` | 预算守恒的加权融合 | [`WeightedConvexCombiner`](#wcc) | 任何"多信号 → 单动作"决策 |
| 2 | `last_weights()` 曝光权重 | 决策审计 | [`AuditTrail`](#audit) | 事后复盘 / 合规审计 |
| 3 | 纵横解耦的两套 W_Q | 快慢双回路 | [`DecoupledControlLoop`](#decoupled) | 请求级限流 vs 小时级容量 |
| 4 | Block Attention Residuals 的分段 | 层级控制 | [`HierarchicalBlockController`](#hier) | 全球 / 区域 / 单元 多级调度 |
| 5 | `LayerSkipGate` 的 σ 门 | 预算门控 | [`BudgetGate`](#gate) | 特性发布 / 灰度 / 故障注入 |
| 6 | `Σ a = 1` 中的 floor 约束 | 必然关注注册表 | [`MustAttendRegistry`](#reg) | 错误预算、安全告警、PII 事件 |
| 7 | §5 末段的"2 选 1" | 结构不冗余的强校验 | 在 `HierarchicalBlockController` 里以断言落地 | 避免双重补偿 |

---

<a id="wcc"></a>
## 2. Primitive 1 · 预算守恒的加权融合 `WeightedConvexCombiner`

### 机制
论文的 `Σ_k a_{l,k} = 1` 是一条硬约束——softmax 天然满足，不能降级成正则项。
在 SRE 里对应的约束是：**给每个信号的权重必须是一个凸组合**。这样才能保证"所有信号都被考虑、且总权重不会超发"。

```
logits_k = (q · K_k) / T + bias_k
a_k      = softmax_k(logits_k), clipped to [floor_k, ceiling_k]
y        = Σ_k a_k · v_k
```

### 典型场景
自动扩缩容：把 P99 延迟、排队深度、错误预算、成本这几个信号融合成一个 `replica_delta`。

```python
from attention_residuals.sre_control import SignalSpec, WeightedConvexCombiner

combiner = WeightedConvexCombiner(
    [
        SignalSpec("p99_breach"),
        SignalSpec("queue_depth"),
        SignalSpec("error_budget", floor=0.25),    # 必然关注
        SignalSpec("cost", ceiling=0.4),           # 成本信号最多拿 40% 权重
    ],
    query_dim=4,
    temperature=0.8,
)

# 每一步：
delta, weights = combiner.combine(query, [v_p99, v_queue, v_budget, v_cost])
```

### 落地要点
- **`bias`** 给运维人员一个"临时提权"的接口——例如灰度发布期间，把 `cost` 信号的 bias 拉到 `-1.0`，让成本信号暂时稀释掉但仍不低于 floor。
- **`temperature`** 控制"分裂型还是共识型"决策：T 小 ⇒ 决策更极端（赢者通吃）；T 大 ⇒ 决策更平均。
- **`floor + ceiling` 可行性**：`Σ floor ≤ 1 ≤ Σ ceiling`。`__init__` 会直接拒绝不可行的配置，防止上线后撕裂。

---

<a id="audit"></a>
## 3. Primitive 2 · 决策审计 `AuditTrail`

### 机制
每一次 `combiner.combine(...)` 之后立刻调用 `trail.record(combiner, action)`，把 `(step, signal_names, weights, action, context)` 追加到内存。
`to_jsonl()` 直接导出为 JSON Lines 给 ELK / ClickHouse / Loki 吃。

### 为什么必须有
Attention Residuals 的三大确定性之一是"可审计"。在 SRE 里这条是**合规红线**：每一次扩缩容决策、每一次限流触发、每一次熔断打开，都必须留下"基于哪些信号、权重多少"的痕迹。
没有 audit trail 的控制器，在 P0 故障复盘时就是黑箱。

### 落地要点
- 审计是廉价的——一条记录 ≤ 1 KB，30 天保留也就几百 MB。
- 权重时间序列还可以反向回放：训练一个"反常决策检测器"，用过去 30 天的 weights 分布做异常检测。

---

<a id="decoupled"></a>
## 4. Primitive 3 · 快慢双回路 `DecoupledControlLoop`

### 机制
Attention Residuals §5.2 的纵横解耦：**横向 W_Q 管上下文依赖；纵向 W_Q 管层间依赖；两者 W_Q 不共享**。
在 SRE 里对应：
- **fast_loop**：每 tick（每秒 / 每请求）跑，处理"此刻的尖峰 / 抖动"。
- **slow_loop**：每 N tick（每分 / 每小时）跑，处理"容量规划 / 预算趋势"。
两者各自维护自己的 `W_K`，彼此不共享；最后用一个 meta 参数 `α` 把两条路输出合起来：`y = (1-α) fast + α slow`。

### 为什么必须分开
- **时间尺度错配**：把 fast 和 slow 逻辑混在同一个控制器里，会让 slow 的梯度被 fast 的噪声掩盖（对应论文里"横向梯度掩盖纵向梯度"）。
- **故障隔离**：fast_loop 的故障（例如 P99 采集断流）不应立刻污染 slow_loop 的预算追踪。
- **变更隔离**：slow_loop 的策略迭代周期通常比 fast_loop 慢一个数量级，解耦后可以独立发版。

### 落地模板

```python
from attention_residuals.sre_control import DecoupledControlLoop

fast = WeightedConvexCombiner([SignalSpec("p99"), SignalSpec("rps")], query_dim=2)
slow = WeightedConvexCombiner([SignalSpec("budget_trend"), SignalSpec("forecast")], query_dim=2)
loop = DecoupledControlLoop(fast, slow, slow_period=60, alpha=0.3)

for tick in range(N):
    action, info = loop.step(fast_q, fast_vals, slow_q, slow_vals)
    # 两条回路的权重、输出分开可见
    prom_push("sre.fast_weights", info["fast_weights"])
    prom_push("sre.slow_weights", info["slow_weights"])
```

---

<a id="hier"></a>
## 5. Primitive 4 · 层级控制 `HierarchicalBlockController`

### 机制
论文的 Block Attention Residuals：`O(L²)` → `O((L/B)² + L)`。
在 SRE 里对应：
- **Block 内部 = 区域 / 单元内的本地控制器**（AZ-east 的 autoscaler、某个 Kubernetes cluster 的限流器）。
- **Block 之间 = 全局控制器**（把 east / west / asia 三个区域的动作再融合成一个全局 `replica_delta`）。

每个区域 `b` 暴露一个 `block_key`（区域特征向量，例如 [cost, rtt_to_user, reliability]）；
全局控制器用自己的 query 对这些 key 做注意力，得到区域级的权重。

### 为什么值得做层级
平铺：每新增一个信号就要对所有层级跑 `O(M * L)` 的计算。
层级：本地只管本地，全局只关心本地的"动作摘要"——数据量从 `O(M * L)` 降到 `O(L) + O(B)`。

### 典型场景
- **跨区域扩缩容**：美东刚过早高峰，美西刚进早高峰。平铺控制器可能因为"平均负载还行"而不作为；层级控制器本地已经感知到热度差并本地扩容，全局再决定是否跨区域漂移流量。
- **多租户限流**：每个租户一个本地 combiner；全局 combiner 只看"每个租户此刻多饿"。

### 落地模板

```python
from attention_residuals.sre_control import BlockSpec, HierarchicalBlockController

east = BlockSpec("east", local_combiner_east, block_key=np.array([cost_e, rtt_e, rel_e]))
west = BlockSpec("west", local_combiner_west, block_key=np.array([cost_w, rtt_w, rel_w]))
ctrl = HierarchicalBlockController([east, west], global_query_dim=3)

action, info = ctrl.step(per_block_queries, per_block_values, global_query)
```

### 「2 选 1」强校验
论文 §5 末段指出：Block 内部的经典残差和 Block 间的 AttnRes 同时保留属于冗余。
在 SRE 里完全同理——**本地控制器已经扩了容**，如果全局控制器再无条件加一次，就是双重补偿。
`HierarchicalBlockController` 的默认行为：全局动作 = 本地动作的凸组合，不叠加；要想叠加必须显式打开 `allow_inner_residual`，并在 code review 里单独讨论。

---

<a id="gate"></a>
## 6. Primitive 5 · 预算门控 `BudgetGate`

### 机制
论文的 `LayerSkipGate`：每层一个可学习门 `g_l = σ(w_l)`。推理期 `g_l < τ` 直接短路。
在 SRE 里直接挪用，但要加一条**群体预算下限**：

```
Σ_i g_i ≥ budget_floor · N
```

不允许一次性把所有 gate 全部关掉——否则系统整体宕机。

### 典型场景
- **特性发布的灰度门**：100 个灰度标志各自有 `g_i`，但任意时刻至少 50% 打开。
- **故障注入**：chaos engineering 里允许关一部分实例，但要保证至少一半实例在线。
- **流量调度**：每条路由有一个 gate，总 gate ≥ 某个阈值保证总运力不低于 SLA。

### 落地模板

```python
from attention_residuals.sre_control import BudgetGate

gate = BudgetGate(n_gates=100, budget_floor=0.5)

# 每次训练 / 评估 / 告警后更新 logits
gate.update_logits(feedback_delta)
active = gate.gates() > 0.5
```

---

<a id="reg"></a>
## 7. Primitive 6 · 必然关注注册表 `MustAttendRegistry`

### 机制
把"不允许被忽略"的信号集中注册；所有 combiner 从这里取 `SignalSpec`，自动把 floor 带上。
这条是 §5.2 "信息传递的确定性保障"最直白的工程实现。

### 典型场景
- 错误预算烧穿告警：`floor=0.3`
- 安全/合规告警：`floor=0.2`
- P0 SLO 违规：`floor=0.5`

这样即便 ML 模型或运维人员在 query 侧"没看到这些信号"，最终融合动作里这些信号仍然占据一个硬性最低比重。

### 落地模板

```python
reg = MustAttendRegistry()
reg.register("error_budget", 0.30)
reg.register("security", 0.20)

signals = [
    SignalSpec("p99"),
    reg.spec("error_budget"),         # floor=0.30 自动带上
    reg.spec("security"),             # floor=0.20
    SignalSpec("cost", ceiling=0.3),  # 成本最多 30%
]
combiner = WeightedConvexCombiner(signals, query_dim=4)
```

注意 `Σ floor ≤ 1` 是硬性前置条件；注册表的 `total_floor()` 会帮你在部署前检查。

---

## 8. 端到端 · 分层自动扩缩容 Demo

完整流程（见 [`demo_sre_autoscaler.py`](../examples/demo_sre_autoscaler.py)）：

```
MustAttendRegistry                       # 把 error_budget 钉住 floor=0.25
     │
     ▼
WeightedConvexCombiner × 2               # 每个区域一个本地 combiner
     │       │
  east  ·  west
     └───┬───┘
         ▼
HierarchicalBlockController              # 跨区域融合
         │
         ▼
DecoupledControlLoop                     # fast(秒级) + slow(10 秒级)
         │
         ▼
BudgetGate                               # 群体下限 ≥ 50%
         │
         ▼
AuditTrail                               # JSON Lines 落盘
```

实际跑出来的现象（30 tick，tick 15 时错误预算烧穿）：

- 每个本地 combiner 的 `error_budget` 权重始终 ≥ 0.25（floor 生效）；
- tick ≥ 15 后，`slo_violation` 和 `error_budget` 的综合权重上升，`cost` 信号被主动稀释；
- 全局权重随 east/west 的 heat 比例平滑漂移（0.46 ⇄ 0.54）；
- `BudgetGate` 即使 logits 全为负，`gates().sum()` 仍不低于 `0.5 × N`；
- 60 条审计记录全部带权重向量，可直接回放。

---

## 9. 复用路线图（建议）

| 阶段 | 动作 | 预期收益 |
| --- | --- | --- |
| **Phase 0** | 把现有 SRE 控制器的"if/else + 阈值"替换成 `WeightedConvexCombiner` + `AuditTrail`。 | 决策可审计；信号权重可离线分析。 |
| **Phase 1** | 给关键业务信号登记 `MustAttendRegistry`；把"必须被考虑"的硬约束从代码注释变成运行时保证。 | 合规 / SLA 硬红线。 |
| **Phase 2** | 把"秒级尖峰防护"和"小时级容量规划"拆成 `DecoupledControlLoop`。 | 变更隔离、故障隔离；slow-loop 可独立发版。 |
| **Phase 3** | 多区域或多 cluster 引入 `HierarchicalBlockController`。 | 数据规模从 O(M·L) 降到 O(L)+O(B)；本地自治。 |
| **Phase 4** | 灰度 / chaos 引入 `BudgetGate`。 | 群体预算约束不会被单点踩空。 |
| **Phase 5** | 在 audit trail 上训练一个"决策异常检测器"——反过来喂回 bias / temperature。 | 控制面自举闭环，接近论文的"AttnRes 权重自学习"。 |

---

## 10. 与传统 SRE 原语的对照

| 传统做法 | 新做法 | 差异 |
| --- | --- | --- |
| 阈值触发（if P99>300ms then scale up） | WeightedConvexCombiner | 多信号、可审计、权重可学习、硬 floor |
| 固定 PID 环 | DecoupledControlLoop | 快慢解耦、参数独立、故障隔离 |
| 粗暴的"关所有灰度" | BudgetGate | 群体预算下限，避免一键全关 |
| 中心化大表 / 大 query | HierarchicalBlockController | 本地自治 + 全局融合，扩展性 O((L/B)²) |
| 散落在代码里的"必须监控" | MustAttendRegistry | 集中注册、类型安全、运行时保证 |
| 控制器日志 | AuditTrail + weights | 每次决策都有量化权重，可做反常检测 |

---

## 11. 复利点（为什么值得投入）

1. **统一的控制平面语义**：扩缩容、限流、熔断、流量切换、灰度发布统一用 `WeightedConvexCombiner`，接口一致，可组合。
2. **决策异常检测变得可行**：audit trail 里 weights 的分布天然适合做无监督异常检测。
3. **ML 可选而非必须**：`W_K / bias / temperature` 都可以手工配置，也可以用强化学习训练；工程团队先手工跑起来，ML 团队再接入，不阻塞。
4. **领域不绑定**：这套原语对"网络调度、数据库限流、风控决策、广告出价"同样适用——抽象层次足够低。
5. **可解释 AI**：当 ML 模型介入控制平面时，`MustAttendRegistry` 的 floor + `AuditTrail` 的 weights 就是最直接的可解释性保证。
