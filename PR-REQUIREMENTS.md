# PR 级功能需求清单

把《Attention Residuals》一文中的叙述性内容逐项翻译成可独立交付的 PR。
每个 PR 都有：背景、验收标准（DoD）、涉及文件、对应论文/文章原文定位。
颗粒度按"1 个 PR 1~2 天、不超过 400 行代码"来切分。

> 命名规约：`PR-<section>-<seq>: <短标题>`
> 例：`PR-5.1-01: 纵向自注意力核心算子`

---

## Epic 1 · 基础与背景：从"更深"到"更可靠"

### PR-1-01 · 层次化特征金字塔的文档化
- **背景**：文章 §1 强调深度学习之所以"要更深"，是为了层次化特征金字塔带来的表达能力；但加深会引入梯度消失与训练不稳定。
- **范围**：
  - 在 `docs/DESIGN.md` 中完成"为何要更深 / 为何会难训"的综述小节。
  - 加一张概念图（可用 Mermaid）体现浅层→深层的抽象递进。
- **DoD**：文档在 README 中有入口链接；所述观点严格对应原文，不引入外部主张。
- **文件**：`docs/DESIGN.md`。

### PR-1-02 · 核心术语表
- **背景**：文章穿插使用"残差 / 隐式纵向自注意力 / HC / mHC / Pre-Norm / Post-Norm"等术语，工程实现需要统一口径。
- **范围**：`docs/DESIGN.md` 增加术语表，中英文对照。
- **DoD**：所有术语在 README 与 FORMULA_MAP 中使用一致；新增术语通过 grep 检索能回到术语表。

---

## Epic 2 · 传统残差与 Norm 放置

### PR-2-01 · 经典残差算子 `x_{l+1} = x_l + F_l(x_l)`
- **背景**：文章 §2 给出残差网络最基础的形式。
- **范围**：
  - `ClassicResidual(nn.Module)`：接受任意 `F: Callable[[Tensor], Tensor]`，前向输出 `x + F(x)`。
  - 保留 `drop_path` 可选以便做 ablation，但默认关闭。
- **DoD**：
  - 输入输出形状一致。
  - 当 `F` 输出为 0 时等价于恒等映射（数值误差 < 1e-6）。
- **文件**：`attention_residuals/classic_residual.py`、`tests/test_norm.py` 中补一个冒烟用例。

### PR-2-02 · Pre-Norm / Post-Norm 封装
- **背景**：文章 §3 指出"Post-Norm 导致浅层信息绝对尺度逐层丢失；Pre-Norm 导致深层难以区分归一化偏差与微小学习目标"。工程要让两种模式可切换用于对照。
- **范围**：
  - `NormStyle` 枚举：`POST_NORM / PRE_NORM / NONE`。
  - `NormWrapper(sub, style, dim)`：对子模块的输入或输出做 LayerNorm。
  - 数学对齐：
    - Post-Norm：`LN(x + F(x))`
    - Pre-Norm： `x + F(LN(x))`
- **DoD**：
  - `tests/test_norm.py` 用同一份 `F` 与同一份输入，三种模式均能前向反向。
  - 关闭 Norm (NONE) 时等价于 `ClassicResidual`。
- **文件**：`attention_residuals/norm.py`、`tests/test_norm.py`。

---

## Epic 3 · HC / mHC 作为"修补式微创新"的参照

### PR-3-01 · Hyper-Connections (HC) 基础实现
- **背景**：文章 §4 提到字节 / DeepSeek 的 HC 用"多通道残差 + 通道混合"优化信息流动。
- **范围**：
  - `HyperConnection(nn.Module)`：维护 M 条残差通道；通过可训练的 M×M 矩阵 `A` 做通道混合。
  - 公式：`X^{(m)}_{l+1} = Σ_n A_{m,n} X^{(n)}_l + F(Σ_n B_{m,n} X^{(n)}_l)`，M 个通道。
  - 参数量 `O(M²)`，默认 M=4。
