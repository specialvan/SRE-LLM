# Equations → SRE Primitives · Deep Dive (Round 4)

> 这一轮把每个方程里之前被"一带而过"的标量细节都吃透，每个都抽出一条可直接进入生产控制面的工程能力。
> 所以有些事情，不把数学细节钉死，就永远只停在"大概知道"。

配套代码：
- [`attention_residuals/sre_math.py`](../attention_residuals/sre_math.py) — 七条原语的纯 numpy 实现
- [`examples/demo_sre_math_primitives.py`](../examples/demo_sre_math_primitives.py) — 三视角 + 学习 + 稳定监控联动

---

## 0. 地图

| # | 方程（论文出处） | 数学内核 | 抽出的 SRE 原语 |
| --- | --- | --- | --- |
| 1 | `(q·K)/√d`  (§05)        | 尺度不变性 / 随机投影                                | `ScaleInvariantNormalizer` |
| 2 | `softmax(·/τ)` (§05)     | 温度 = Legendre 对偶 / 探索↔利用旋钮                 | `TemperatureScheduler` |
| 3 | `concat_h · W_O` (§08)   | 子空间正交分解 + 凸组合的凸组合                         | `ViewSpec` / `MultiViewCombiner` |
| 4 | `w ← w·exp(-η·loss)` (§17) | Hedge = FTRL(negative entropy) = 镜像下降一步      | `FTRLLearner` |
| 5 | `I + ∂F/∂x` 稳定性 (§02)  | 残差雅可比 / 收缩映射                                | `JacobianContractionMonitor` |
| 6 | `∂L/∂x_l = …` 梯度回流 (§02) | BPTT 的线性简化 / 时间信用分配                       | `TemporalCreditAssigner` |
| 7 | `KL(p‖q)` 漂移 (§18)      | 信息几何 vs **Wasserstein** 度量几何                | `WassersteinDriftDetector` |

下面七节分别吃透每个方程、证明关键性质、然后给出它在 SRE 控制器里干什么活。

---

## 1. `(q·K) / √d` — 尺度不变性

### 方程
Scaled dot-product attention：

```
score_k = (q · K_k) / √d_k ,      d_k = feature dim
```

### 为什么除以 `√d`？
`q·K` 是 `d` 个独立随机积的和。如果每个分量方差为 1：

```
Var[q·K] = d,     因此  Std[q·K] = √d
```

不除以 `√d`，**softmax 的锋利度会随维度指数性变化**：高维度下 softmax 退化成 one-hot，低维度下退化成均匀分布——同一段代码在不同规模上行为截然不同。
除以 `√d` 正好把 score 的标准差拉回 O(1)，让 softmax 曲线的锐度对维度不敏感。
**这是一条"尺度不变性"工程原则**。

### 严格论述
令 `X_1,...,X_d` 是均值 0 方差 1 的独立变量，`Y_d = (1/√d) Σ X_i`。则：

```
E[Y_d] = 0,  Var[Y_d] = 1,  ∀ d
```

换句话说，`(q·K)/√d` 给出的 score 分布在任意 `d` 下都有 O(1) 尺度。
**只要让信号的尺度保持 O(1)，softmax 就能在跨维度、跨时间上表现一致**。

### SRE 映射：`ScaleInvariantNormalizer`

SRE 里的信号天然跨量级：P99 在毫秒级，RPS 在千级，错误率在 `[0, 1]`。
如果不把它们拉回同一尺度就塞进 softmax，**量纲大的信号永远赢**，跟它的实际重要性无关。

**在线 Welford-风格的 EWMA z-score** 就是这个问题的工程答案：

```
mean_t = (1-α)·mean_{t-1} + α·x_t
var_t  = (1-α)·(var_{t-1} + α·(x_t - mean_{t-1})²)
z_t    = (x_t - mean_t) / √max(var_t, ε)
```

