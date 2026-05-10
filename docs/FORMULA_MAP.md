# 公式 ↔ 代码对照

所有公式严格对应原文图 / 正文里的描述。每一行给出：**数学式 → 论文章节 → 代码定位**。

---

## §2 传统残差

| 公式 | 章节 | 代码 |
| --- | --- | --- |
| `x_{l+1} = x_l + F_l(x_l)` | §2 残差诞生 | `attention_residuals/classic_residual.py` — `ClassicResidual.forward` |

---

## §3 Pre-Norm / Post-Norm

| 公式 | 章节 | 代码 |
| --- | --- | --- |
| `x_{l+1} = LN(x_l + F_l(x_l))` (Post-Norm) | §3 迁移挑战 | `attention_residuals/norm.py` — `NormWrapper(style=POST_NORM)` |
| `x_{l+1} = x_l + F_l(LN(x_l))` (Pre-Norm)  | §3 迁移挑战 | `attention_residuals/norm.py` — `NormWrapper(style=PRE_NORM)` |

---

## §4 Hyper-Connections (HC / mHC)

| 公式 | 章节 | 代码 |
| --- | --- | --- |
| `X^{(m)}_{l+1} = Σ_n A_{m,n} X^{(n)}_l + F_l(Σ_n B_{m,n} X^{(n)}_l)` | §4 演进探索 | `attention_residuals/hyper_connections.py` — `HyperConnection.forward` |
| 块对角 A（mHC）                                                      | §4          | `HyperConnection(groups=...)` 的 `_masked_mix_matrix` |

---

## §5 Attention Residuals（核心）

| 公式 | 章节 | 代码 |
| --- | --- | --- |
| `a_{l,k} = softmax_k( (q_l · K_k) / √d )` | §5.1 | `attention_residuals/attn_residual.py` — `AttentionResidual._compute_weights` |
| `AttnRes_l = Σ_k a_{l,k} · x_k`          | §5.1 | `AttentionResidual.forward`                         |
| `Σ_k a_{l,k} = 1`                         | §5.1 | `AttentionResidual.forward` 中的 `F.softmax`         |
| `K_k = W_K^{(k)} x_k`                     | §5.1 | `AttentionResidual.forward` 的 `share_key=False` 分支 |
| `x_{l+1} = AttnRes_l + F_l(x_l)`          | §5.1 | `AttentionResidualConnector.forward`                |

---

## §5 Block Attention Residuals

| 公式/规则 | 章节 | 代码 |
| --- | --- | --- |
| Block 间使用 Attn Residual，Block 内部使用（可选的）经典残差 | §5 图 5 | `attention_residuals/blocks.py` — `BlockAttnResStack.forward` |
| `num_blocks == 1` 退化为纯经典残差堆栈                        | §5 图 5 | `BlockAttnResStack` 边界情形 |
| `layers_per_block == 1` 退化为 Full Attention Residuals        | §5 图 5 | 同上 |
| "2 选 1"：默认关闭 Block 内经典残差                           | §5 末段 | `BlockAttnResStack.inner_residual=False` |

---

## §5.2 确定性保障的工程映射

| 论文提法 | 代码 |
| --- | --- |
| 信息传递必然关注（`Σ_k a_{l,k}=1`）                       | `metrics.mandatory_attention_score` |
| 纵横解耦（两套独立 Q 矩阵）                               | `DecoupledTransformerLayer` 的两个独立 `nn.Linear` |
| 分段机制保证 `O((L/B)^2 + L)`                              | `metrics.complexity_report` |

---

## §6 开放讨论

| 公式 | 章节 | 代码 |
| --- | --- | --- |
| `AttnRes^{(h)}_l = Σ_k a^{(h)}_{l,k} · (x_k W_V^{(h)})`                            | §6 多头纵向   | `attention_residuals/multi_head_vertical.py` — `MultiHeadAttentionResidual` |
| `x_{l+1} = g_l·(AttnRes_l + F_l(x_l)) + (1-g_l)·x_l`, `g_l = σ(w_l)`            | §6 动态跳层   | `attention_residuals/layer_skip.py` — `LayerSkipGate` |
| 多通道 AttnRes：`y = Σ_c μ_c · AttnRes^{(c)}_l`, `Σ_c μ_c = 1`                  | §6 多通道分层 | `MultiChannelVerticalAttention`（规划中，MVP 不含）|

---

## 工程常量对齐

| 常量 | 默认值 | 含义 |
| --- | --- | --- |
| `d_model`       | 64  | 特征维度（Demo 级别） |
| `num_heads`     | 1   | 默认"纯粹配置"使用单头 |
| `layers_per_block` | 4 | Block 分段大小，典型取 4 或 8 |
| `skip_threshold`   | 0.1 | 动态跳层推理阈值 |