- **DoD**：
  - M=1 时退化为经典残差（数值一致）。
  - `tests/test_hyper_connections.py` 验证 M>1 时仍能过前反向。
- **文件**：`attention_residuals/hyper_connections.py`。

### PR-3-02 · mHC 变体（分组连接）
- **背景**：同 §4，mHC 对通道做分组避免全连接带来的复杂度爆炸。
- **范围**：`HyperConnection` 新增 `groups` 超参；分组后矩阵 `A` 被约束为块对角。
- **DoD**：
  - `groups=M` 时 A 是对角阵，相当于独立多通道；
  - `groups=1` 回到普通 HC。
- **文件**：`attention_residuals/hyper_connections.py`。

### PR-3-03 · HC/mHC 的局限性记录
- **背景**：文章批评 HC/mHC "没有跳层的混合连接或分组连接……历史学习成果作为一个不可分割的整体看待"。
- **范围**：在 `docs/DESIGN.md` 的 §4 对应小节里用不超过 200 字记录该批评；在 `HyperConnection` docstring 顶部贴一条对应的 TODO/NOTE 供未来 ablation 使用。
- **DoD**：代码注释可回溯到文档段落。

---

## Epic 4 · 核心：§5 Attention Residuals（本仓库的重头戏）

### PR-5.1-01 · 纵向自注意力核心算子（Full Attention Residuals）
- **背景**：文章 §5.1 提出新公式——当前层对所有历史层输出做 softmax 归一化的加权求和：
  ```
  AttnRes_l = Σ_{k=0..l} a_{l,k} · x_k,
  a_{l,k}   = softmax_k( (q_l · K_k) / √d ),
  Σ_k a_{l,k} = 1
  ```
- **范围**：
  - `AttentionResidual(nn.Module)`：
    - 输入：历史层输出列表 `[x_0, ..., x_l]`（形状 `[B, T, D]`）。
    - 可训练参数：当前层的 Query 矩阵 `W_Q`。Key 由历史层共享一个 `W_K`（或使用 x_k 本身作 key，依配置）。
    - 输出：`AttnRes_l`（形状 `[B, T, D]`）。
  - 权重暴露：提供 `last_weights()` 返回 `a_{l,k}`，便于可视化。
  - 严格验证：`torch.allclose(a.sum(-1), 1.0)`。
- **DoD**：
  - 单元测试 `tests/test_attn_residual.py`：
    - 权重沿 k 维度之和 ≈ 1；
    - 历史输入相同（恒等）的极端情况下输出 ≈ 输入均值；
    - 反向传播能更新 `W_Q`。
- **文件**：`attention_residuals/attn_residual.py`、`tests/test_attn_residual.py`。

### PR-5.1-02 · 扩展的残差替换：`x_{l+1} = AttnRes_l + F_l(x_l)`
- **背景**：§5.1 最后一步——把传统 `x_l + F_l(x_l)` 替换为 `AttnRes_l(x_{≤l}) + F_l(x_l)`。
- **范围**：
  - `AttentionResidualConnector(sublayer, attn_res)`：封装调用流程：
    1) 缓存历史层输出；2) 计算 `AttnRes_l`；3) 加上 `F_l(x_l)`；
  - 与 `NormWrapper` 互相兼容，可组合 Pre-Norm。
- **DoD**：`tests/test_stack.py` 验证端到端一条 3 层小 Stack 的前反向正确。
- **文件**：`attention_residuals/attn_residual.py`。

### PR-5-01 · Block Attention Residuals（分段版本）
- **背景**：§5 图 5 展示 Block Attention Residuals：总层数切成多个 Block，Block 内部沿用经典残差，Block 之间使用 Attn Residual。
- **范围**：
  - `BlockAttnResStack(nn.Module)`：
    - 超参：`num_blocks`, `layers_per_block`。
    - Block 内部复用经典残差；
    - 每个 Block 出口被记录为 `x_b`，新 Block 的第 1 层输入为 `AttnRes_b(x_0, ..., x_{b-1})`；
  - 可观测性：`trace()` 返回每个 Block 级注意力的 a 权重。
