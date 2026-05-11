# Attention-Residuals

> 从深度学习本质出发看残差网络的演进 —— Kimi《Attention Residuals》工程落地
> Engineering reimplementation of *Kimi Team. Attention Residuals. arXiv: 2603.15031 [cs.CL]*

本工程把《Attention Residuals》一文里的数学结构系统性地落地为 PyTorch 代码：
把论文里所有公式都写成可运行的 PyTorch 模块，把其他叙述性内容逐项拆成 PR 级功能需求（见
[`PR-REQUIREMENTS.md`](./PR-REQUIREMENTS.md)），并串成一个从单层到整网的端到端 Demo。

> **📖 机制级深度拆解（图文知识库）：** [`docs/knowledge-base.html`](./docs/knowledge-base.html)
> — 每个模块按"机制直觉 → 公式 → 重绘原理图 → 工程实现 → 局限"逐项讲透，双击即可在浏览器里看。
>
> **🔁 SRE 控制工程复利：** [`docs/SRE-CONTROL-PLAYBOOK.md`](./docs/SRE-CONTROL-PLAYBOOK.md)
> — 把 Attention Residuals 抽成 7 条领域无关的原语，落到 `attention_residuals/sre_control.py`，配套
> [`examples/demo_sre_autoscaler.py`](./examples/demo_sre_autoscaler.py) 端到端分层扩缩容 Demo。
>
> **🧮 数学底座 / 闭环学习 / 工业安全：** [`docs/DEEP-DIVE.md`](./docs/DEEP-DIVE.md)
> — softmax 的最大熵推导、Hedge 后悔界证明、四锁安全层设计。配套模块
> [`sre_adaptive.py`](./attention_residuals/sre_adaptive.py) / [`sre_safety.py`](./attention_residuals/sre_safety.py) 与三层联动 Demo
> [`examples/demo_sre_adaptive_safety.py`](./examples/demo_sre_adaptive_safety.py)。
>
> **🧬 七个方程 × 七条原语：** [`docs/EQUATIONS-AND-SRE.md`](./docs/EQUATIONS-AND-SRE.md)
> — 把 `(q·K)/√d` / `softmax(·/τ)` / `concat·W_O` / FTRL / `I+∂F/∂x` / `∂L/∂x_l` / `KL vs W₁` 每个方程吃透，
> 各抽一条复利原语到 [`sre_math.py`](./attention_residuals/sre_math.py)。
> Demo：[`examples/demo_sre_math_primitives.py`](./examples/demo_sre_math_primitives.py)。
>
> **🔒 自学习 SafetyEnvelope：** [`docs/SELF-LEARNING-ENVELOPE.md`](./docs/SELF-LEARNING-ENVELOPE.md)
> — 把安全外壳从"静态人工配置"升级为"从 audit trail 自学习、只收不放的棘轮"。
> 五条硬约束 + 六大不变量全部用代码验证。
> 实现：[`sre_self_envelope.py`](./attention_residuals/sre_self_envelope.py)，
> Demo：[`examples/demo_self_learning_envelope.py`](./examples/demo_self_learning_envelope.py)。
>
> **🧭 软标签 + 归因修正：** [`docs/SOFT-LABEL-CREDIT.md`](./docs/SOFT-LABEL-CREDIT.md)
> — 把 `SAFE/UNSAFE` 升级为带置信度的 evidence，并用 `TemporalCreditAssigner` 防止外因事故误收紧 envelope。
> Demo：[`examples/demo_credit_aware_envelope.py`](./examples/demo_credit_aware_envelope.py)。
>
> **📼 Audit JSONL 回放：** [`docs/AUDIT-CREDIT-REPLAY.md`](./docs/AUDIT-CREDIT-REPLAY.md)
> — 把 `AuditTrail.to_jsonl()` 直接重放进 `TemporalCreditAssigner`，用于离线复盘或流式事故归因。
> Demo：[`examples/demo_audit_credit_replay.py`](./examples/demo_audit_credit_replay.py)。
>
> **📡 指标源接入：** [`docs/METRIC-SOURCES.md`](./docs/METRIC-SOURCES.md)
> — 用标准库适配 Prometheus instant query 与 OpenTelemetry OTLP JSON，把真实指标转成 audit context。
> Demo：[`examples/demo_metric_source_replay.py`](./examples/demo_metric_source_replay.py)。