- **`warmup`**：前 K 样本只累积统计，不输出 z-score——避免冷启动阶段的噪声放大；
- **`eps`**：防止方差塌缩到 0 时除零（常数流一定会遇到）；
- **`α`**：决定追踪速度，α=0.05 对应约 20 步的有效窗。

测试 `test_scale_normalizer_zero_mean_unit_std_after_convergence` 用三维真值验证：3000 步后 z-score 均值 ≤ 0.2、标准差 ∈ [0.65, 1.35]，与理论一致。

### 为什么这是复利点
- **只需 O(1) 内存 + O(n) 操作**：可塞进任何热路径；
- **完全领域无关**：风控、广告、推荐场景都能套；
- **解决一个现实而不起眼的坑**：团队间信号融合时最常见的 bug 就是"某个信号量级碾压别的"，这条原语从根上拔掉。

---

## 2. `softmax(·/τ)` — 温度作为 Legendre 对偶

### 方程
```
a_k(τ) = exp(s_k/τ) / Σ_j exp(s_j/τ)
```

### 两个极限

```
τ → 0⁺ :  a → 1_{argmax}           (纯利用)
τ → ∞  :  a → 1/n (均匀)            (纯探索)
```

### Legendre 对偶视角

Softmax 是 log-sum-exp 的梯度（凸共轭）：

```
φ(s) = τ · log Σ_k exp(s_k/τ)
∇φ(s) = softmax(s/τ)
```

这意味着 softmax 天然是一个**在负熵正则下的 argmax**：

```
softmax(s/τ) = argmax_{a ∈ Δ} { ⟨a, s⟩  +  τ · H(a) }
```

`τ` 就是负熵正则的强度。
- τ 大：惩罚小熵 → 鼓励均匀 → 探索；
- τ 小：惩罚弱 → 分布可以很尖 → 利用。

这直接给出了**"从探索到利用"的调参旋钮**，不需要额外的机制。

### 收敛意义上的 τ 退火

Hedge 的后悔界定理要求 `η = √(ln n / T)`——等价于 τ 随时间退火为 `τ_t ∝ 1/√(1+t)`。
换句话说，**"√t 退火"不是工程启发式，是后悔界证明里的精确速率**。

### SRE 映射：`TemperatureScheduler`

四种内置策略：

| kind | 公式 | 用途 |
| --- | --- | --- |
| `constant` | `τ = τ0` | Baseline / 稳定生产 |
| `sqrt` | `τ_t = τ0 / √(1+t)` | 匹配 Hedge 最优退火 |
| `linear` | `τ = τ0 + (τ_min-τ0)·min(1, t/T)` | 简单可预测，易向运维解释 |
| `exp` | `τ_t = τ0 · 0.5^(t/half_life)` | 强烈偏向快速利用 |

### 为什么这是复利点
- **解决"冷启动就定死 bias"的老问题**：新上线的控制器天然需要一段探索期；
- **与 Hedge 后悔界天然对齐**：不用调参；
- **领域无关**：流量切换、A/B 测试、灰度发布、广告出价全能套。

---

## 3. `concat_h · W_O` — 子空间正交分解

### 方程
多头注意力的输出：

```
AttnRes^(h)_l = Σ_k a^(h)_{l,k} · (x_k · W_V^(h))
AttnRes_l     = concat_h(AttnRes^(h)_l) · W_O
```

### 代数含义
每个头把 `d`-维特征空间投影到 `d/H` 维子空间，在子空间内独立做 softmax + 加权求和，最后 `W_O` 把 `H` 个子空间的结果混合回 `d` 维。
关键性质：**每个头里 `Σ_k a^(h)_{l,k} = 1` 独立成立**——不是头之间共享权重，而是每头各有一个概率单纯形。

### 为什么分头而不是单头更大
单头大注意力参数等价于 `H` 个小注意力 + 强约束（跨头耦合）。分头等价于**明确地假设任务可分解为 `H` 个独立子任务**——如果假设成立，优化会快得多；如果不成立，W_O 会学出投影让有效头数重新膨胀。