- **DoD**：当 `num_blocks == 1` 时退化为纯经典残差堆栈；当 `layers_per_block == 1` 时退化为 Full Attention Residuals。
- **文件**：`attention_residuals/blocks.py`、`tests/test_blocks.py`。

### PR-5-02 · 二次残差消融开关
- **背景**：文章最后指出 Block Attention Residuals 与 Block 内部的经典残差同时存在是"信息冗余"，作者倾向 2 选 1。
- **范围**：`BlockAttnResStack.inner_residual: bool = False`；开启则保留 Block 内部经典残差，默认关闭。
- **DoD**：两种取值都能跑；`docs/DESIGN.md` §5 小节记录该选择的理由。

### PR-5.2-01 · 横向+纵向解耦的 Transformer 层
- **背景**：§5.2 强调"横向自注意力对上下文深度学习，纵向自注意力在层间传递有效学习成果"；两者参数独立。
- **范围**：
  - `DecoupledTransformerLayer`：
    - 横向 MHA（标准 `nn.MultiheadAttention`）处理 token 维度；
    - 纵向 `AttentionResidual` 处理 layer 维度；
    - 两者的 `W_Q` 不共享。
  - 层输出 = FFN(LN(x + MHA(LN(x)))) + AttnRes_l，按 README 公式。
- **DoD**：合成 `[B=2, T=8, D=16]` 输入下能过 3 层前反向；纵向权重与 MHA 权重在梯度上彼此独立（断开对方参数后仍能求导）。
- **文件**：`attention_residuals/transformer_layer.py`、`tests/test_stack.py`。

### PR-5.2-02 · 三种确定性保障的指标化
- **背景**：§5.2 给出 3 项确定性保障：必然关注、训练动态可控、分段机制。工程需要把它们变成可度量的指标。
- **范围**：
  - `metrics.py`：
    - `mandatory_attention_score(a)`：衡量 a 权重的熵 / 非零占比；
    - `vertical_horizontal_decoupling(grads)`：纵向/横向梯度协方差；
    - `complexity_report(stack)`：输出理论 FLOPs/参数量与层数的关系。
- **DoD**：在 `examples/compare_residual_variants.py` 里调用这三项指标并打印。

### PR-5.3-01 · "纯粹性"原则下的默认配置
- **背景**：§5.3 强调"回归自注意力本质"，架构要简洁、依赖关系要简单。
- **范围**：为 `AttentionResidual` / `BlockAttnResStack` 提供一份"纯粹默认"预设：单头、无 dropout、softmax 不加温度、Key 直接取历史 hidden、Query 是唯一新增参数。
- **DoD**：默认构造的 `AttentionResidual(d_model=D)` 只引入 `D·D` 个新参数。

---

## Epic 5 · §6 开放讨论：多头纵向 + 动态跳层

### PR-6-01 · 多头纵向自注意力
- **背景**：§6 提问"Attention Residuals 有没有可能演变成多头自注意力？"。
- **范围**：
  - `MultiHeadAttentionResidual`：在 head 维度上并行计算 `AttnRes^{(h)}_l`，最后 concat + `W_O`。
  - 每头独立的 `W_Q^{(h)}, W_K^{(h)}, W_V^{(h)}`。
- **DoD**：`num_heads = 1` 时与 `AttentionResidual` 数值一致。
- **文件**：`attention_residuals/multi_head_vertical.py`。

### PR-6-02 · 动态跳层门控
- **背景**：§6 第二问："Transformer 层数变多了之后，有没有可能动态跳过一些层？"
- **范围**：
  - `LayerSkipGate`：每层一个可学习标量 `g_l ∈ (0,1)`（通过 sigmoid 约束）。
  - 前向：`x_{l+1} = g_l · (AttnRes_l + F_l(x_l)) + (1 - g_l) · x_l`。
  - 推理期支持将 `g_l < τ` 的层直接短路以省算力。
