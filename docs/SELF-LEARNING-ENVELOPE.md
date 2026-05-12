# Self-Learning SafetyEnvelope · Round 6

> 把外层安全壳从"静态人工配置"升级为"从 audit trail 自学习、只能收紧不能自动放松"的自举结构。
> 这是 Attention Residuals §5.2 "audit 反哺 controller = 确定性"在 SRE 侧最深刻的工程翻版。

配套代码：
- [`attention_residuals/sre_self_envelope.py`](../attention_residuals/sre_self_envelope.py)
- 测试：[`tests/test_sre_self_envelope.py`](../tests/test_sre_self_envelope.py) · 32 个用例
- Demo：[`examples/demo_self_learning_envelope.py`](../examples/demo_self_learning_envelope.py)

---

## 1. 为什么 SafetyEnvelope 必须学

前几轮的 `sre_safety.SafetyEnvelope` 是**静态**的——运维在部署时拍一组 `low / high / max_delta`。
问题：

| 拍太松 | 拍太紧 |
| --- | --- |
| 控制器一路开到 `high`，安全网形同虚设 | 控制器被勒死，无法响应真实 SLO 需求 |
| 生产出事故后才发现边界不对 | 运维不敢放宽，怕再出事；无限循环 |

两种情况都意味着**人要持续介入**，这违背了 SRE 的核心目标——自动化。

Attention Residuals 给的答案：让外壳**从历史决策里自己学边界**。
但必须带上一组不可妥协的安全约束——否则自己学到的外壳反倒会放大风险。

---

## 2. 五条安全约束

这套原语的整个价值取决于这五条约束是否**永不破**。

### 2.1 硬外壳（hard bounds）
运维配的 `hard_low / hard_high / hard_max_delta` 是**不可逾越的上限**。
学出来的 envelope 永远 `⊆` 硬外壳。
> 学多激进，都不会比运维允许的更激进。

### 2.2 单调收紧棘轮（monotone ratchet）
`fit()` 只能让 envelope 变紧，**永不自动放宽**。
想放宽必须调用 `relax()`——这是运维的显式操作。
> 就像家里的防火门：自动关上、手动才能开。

### 2.3 法定人数（quorum）
单次偶然的 UNSAFE 事件不触发收紧。
至少要 `unsafe_quorum` 次连续 UNSAFE 才启动一次 fit。
> 防止抖动：孤立的离群点不应该永久改变系统行为。

### 2.4 滞回（hysteresis）
收紧时不是贴着安全数据边界贴，而是留 `hysteresis × width` 的余量。
> 避免"边界线"附近的小波动反复触发。

### 2.5 最小动作余量（min_max_delta）
`max_delta` 有下限。不允许自锁死到 0。
> 最坏情况下控制器仍然可以慢慢走出去，不会彻底瘫痪。

---

## 3. 数学

### 3.1 Ratchet 更新

给定过去的 SAFE 动作样本 `{a_i}^N`，取其 ``p`` 分位数：

```
q_hi = quantile(SAFE_actions, p)
q_lo = quantile(SAFE_actions, 1-p)
width = max(q_hi - q_lo, ε)
pad = width · hysteresis / 2
proposed_hi = q_hi + pad
proposed_lo = q_lo - pad
```

**棘轮**（只收不放）：

```
new_hi = min(current_hi, proposed_hi)
new_lo = max(current_lo, proposed_lo)
```

**硬外壳**夹紧：

```
new_hi = clip(new_hi, hard_lo, hard_hi)
new_lo = clip(new_lo, hard_lo, hard_hi)
new_hi = max(new_hi, new_lo + ε)    # 保持区间不退化
```

### 3.2 Max_delta 学习

从 SAFE delta（`|action_t - action_{t-1}|`）的 p 分位数学：

```
q_md = quantile(SAFE_deltas, p) · (1 + hysteresis)
new_md = clip(min(current_md, q_md), min_max_delta, hard_max_delta)
```

`min_max_delta` 的 floor 确保控制器永远有一定的动作空间。

### 3.3 Contraction-aware 额外收紧