### SRE 映射：`ViewSpec` + `MultiViewCombiner`

每一个 view 对应一个"视角"（latency / reliability / cost / security），**各自维护一个 `WeightedConvexCombiner`**，每个视角内部 `Σa=1` 独立成立。
最外层用静态凸组合合并：

```
y = Σ_h μ_h · AttnRes^(h),   Σ_h μ_h = 1
```

这与论文 §08 多头结构同构，只是 `μ_h` 用静态 view weight 而非学出来的 `W_O`——因为 SRE 运维人员通常希望这一层**完全可解释、不学习**。

### 为什么这是复利点
- **强制解耦**：延迟的 softmax 不会污染成本的 softmax；
- **每个视角内 Σa=1 单独成立**：信息守恒定理分而治之；
- **允许视角之间信号重叠**：`error_rate` 可以同时出现在 reliability 和 latency 视角；
- **扩展零成本**：新增一个 "security" 视角等于新增一个 combiner，不影响其它视角的后悔界证明。

---

## 4. `w ← w · exp(-η · loss)` — FTRL 家族

### 方程
Hedge 更新：

```
w_{i,t+1} = w_{i,t} · exp(-η · loss_{i,t})
a_{t+1}   = w_{t+1} / Σ_j w_{j,t+1}
```

### 更深的数学身份：FTRL

**Follow-The-Regularized-Leader** 框架：

```
x_{t+1} = argmin_{x ∈ Δ} [ ⟨Σ_{s≤t} g_s, x⟩ + (1/η) · Ψ(x) ]
```

不同的 `Ψ`（正则子）给出不同的算法：

| Ψ(x) | 算法名 | 几何 | 后悔界 |
| --- | --- | --- | --- |
| `Σ x_i log x_i` (negative entropy) | **Hedge** | 单纯形上的信息几何 | `√(T log n)` |
| `½‖x‖²` | **OGD(simplex)** | 欧几里得几何 | `√T` |
| `½ xᵀ A x` | 自适应预条件 AdaGrad | Mahalanobis 几何 | 问题相关 |

**Hedge 就是 FTRL 在负熵正则下的特解**。这意味着我们可以用完全一致的代码框架实现多种在线学习算法，只要换 `Ψ`。

### 几何差异的工程含义

- **Entropy**：分布可以非常尖锐（极端 one-hot），对坏信号很"残忍"，短期收敛快；
- **L2**：更新是简单加减，分布在边界附近更平滑，调参余地大，对异常值更鲁棒。

生产上的选择建议：
- 决策离散空间小（≤ 10 个信号）+ 环境平稳 → Hedge；
- 决策空间大或信号噪声大 → L2 更稳。

### SRE 映射：`FTRLLearner(regularizer=...)`

两种正则共用一套接口：

```python
L = FTRLLearner(n_signals=3, eta=0.3, regularizer="entropy")  # == Hedge
L = FTRLLearner(n_signals=3, eta=0.3, regularizer="l2")       # == OGD(simplex)
L.update(loss_vec)
weights = L.weights()                                          # 恒在 Δ^{n-1}
```

`test_ftrl_entropy_matches_hedge_exactly` 验证 entropy FTRL 与 `HedgeRegretLearner` 数值一致。

### 欧几里得单纯形投影算法

`l2` 分支用到一个独立的工程细节：把任意向量 `y ∈ R^n` 投到概率单纯形上。
我们用 Wang & Carreira-Perpinán 2013 的 O(n log n) 排序算法：

```
sort y descending → u
cumsum(u)          → cssv
rho = max{ i : u_i - (cssv_i - 1) / i > 0 }
theta = (cssv_rho - 1) / rho
x = max(y - theta, 0)
```

