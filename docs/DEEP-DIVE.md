# Deep Dive · 数学底座 / 闭环自适应 / 工业级安全

> 这份文档把前两轮 Playbook 里"直觉上对"的东西补齐数学证明，并把整套控制器从**开环**升级到**闭环**，再套一层**工业级安全外壳**。
> 核心观点：Attention Residuals 里那条 softmax 既是"归一化技巧"，更是一个**最大熵解 + 镜像下降一步 + 在线学习基元**的三合一结构。理解这一点，才能把它放心地塞进生产。

配套代码：
- [`attention_residuals/sre_control.py`](../attention_residuals/sre_control.py) — 开环原语
- [`attention_residuals/sre_adaptive.py`](../attention_residuals/sre_adaptive.py) — Hedge / 后悔界学习器 + AdaptiveCombiner
- [`attention_residuals/sre_safety.py`](../attention_residuals/sre_safety.py) — 安全外壳 / 影子模式 / 反事实 / 漂移检测
- [`examples/demo_sre_adaptive_safety.py`](../examples/demo_sre_adaptive_safety.py) — 三层联动 Demo

---

## 1. 数学底座：为什么 softmax + Σ=1 是"对的"

### 1.1 最大熵推导

给定 `n` 个信号，每个有一个得分 `s_k = q · K_k / T + bias_k`，我们要挑一个概率分布 `a ∈ Δ^{n-1}`（单纯形）来加权。
"应该选哪一个 a"这个问题，在信息论下有一个唯一正解：

> **在固定期望得分 `⟨a, s⟩` 的约束下，熵 `H(a)` 最大化的那一个**。

形式化：
```
max     H(a) = -Σ_k a_k log a_k
s.t.    ⟨a, s⟩ = c          (给定期望得分)
        Σ_k a_k = 1,  a_k ≥ 0
```

用 Lagrange 乘子法（β 对应 `⟨a, s⟩=c` 的约束，λ 对应 `Σ=1`），一阶条件直接给出：

```
-log a_k - 1 - β s_k - λ = 0
⇒ a_k ∝ exp(β s_k)
⇒ a_k = exp(β s_k) / Σ_j exp(β s_j)          ← 这就是 softmax
```

`β` 对应 temperature 的倒数。**论文里的 softmax 不是"随手选的归一化"，是信息论最小承诺原则下的唯一解**。

### 1.2 "Σa=1 是硬约束" vs "当作损失项"

工程上经常见到这种提议："何必 softmax？加个 `λ·(Σa-1)²` 当正则不就行了？"
答案：不行。从 KKT 条件看，把 `Σ=1` 降级成软约束意味着：
- 在非平稳输入下，某些样本会出现 `Σa ≠ 1`（超发或欠发），预算守恒被破坏；
- 工程上表现为"周期性出现异常大/小的控制动作"，且难以复现。

Attention Residuals 论文 §5.1 为什么强调"必须是 softmax"，这条数学约束是根因。

### 1.3 为什么还要加 floor/ceiling？

最大熵解假设所有信号地位平等。但在 SRE 场景里，某些信号是**绝对不能被忽略**的（错误预算、安全告警）。
这就要求对最大熵解再加一组上下界约束：

```
floor_k ≤ a_k ≤ ceiling_k
```

加了这组约束以后，最大熵问题不再有闭式解，必须用投影算法求。这就是 §2 要讲的东西。

### 1.4 投影到受限单纯形：收敛性

我们要求解：

```
min  ‖a - a0‖²
s.t. Σ_k a_k = 1,  floor_k ≤ a_k ≤ ceiling_k
```

其中 `a0` 是 softmax 给出的无约束解。

可行域 `F = {a : Σa=1, floor ≤ a ≤ ceiling}` 是一个**紧致凸多面体**。
我们的迭代算法：

```
repeat:
  clip:          a ← min(max(a, floor), ceiling)
  redistribute:  a ← a + residual · (room / Σ room)
until |Σa - 1| < ε
```

**收敛性**：每次 clip 要么保持可行性，要么**严格拉近与可行域的距离**；redistribute 保证 `Σa=1` 并严格减小残差范数。两个操作都是对可行域的**非扩张投影**（Lipschitz 常数 ≤ 1），因此序列单调收敛到 `F` 上的唯一点。
对可行输入（`Σ floor ≤ 1 ≤ Σ ceiling`），实测常常 3 次迭代内终止（见测试 `test_simplex_projection_boundary_cases`）。

**不可行时的行为**：如果 `Σ floor > 1`，没有任何 `a` 能同时满足。
我们在 `WeightedConvexCombiner.__init__` 就拒绝这种配置——**构造期失败好于运行期失败**。

---

## 2. 闭环自适应：从开环控制器到"看结果学习"

### 2.1 为什么现有的 `WeightedConvexCombiner` 还不够