叠在学到的 envelope 上，基于 §20 方程 ⑤ 的实时增益估计：

```
scale = clip(target_gain / max(|gain|, target_gain), min_scale, 1)
effective_max_delta = max(min_max_delta, learned_max_delta · scale)
```

关键：这是一个**瞬时、不持久化**的修饰——`inner.max_delta` 本身不变。
> 给控制器一个"plant 正在烧"的刹车，但不污染 envelope 状态。

---

## 4. 选型偏差（Selection Bias）注意事项

> **"envelope 只能看到它没拦住的动作。"**

如果 envelope 永远不让控制器尝试 `u > 2`，就永远没机会观察到 `u=3` 到底安不安全。
这条 limitation 不可避免——**硬外壳必须由人设定**。
硬外壳的作用正是**给一个受控的探索空间**，在里面 envelope 收紧。

工程上的应对：
1. **定期 `relax(factor)`**：每 N 天 / 每个 release 周期，按 1.5× 放宽，让 envelope 重新探索边缘。
2. **Chaos / canary 里跑得比生产宽**：故意在 canary 环境用更宽的硬外壳，把结果拉回来训练生产的 envelope。
3. **Shadow runner 并行**：`ShadowRunner` 让新 envelope 在旁边跑、不影响主流量，观察它会不会主动 clip 有害动作。

---

## 5. 与 §5.2 论文洞察的呼应

论文 §5.2 三条确定性保障里最关键的是：

> **"审计 + 自学习 = 确定性"**

Attention Residuals 实现的是"层间权重可学习 + Σa=1 + last_weights() 可审计"。
本模块实现的是"**动作边界可学习 + 硬外壳永不破 + fit_history() 可审计**"。

两者共享同一套哲学：
- 约束内核（Σa=1 / hard bounds）**硬**；
- 偏好（bias / learned bounds）**软、可学、可审计**；
- 一切从历史数据来，一切都留下痕迹给事后追查。

---

## 6. API 概览

```python
from attention_residuals.sre_self_envelope import (
    LearnedSafetyEnvelope, ContractionAwareEnvelope,
    EnvelopeLearner, OutcomeLabel,
)

# 1. Construct with hard bounds (operator-chosen)
env = LearnedSafetyEnvelope(
    action_dim=1,
    hard_low=np.array([-5.0]),
    hard_high=np.array([+5.0]),
    hard_max_delta=np.array([3.0]),
    min_max_delta=np.array([0.3]),
    safe_quantile=0.9,
    hysteresis=0.1,
    unsafe_quorum=5,
    min_safe_samples=30,
    buffer_size=500,
)

# 2. (optional) wrap with contraction awareness
from attention_residuals.sre_math import JacobianContractionMonitor
mon = JacobianContractionMonitor(window=64)
wrapper = ContractionAwareEnvelope(env, gain_provider=mon.gain,
                                    target_gain=1.0, min_scale=0.3)

# 3. Wire into an orchestrator that pulls from audit + labels outcomes
def labeler(ctx): return OutcomeLabel.SAFE if ctx["p99"] < 300 else OutcomeLabel.UNSAFE
learner = EnvelopeLearner(wrapper, labeler=labeler, fit_every=25)

# 4. Per-tick: apply + observe
for t in ticks:
    clipped_action, info = wrapper.apply(raw_action)
    # ... apply clipped_action to the plant ...
    mon.observe(clipped_action[0], observed_state_delta, step=t)
    learner.ingest(clipped_action, post_action_context, delta=delta, step=t)

# 5. Operator intervention when needed
env.relax(factor=1.5)                # widen 50%
env.relax(to_hard=True)              # back to hard bounds
env.relax(dim=0, factor=2.0)         # per-dim
```

### 6.1 Soft-label fit gates

Under hard labels, one SAFE record carries one unit of SAFE evidence, so
`min_safe_samples` and the evidence threshold are numerically identical.
Under soft labels they diverge:

- `min_safe_samples` counts SAFE records admitted to the rolling buffer.
- `min_safe_evidence` sums the SAFE weights used by the weighted
  quantile estimator.