这是 **Euclidean 投影**，和 `sre_control._project_to_simplex_with_bounds` 的"求和守恒重分配"是两个不同目标，所以独立实现。
测试 `test_ftrl_l2_stays_on_simplex` 保证每一步都 `Σw = 1` 且 `w ≥ 0`。

### 为什么这是复利点
- **一套代码，两种几何**：生产可 A/B 两种学习动态；
- **统一后悔分析**：两个正则都有闭式后悔界；
- **模块化**：未来可插入自适应预条件、镜像下降等新正则，不改下游。

---

## 5. `I + ∂F/∂x` — 残差雅可比 / 收缩映射

### 方程
残差递推的一阶线性化：

```
x_{l+1} = x_l + F(x_l)
⇒ ∂x_{l+1}/∂x_l = I + ∂F/∂x_l
```

### 稳定性判据
一阶近似下，递推是**收缩映射**当且仅当：

```
ρ(I + ∂F/∂x) < 1         或更保守地   ‖∂F/∂x‖ < 1
```

这就是深度残差网络训练稳定的本质——identity 项让雅可比的谱半径永远不会坍塌到 0（梯度消失）也不会爆炸到 ∞（梯度爆炸）**除非 F 本身的导数不合理**。

### SRE 里对应的稳定性
SRE 控制环 `state ← state + F(state, action)` 也是残差结构。如果 `F` 的实效增益 > 1，一个小扰动会被**正反馈放大**——最典型的就是：
- 排队变长 → 控制器扩容 → 下游瓶颈暴露 → 排队进一步变长；
- 错误率升 → 限流打开 → 上游重试 → 错误率更高。

### 工程近似：在线最小二乘估 gain

实际 `F` 是黑盒，我们测不到真雅可比，但可以从 `(action_t, Δstate_t)` 的时间序列估**有效标量增益**：

```
gain ≈  Σ action · Δstate  /  Σ action²       (scalar OLS over a rolling window)
```

若 `|gain| > 1` 并持续多个窗口 → 系统处于正反馈状态，**立即告警，人工介入**。

### SRE 映射：`JacobianContractionMonitor`

```python
mon = JacobianContractionMonitor(window=64, min_samples=16, threshold=1.0)
for t in ticks:
    action_t = controller.decide(...)
    ...
    mon.observe(action_t, delta_state_t, step=t)
    if mon.alerts():
        alert_ops(mon.alerts()[-1])
```

### 为什么这是复利点
- **无需模型**：不要求知道系统动力学；
- **无需微分**：纯 O(window) 的 OLS；
- **提前于 SLA 告警**：通常 10–20 tick 内就能观察到 |gain| 异常，比 P99 超阈值告警更早；
- **直接落到控制理论的 CBF 框架**：可以接入 §18 的 `SafetyEnvelope` 自动收紧。

---

## 6. `∂L/∂x_l = ∂L/∂x_{l+1} · (I + ∂F/∂x_l)` — 时间信用分配

### 方程
损失对第 `l` 层的梯度：

```
∂L/∂x_l = ∂L/∂x_{l+1} · (I + ∂F/∂x_l)
        = ∂L/∂x_L · Π_{m=l..L-1} (I + ∂F/∂x_m)
```

### 两个含义

**直接**：identity 项保证梯度在反传中至少保留 `∂L/∂x_L`，不会完全消失。
**更深的**：每一层都对最终损失**贡献一个乘性因子**。哪一层导致了最后的失败？看它的因子贡献多大。
这在时间维上就是 **Back-Propagation-Through-Time (BPTT)**——追溯"之前的哪个决策导致了眼下的故障"。

### SRE 里的现实需求
事故复盘最常问的问题：
> 凌晨 3 点系统挂了，可是决策器早在凌晨 1 点就开始了错误扩容。**那 2 小时里哪些信号应该为结果负责？**

### 线性简化

SRE 控制器（至少 `WeightedConvexCombiner`）是**线性 in action**：