它是一个**开环**控制器：输入 query + values，输出 action。没有任何机制让它"看到后果"。
真实 SRE 控制器必须闭环：如果信号 k 给的建议让排队变长了，下次应该减小它的影响力。

### 2.2 Hedge / Multiplicative Weights Update

经典在线学习算法（Freund & Schapire 1997）。每步：

```
w_i ← w_i · exp(-η · loss_i)
a_i = w_i / Σ_j w_j
```

等价于在**单纯形 + 负熵几何**下走一步镜像下降（Mirror Descent）。
Softmax 恰好是"log-weights 空间里的单位化"，所以 Hedge 的状态就是 `log_w`，可以直接当作 `bias` 喂给 `WeightedConvexCombiner`——两条线无缝对接。

### 2.3 后悔界定理

**定理**（Hedge regret bound）：若每步损失 `loss_{t,k} ∈ [0,1]`，且学习率选为 `η = √(ln n / T)`：

```
Σ_{t=1..T} E[loss_t]  -  min_{k}  Σ_{t=1..T} loss_{t,k}   ≤   √(T · ln n)
```

翻译成 SRE 语言：
> **无论未来的 T 步里"事后看最该听谁的"是哪一个信号，我们的控制器都至多比它多累积 `O(√(T log n))` 的代价。**

关键在于：
- 不需要先知道 T；可以用 "doubling trick" 或保守的 `η`。
- 信号数 n 只以 `√log` 的形式进入——**增加信号几乎不惩罚**。
- 结果对**最坏情况**敌手都成立（非随机、不假设平稳性）。

### 2.4 `AdaptiveCombiner` 的工程形态

```python
class AdaptiveCombiner:
    def step(self, query, values, observed_losses=None):
        if observed_losses is not None:
            self.learner.update(observed_losses)    # (1) 消化上一轮反馈
        for spec, lg in zip(self.combiner.signals, self.learner.logits()):
            spec.bias = float(lg)                   # (2) 学到的偏好 → bias
        return self.combiner.combine(query, values) # (3) 原控制器输出
```

精妙之处：**硬约束（floor/ceiling/Σ=1）从来没被学习器动过**。学习器只能"倾斜信念"，不能打破安全包络。

### 2.5 Demo 实测的两个重要现象

在 `demo_sre_adaptive_safety.py` 里（regime 每 40 tick 切换）：

| 现象 | 直觉 | 工程含义 |
| --- | --- | --- |
| tick 10 学习器已到 95% p99 | `O(√T log n)` 带来的快速收敛 | 平稳期内，闭环几乎免费 |
| tick 40 换 regime 后仍固执 p99 | 累积损失把 p99 锁死 | 需要"忘记"机制：衰减权重、doubling trick 或重启 |
| 学习器 → 0 的信号，combiner 仍 ≥ floor | floor 在学习器之外生效 | 安全约束从不是可学习的 |

**策略建议**：在生产里把 Hedge 加上指数遗忘（`w_i ← α w_i + (1-α)·reset`）或者滑动窗口，避免被历史锁死。

---

## 3. 工业级安全层：能不能上生产的四把锁

### 3.1 动作空间安全包络（`SafetyEnvelope`）

权重空间的 floor/ceiling 只能保证"信号权重合理"，但合成出的最终**动作**仍可能超标。例如：
- 所有信号都投票"+3 个副本"，合成后真的扩 +3，但本系统每 tick 最多只能变 ±2。

因此再加一层动作空间约束：

```
a_final = clip(a_raw, low, high)                              # 绝对边界
a_final = clip(a_final, last_a - max_delta, last_a + max_delta)  # 变化率
```

**这层与 §1 的权重投影是互补的**：权重投影保证"想做的决策合理"，动作包络保证"实际下发的命令安全"。
违反计数器暴露给 Prometheus，便于触发告警。

### 3.2 影子模式（`ShadowRunner`）

新控制器上线前必须能安全验证。`ShadowRunner`：
- 每 tick 并行调用 `baseline_fn` 和 `shadow_fn`；
- **只下发 baseline 的动作**；
- 记录两者差异的 L1/L2/max 散度；
- 提供分位数统计。

上线决策应基于三件事：
1. **散度分布**：`p95` 稳定在合理范围内；
2. **反事实代价**：把 shadow 的假设动作回放到历史数据上估出的 counterfactual loss；
3. **对抗样本覆盖**：已知长尾故障上 shadow 的表现。

本模块只提供**可观测性**，**决策权始终在人**。这是有意的——自动化的上线决策本身就是一个新的风险面。

### 3.3 反事实解释（`CounterfactualExplainer`）

> P0 复盘最常问的问题：**"控制器为什么在那一刻扩了 +3 个副本？"**

对 `WeightedConvexCombiner` 这个问题有一个**精确答案**：依次把每个信号的 bias 拉到 `-∞`，重新算一次 action，看差多少。