一句话总结 Kimi 的主张：
> **Transformer 除了横向（上下文方向）的自注意力之外，层间同样存在一个被残差网络隐式承载的"纵向自注意力"。既然它是自注意力，就应该把它显式化、可学习化、可审计化。**

显式化之后：
- 信息稀释从"概率事件"变成"确定性事件"；
- 纵向与横向信息流解耦，训练动态更可控；
- 借助 Block 分段，100 层以上的超深模型在计算复杂度上是可预期的。

---

## 1. 文章结构与代码的一一映射

| 论文章节 | 核心对象 | 代码模块 |
| --- | --- | --- |
| §1 深度学习为何要更深 | 层次化特征金字塔 | 总体设计动机，见 [`docs/DESIGN.md`](./docs/DESIGN.md) |
| §2 残差诞生 | `x_{l+1} = x_l + F_l(x_l)` | [`attention_residuals/classic_residual.py`](./attention_residuals/classic_residual.py) |
| §3 迁移挑战：Pre-Norm / Post-Norm | LayerNorm 放置位置 | [`attention_residuals/norm.py`](./attention_residuals/norm.py) |
| §4 演进探索：HC / mHC | 多通道残差混合 | [`attention_residuals/hyper_connections.py`](./attention_residuals/hyper_connections.py) |
| §5.1 显式纵向自注意力 | `AttnRes_l = Σ_k a_{l,k} · x_k`, `Σ a_{l,k} = 1` | [`attention_residuals/attn_residual.py`](./attention_residuals/attn_residual.py) |
| §5 Full Attention Residuals | 所有历史层全连通 | `AttnResMode.FULL` in `attn_residual.py` |
| §5 Block Attention Residuals | Block 内部经典残差 + Block 间 Attn Residual | [`attention_residuals/blocks.py`](./attention_residuals/blocks.py) |
| §5.2 纵/横解耦 | 两条独立的注意力路径 | [`attention_residuals/transformer_layer.py`](./attention_residuals/transformer_layer.py) |
| §5.2 分段机制保证工程可行 | 计算量随 L 的渐进可控 | `BlockAttnResStack` 分段策略 |
| §6 开放讨论 | 多头纵向自注意力、动态跳层 | [`attention_residuals/multi_head_vertical.py`](./attention_residuals/multi_head_vertical.py)、[`attention_residuals/layer_skip.py`](./attention_residuals/layer_skip.py) |

公式的"出处 - 数学式 - 代码定位"三元对照请见 [`docs/FORMULA_MAP.md`](./docs/FORMULA_MAP.md)。

---

## 2. 数学公式总览

以下公式全部在 `attention_residuals/` 对应模块里有可运行实现：

```
# §2 Classic residual
x_{l+1} = x_l + F_l(x_l)                        # classic_residual.py

# §3 Pre-Norm / Post-Norm
x_{l+1} = LN(x_l + F_l(x_l))                    # Post-Norm,  norm.py
x_{l+1} = x_l + F_l(LN(x_l))                    # Pre-Norm,   norm.py

# §4 Hyper-Connections (HC / mHC, 多通道残差)
X^{(m)}_{l+1} = Σ_n α_{m,n} X^{(n)}_l + F_l(Σ_n β_{m,n} X^{(n)}_l)    # hyper_connections.py

# §5.1 核心公式：纵向自注意力残差
# 传统残差:      x_{l+1} = x_l + F_l(x_l)
# Attn Residual: x_{l+1} = AttnRes_l(x_0, x_1, ..., x_l) + F_l(x_l)
#               AttnRes_l = Σ_{k=0..l} a_{l,k} · x_k
#               Σ_{k=0..l} a_{l,k} = 1
#               a_{l,k} = softmax_k( (q_l · K_k) / √d )                # attn_residual.py

# §5 Block Attention Residuals (分段)
# 在 Block 内部使用传统残差；Block 之间使用 Attn Residual。
# 总层数 L 被切成 G 段，每段 B 层。纵向注意力只跨 Block 出口计算，
# 复杂度从 O(L^2) 降到 O((L/B)^2 + L)。                                    # blocks.py

# §6 多头纵向自注意力
# AttnRes^{(h)}_l = Σ_k a^{(h)}_{l,k} · (x_k W_V^{(h)})                # multi_head_vertical.py

# §6 动态跳层：给每一层一个可学习 gating g_l ∈ (0, 1)
# x_{l+1} = g_l · (AttnRes_l + F_l(x_l)) + (1 - g_l) · x_l             # layer_skip.py
```