```
action_t = Σ_k a_{t,k} · v_{t,k}
```

因此一次决策对结果的贡献**与权重成正比**。加一条时间衰减 `γ^age`，就得到：

```
blame(signal=k, tick=t | incident at T) = a_{t,k} · loss_{t,k} · γ^(T-t)
```

这就是 BPTT 在线性控制器上的简化版——**O(window·n_signals) 纯前向计算**。

### SRE 映射：`TemporalCreditAssigner`

```python
tca = TemporalCreditAssigner(decay=0.9)
for t in ticks:
    tca.record(t, weights=a_t, losses=L_t, signal_names=["p99", ...])

# 事故发生后
top_blamed = tca.attribute(incident_tick=T, window=60, top_k=10)
for e in top_blamed:
    print(e.tick, e.signal_name, e.score)
```

测试 `test_credit_assigner_decay_reduces_old_scores` 精确验证 `γ=0.5, age 0/1/2 → 1, 0.5, 0.25`。

### 为什么这是复利点
- **把 audit trail 从"查日志"升级为"量化归因"**；
- **报告自动生成**：P0 复盘报告的"直接原因 / 促成因素"章节可以由 `attribute()` 直接生成；
- **可反馈给学习器**：把 top-blamed 信号作为负样本，让 `FTRLLearner` 加速惩罚。

---

## 7. KL vs Wasserstein — 信息几何 vs 度量几何

### 方程
两种分布距离：

```
KL(p ‖ q) = Σ_i p_i · log(p_i / q_i)            # 信息几何
W₁(p, q)  = Σ_i | cumsum(p)_i - cumsum(q)_i |   # Wasserstein-1 on a line
```

### 本质差异

| 性质 | KL | Wasserstein-1 |
| --- | --- | --- |
| 对称？ | 否 | 是 |
| 三角不等式？ | 否 | 是（是真正的 metric） |
| q_i = 0 时？ | **发散 ∞** | 有限 |
| 对坐标排序敏感？ | 否 | 是 |
| 计算复杂度（1D） | O(n) | O(n log n)（或有序 O(n)） |

### 为什么两个都要有

- **KL** 放大"应该非零但变零"的尾部——对**必然关注信号消失**敏感；
- **W₁** 处理"质量流动"——对**整体分布的平移**敏感，但对尾部塌缩不至于发散。

```
示例 a₁ = [0.5, 0.3, 0.2]     a₂ = [0.0, 0.5, 0.5]
KL(a₁ ‖ a₂) = ∞     (因为 a₂[0] = 0)
W₁(a₁, a₂) = |0.5 - 0| + |0.8 - 0.5| + |1 - 1|  = 0.8     (有限)
```

如果第一个信号是"error_budget"，这事儿应该响警报还是不应该？答案取决于你在问什么：
- **"这信号被事实性屏蔽了"** → KL 更合适；
- **"偏好整体平移了"** → Wasserstein 更合适；
- **两个都用**，互为旁证，任一触发都告警。

### Wasserstein 的 1D 特殊形态

对 1D 分布，Wasserstein-1 有闭式：

```
W₁(p, q) = ∫ |F_p(x) - F_q(x)| dx
         ≈ Σ_i |cumsum(p)_i - cumsum(q)_i|      (离散化)
```

需要给坐标轴一个"排序"——信号的相对顺序语义上有意义时（例如 `[error_budget, slo, cost]`，从不能退让到可以妥协），这个顺序就是 W₁ 的自然轴。

### SRE 映射：`WassersteinDriftDetector`

```python
det = WassersteinDriftDetector(
    n_signals=3,
    ordering=[2, 0, 1],         # signal priority order
    fast_alpha=0.3, slow_alpha=0.03,
    threshold=0.15,
)
for t in ticks:
    w = combiner.last_weights()
    alert = det.observe(w, step=t)
```