为什么这是精确的？因为：
- 把信号 k 的 bias 压到极负，softmax 会让 `a_k → 0`；
- 其余信号的权重按**比例放大**（不是重新分配，是放缩）——这正是"marginal contribution"的自然定义；
- 整个过程保持 `Σa=1`，因此"权重平移"向量的和严格为 0（这条在单测里验证过）。

对比主流的 Shapley value / LIME：本方法**不需要采样、没有随机性、O(n)**。
代价是它只对线性-softmax 结构成立，不适合非凸决策引擎。

### 3.4 权重漂移检测（`WeightDriftDetector`）

即便每个原语都工作正常，控制器整体的"偏好"也可能在**慢漂移**：
- 错误预算整体变紧，`error_budget` 信号长期高权重；
- 某个 upstream 业务变更，使 `p99` 的信息量下降；
- 学习器被长尾 regime 锁死。

漂移检测用两条 EWMA（fast / slow）跟踪权重分布：

```
fast ← (1 - α_f) fast + α_f · a_t          # 短时
slow ← (1 - α_s) slow + α_s · a_t          # 长时
alert when KL(fast ‖ slow) > threshold
```

**为什么用 KL 而不用 L2**：权重是概率分布；KL 是概率空间的自然度量，对低概率尾部敏感（一个重要信号从 0.01 跳到 0.0001 在 L2 上几乎没差，在 KL 上差 2 倍以上）。
阈值默认 0.25 是一个保守的起点——生产环境建议按"正常运行期的 KL 99th 分位数的 3 倍"来定。

---

## 4. 三层组合：从 Attention Residual 到生产级 SRE 控制面

把三层叠起来，一次完整的控制 tick 就是：

```
┌────────────────────────────────────┐
│ 1. sre_control   (数学底座)         │
│   ├─ MustAttendRegistry  → floor    │
│   ├─ WeightedConvexCombiner         │ softmax + 投影, Σa=1 硬保证
│   └─ AuditTrail                     │
└───────────────┬────────────────────┘
                ▼
┌────────────────────────────────────┐
│ 2. sre_adaptive  (闭环学习)         │
│   ├─ HedgeRegretLearner  → bias     │ O(√(T log n)) 后悔界
│   └─ AdaptiveCombiner               │ learner 只能倾斜，不能突破硬约束
└───────────────┬────────────────────┘
                ▼
┌────────────────────────────────────┐
│ 3. sre_safety   (工业级外壳)         │
│   ├─ SafetyEnvelope   动作空间钳位  │
│   ├─ ShadowRunner     双轨对照      │
│   ├─ CounterfactualExplainer       │ 可解释 / 复盘
│   └─ WeightDriftDetector            │ KL 漂移告警
└────────────────────────────────────┘
```

每一层都**只能收紧**下一层的决策——这是安全工程的黄金法则："失败时向保守方向倒"。

---

## 5. 下一步能做什么

| 方向 | 思路 | 预期收益 |
| --- | --- | --- |
| **指数遗忘 Hedge** | 让学习器在新 regime 下快速摆脱历史 | 解决 demo 里 40→80 tick 的"固执 p99"问题 |
| **EXP3 变体** | 当我们只观察所选动作的结果（bandit 场景）而非所有信号的 counterfactual loss 时 | 更贴近真实 SRE：你只看到"这个决定的后果"，不知道"别的决定会怎样" |
| **Model-Based 补充** | 用一个小模型预测"如果下发 Δ，下一 tick 指标会怎样" | 减少安全包络被触发的次数；对 chaos-engineering 友好 |
| **层级漂移检测** | 给 `HierarchicalBlockController` 的每个 block 单独跑漂移检测器 | 比全局 KL 更早定位问题到具体 region/cluster |
| **学习到的安全包络** | 从历史 audit trail 学出"何时 +2 会撞限"，自动收紧 `max_delta` | 控制面自举：包络不再纯人工 |
| **对抗性信号测试** | 用已知对抗样本（flash crash、cascading failure）做 shadow 对照 | 上线前发现 "loss=0 但后果灾难"的 Goodhart 式欺骗 |

---

## 6. 参考

- Freund, Y., & Schapire, R. E. (1997). *A decision-theoretic generalization of on-line learning and an application to boosting.*
- Shalev-Shwartz, S. (2011). *Online Learning and Online Convex Optimization.* — 第 2 章 Hedge/OGD 的完整证明
- Jaynes, E. T. (1957). *Information Theory and Statistical Mechanics.* — 最大熵原理原始论文
- Ames, A. D., et al. (2019). *Control Barrier Functions: Theory and Applications.* — 与 `SafetyEnvelope` 思路一致的控制理论框架
- Ribeiro, M. T., et al. (2016). *"Why Should I Trust You?" Explaining the Predictions of Any Classifier.* (LIME) — 反事实解释的近似版本
- Gretton, A., et al. (2012). *A Kernel Two-Sample Test.* — 权重漂移检测的理论参考