所有 softmax、权重归一化、参数矩阵维度均严格与论文描述对齐，详见
[`docs/FORMULA_MAP.md`](./docs/FORMULA_MAP.md)。

---

## 3. 目录结构

```
Attention-Residuals/
├── README.md                  # 你正在看的这份
├── PR-REQUIREMENTS.md         # 叙述性内容翻译成的 PR 清单
├── pyproject.toml
├── requirements.txt
├── docs/
│   ├── DESIGN.md              # "纯粹性 / Less is More" 下的设计说明
│   └── FORMULA_MAP.md         # 公式 ↔ 代码逐行对照
├── attention_residuals/
│   ├── __init__.py
│   ├── types.py               # 基础数据类型与配置
│   ├── norm.py                # §3 Pre-Norm / Post-Norm 封装
│   ├── classic_residual.py    # §2 传统残差
│   ├── hyper_connections.py   # §4 HC / mHC
│   ├── attn_residual.py       # §5.1 Full Attention Residuals (核心)
│   ├── blocks.py              # §5   Block Attention Residuals (分段)
│   ├── multi_head_vertical.py # §6   多头纵向自注意力
│   ├── layer_skip.py          # §6   动态跳层
│   ├── transformer_layer.py   # §5.2 横向+纵向解耦的 Transformer 层
│   └── stack.py               # 端到端装配：Residual-Only / Attn-Res / Block
├── examples/
│   ├── demo_attn_residual.py          # Full Attention Residuals 前向/反向验证
│   ├── demo_block_attn_residual.py    # Block 版本 vs 全连通的开销对比
│   └── compare_residual_variants.py   # 传统残差 / HC / AttnRes 在同一小任务上的对比
└── tests/
    ├── test_attn_residual.py
    ├── test_blocks.py
    ├── test_hyper_connections.py
    ├── test_norm.py
    └── test_stack.py
```

---

## 4. 快速开始

```bash
# 建议使用虚拟环境
python -m venv .venv && .venv\Scripts\activate

# 安装依赖（需要 PyTorch）
pip install -r requirements.txt

# 运行核心 Demo：对比传统残差 / HC / Attention Residuals
python -m examples.compare_residual_variants

# 仅跑 Full Attention Residuals 的数值正确性验证
python -m examples.demo_attn_residual

# Block 版本（分段）与 Full 版本的性能对比
python -m examples.demo_block_attn_residual

# 单元测试
pytest -q
```

---

## 5. 设计原则（摘自论文 + 工程裁剪）

1. **Less is More**：用一个统一的自注意力算子同时覆盖"横向上下文依赖"与"纵向层间依赖"，而不是堆新的连接模式。
2. **权重归一化 = 信息守恒**：纵向注意力的权重 `a_{l,k}` 必须严格 softmax 归一化，`Σ_k a_{l,k} = 1`，保证浅层有效信息最大保真、避免信息过载。
3. **纵/横解耦**：横向 self-attention 继续负责上下文理解；新增的纵向 self-attention 单独负责层间残差，两者用各自的权重矩阵。
4. **2 选 1**：Block Attention Residuals 中，Block 之间使用 Attn Residual；Block 内部的经典残差仍可保留，但默认策略是 **去掉** Block 级别的二次残差以避免冗余（见论文结语中作者的观察）。
5. **分段可控**：把 L 层切成 G 个 Block，纵向注意力只跨 Block 出口计算，计算量从 O(L²) 降到 O((L/B)² + L)，100 层级别依旧可预期。
6. **可审计**：每一层暴露 `a_{l,k}` 权重向量，便于离线分析浅层→深层信息路径。

---

## 6. 致谢

原文：
[《Attention Residuals》？从深度学习本质出发看残差网络的演进](
https://www.chaspark.com/)（黄大年茶思屋，作者：丁美玲，2026-03-17）

论文：
- Kimi Team. *Attention Residuals*. arXiv:2603.15031 [cs.CL].
- Zhenda Xie et al. *mHC: Manifold-Constrained Hyper-Connections*. arXiv:2512.24880 [cs.CL] (2026).

本工程为学习/工程落地目的，对原文观点做了最小化重述，并附加了可运行实现。