- **DoD**：
  - `g_l = 1` 时等价于标准 Attention Residual；
  - 推理阶段 `skip_threshold` 可以跳过任意子集。
- **文件**：`attention_residuals/layer_skip.py`。

### PR-6-03 · 多通道纵向自注意力（分层 × 分类）
- **背景**：§6 指出"多通道的分层学习仍然是值得拓展的路径"，即把分类学习（HC 思路）与分层学习（Attn Residual 思路）相结合。
- **范围**：`MultiChannelVerticalAttention`：维护 M 个并行的 `AttentionResidual`，最后通过一个轻量加权汇总。
- **DoD**：与 HC 的接口风格保持一致，能在 `compare_residual_variants.py` 中作为第 4 条基线。

---

## Epic 6 · 端到端装配、示例与 CI

### PR-7-01 · 端到端 Stack（可配置的纵向连接类型）
- **背景**：需要一个总入口把"纯 Residual / HC / mHC / Full AttnRes / Block AttnRes / 多头 AttnRes"都作为可切换策略。
- **范围**：
  - `ResidualStack(mode: ResidualMode, ...)`：
    - 统一的前向接口 `forward(x)`；
    - 内部根据 `mode` 装配对应模块；
    - 保留统一的 `trace()` 与 `metrics()` 入口。
- **DoD**：六种模式均能在 `examples/` 中跑通前反向。
- **文件**：`attention_residuals/stack.py`、`tests/test_stack.py`。

### PR-7-02 · 对照实验 Demo
- **背景**：文章的叙述是"Attn Residual 胜于 HC / Classic"。工程需要用一个小任务把三种连接方式对比打印出来。
- **范围**：
  - `examples/compare_residual_variants.py`：
    - 合成任务（MLP-Mixer 风格的小序列分类）；
    - 固定随机种子；
    - 打印每种模式的收敛曲线、纵向注意力权重分布、理论 FLOPs。
- **DoD**：在 CPU 上 1 分钟内跑完；输出一个 CSV 与可选 PNG。

### PR-7-03 · Block vs Full 的复杂度对比
- **背景**：§5.2 第 3 点：分段机制保证工程可行。
- **范围**：`examples/demo_block_attn_residual.py`：遍历 L ∈ {8, 32, 64, 100, 128}，记录 Full 与 Block(B=8) 两种模式的前向耗时、显存占用、参数量。
- **DoD**：输出随 L 增长的对比表；证明 Block 模式的斜率显著低于 Full。

### PR-7-04 · 单元测试 & 最小 CI
- **背景**：工程化 guardrail。
- **范围**：
  - `tests/` 每个模块至少 1 个测试；
  - 可选增加 GitHub Actions workflow（本仓库默认只留 pytest 命令，CI 文件不纳入 MVP）。
- **DoD**：`pytest -q` 全绿；覆盖率 ≥ 70%。

---

## 附录 · PR 与论文/文章段落的双向追溯

| PR 编号 | 原文定位 | 关键词 |
| --- | --- | --- |
| PR-1-01/02 | 引言 + §1 深度学习为何要更深 | 层次化特征、更深→更可靠 |
| PR-2-01/02 | §2 残差诞生 / §3 Pre-Norm、Post-Norm | `x+F(x)`、LayerNorm 放置 |
| PR-3-01/02/03 | §4 HC / mHC | 多通道残差、分组连接 |
| PR-5.1-01/02 | §5.1 核心公式 | `AttnRes_l`、Σa=1 |
| PR-5-01/02 | §5 Block Attention Residuals | 分段、2 选 1 |
| PR-5.2-01/02 | §5.2 三项确定性保障 | 纵横解耦、可审计指标 |
| PR-5.3-01 | §5.3 纯粹性 / Less is More | 默认最小参数 |
| PR-6-01/02/03 | §6 开放讨论 | 多头纵向、动态跳层、多通道分层 |
| PR-7-01/02/03/04 | 全文装配 | Stack、对比 Demo、CI |