`test_wasserstein_drift_silent_on_stable_stream` 验证稳定流 500 tick 无误报；`test_wasserstein_drift_detects_regime_shift` 验证突变 < 30 tick 内告警。

### 为什么这是复利点
- **KL 与 Wasserstein 互补**：生产上两个并行监控，**任一触发告警**更稳；
- **W₁ 带边界**：最大值 = 轴长度，容易解释给运维（"偏好从最左端漂到最右端"）；
- **1D W₁ 是 O(n log n)** 的闭式，可以塞进热路径。

---

## 8. 总复盘：每条原语的"为什么能复利"

| 原语 | 单点价值 | 组合价值 |
| --- | --- | --- |
| `ScaleInvariantNormalizer` | 解决"量纲碾压"bug | 与任何 combiner 串联都生效 |
| `TemperatureScheduler` | 探索 / 利用的单一旋钮 | 为 FTRL 提供最优 η 退火 |
| `MultiViewCombiner` | 视角解耦 | 每视角可独立接入 `FTRLLearner` |
| `FTRLLearner` | 两种几何一套接口 | 为 `AdaptiveCombiner` 提供可替换的 learner |
| `JacobianContractionMonitor` | 模型无关的稳定性告警 | 可驱动 `SafetyEnvelope.max_delta` 自动收紧 |
| `TemporalCreditAssigner` | 结构化事故归因 | 与 `CounterfactualExplainer` 互补（时间维 vs 信号维） |
| `WassersteinDriftDetector` | 对补数坐标漂移敏感 | 与 `WeightDriftDetector(KL)` 并行监控 |

**组合规则**：
1. 信号先进 `ScaleInvariantNormalizer`；
2. 按视角走 `MultiViewCombiner`；
3. 每视角内 `AdaptiveCombiner` + `FTRLLearner`，温度由 `TemperatureScheduler` 退火；
4. 旁路挂 `JacobianContractionMonitor` 监控系统闭环稳定性；
5. 每次决策记录进 `TemporalCreditAssigner`；
6. 权重流两路并监：`WeightDriftDetector(KL)` 看塌缩，`WassersteinDriftDetector` 看漂移；
7. 动作出口过 `SafetyEnvelope`；
8. 新版控制器先跑 `ShadowRunner`，P0 用 `CounterfactualExplainer` 复盘。

到这里，Attention Residuals 每一个方程里的"不起眼标量"都已经抽成了独立原语，**整套系统已经不再需要"神经网络"这个前提**——可以直接是一套 pure-numpy 的生产控制面。

---

## 9. 进一步推进的方向

| 方向 | 思路 |
| --- | --- |
| **自适应正则 FTRL** | 按信号自适应 η_k（AdaGrad），匹配 SRE 里信号异质性 |
| **多维 Wasserstein** | 扩展到 K 维结构化信号空间，用 Sinkhorn 近似 |
| **在线雅可比辨识** | 从 scalar OLS 扩展到 vector OLS，估 full Jacobian |
| **时间信用分配的凸松弛** | 从 `a·loss·γ^t` 升级到 Shapley-over-time |
| **温度 + ε-greedy 混合** | 安全探索：小概率绕过 bias 走纯 exploration |

---

## 参考

- Vaswani et al. (2017). *Attention Is All You Need*. — `√d` 来源
- Jaynes (1957). *Information Theory and Statistical Mechanics*. — 温度对应 Legendre
- Shalev-Shwartz (2011). *Online Learning and Online Convex Optimization*. — FTRL 统一分析
- Wang & Carreira-Perpinán (2013). *Projection onto the probability simplex*. — 欧几里得投影算法
- Khalil (2002). *Nonlinear Systems*. — 收缩映射判据
- Werbos (1990). *Backpropagation Through Time*. — 时间信用分配
- Villani (2009). *Optimal Transport: Old and New*. — Wasserstein 理论基础