- If `min_safe_evidence` is not provided, it defaults to
  `float(min_safe_samples)` to preserve hard-label behavior.

Example: ten `OutcomeEvidence(1.0, confidence=0.2)` observations satisfy
`min_safe_samples=10`, but only contribute `safe_evidence=2.0`. Operators
can lower `min_safe_evidence` when they want count-based exploration, or
raise it when low-confidence labels should not move the envelope.

---

## 7. Demo 跑出的六大不变量

`python -m examples.demo_self_learning_envelope`：

| Invariant | 验证 | 结果 |
| --- | --- | --- |
| I. 永不逾越硬外壳 | 全程 `low ≥ hard_low`, `high ≤ hard_high`, `max_δ ≤ hard_max_delta` | 所有 margins 均 = 0 |
| II. 无 UNSAFE 则不收紧 | regime shift 前 150 ticks 无收紧事件 | `[]` |
| III. 有 UNSAFE 后首次收紧 | 第 3 个 UNSAFE 事件后立刻收紧 | `t=159`：`[-5, +5]` → `[+0.40, +2.60]`, `max_δ`: 3.0 → 0.30 |
| IV. 单调（自动永不放宽） | 全程每一步比较 | 自动放宽事件数 = 0 |
| V. `relax()` 是唯一放宽路径 | 手动调用 `relax(1.5)` / `relax(to_hard)` | 分别放宽到指定倍数 / 硬外壳 |
| VI. 收缩感知不破坏内部状态 | gain=4 下 scale=0.3, but `inner.max_δ` 不变 | `inner.max_δ`: 3.000 → 3.000 |

---

## 8. 复利方向

| 方向 | 思路 | 收益 |
| --- | --- | --- |
| **Per-dim adaptive quorum** | 不同维度不同 quorum | 有些维度（例如"关闭全部实例"）第一次就应该收紧 |
| **Soft labels** | 把 `label()` 变成 [0, 1] 的连续可靠度 | 替代硬二元 SAFE/UNSAFE，适配不确定的 post-hoc 判断 |
| **Envelope ensemble** | 用多个独立的学习 envelope 投票 | 降低单个 labeler 噪声；取最紧者 = 更保守 |
| **Bayesian posterior on bounds** | 把分位数换成贝叶斯后验 + 置信区间 | 小样本时更保守，大样本时更贴合经验 |
| **与 `TemporalCreditAssigner` 对接** | 事后归因反过来修正 labeler | 能识别"这个动作*不是*当时的主因"，减少对错 UNSAFE 的过反应 |
| **Policy-gradient envelope** | 把 envelope 作为策略的一部分端到端训 | 打通到 RL-based SRE；但要保证硬外壳仍然不可破 |

---

## 9. 与前面所有原语的关系（闭合图）

```
sre_control       ─┐
                   │ audit trail (weights, actions, labels, counterfactuals)
sre_adaptive      ─┤
                   │                    ┌────────────── feedback ──────────────┐
sre_safety        ─┤                    ▼                                      │
                   │   ┌─────────────────────────────────┐                    │
sre_math          ─┤   │  sre_self_envelope              │                    │
                   │   │  ─ LearnedSafetyEnvelope        │   tightens bounds  │
                   │   │  ─ ContractionAwareEnvelope     │◀───────────────────┘
                   │   │  ─ EnvelopeLearner              │
                   │   └─────────────────┬───────────────┘
                   │                     ▼
                   │              hard bounds (operator-set, immutable)
                   │                     ▼
                   │              actuator
                   └─
```

**这是整个系统第一次真正闭环**：
- 信号流经 `sre_control` 产生决策；
- `sre_adaptive` 学权重偏好；
- `sre_math` 稳定性 / 异常检测 / 归因；
- `sre_safety` 强制硬约束；
- **`sre_self_envelope` 把安全壳本身也学起来**——用 audit trail 的 SAFE/UNSAFE 标签反向调优硬外壳内的边界。

回到 §5.2 的那句话：
> *"自学习 + 可审计 = 确定性"*

这一轮终于做到了"安全层本身也在学、但不破硬约束"。
