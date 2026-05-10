# Codex Handoff 路 Attention-Residuals

> 这份文档用于下一位接手者快速进入状态。
> 目标是把当前仓库的架构、已完成工作、已知风险、下一步动作一次说清。

---

## 1. 当前状态

- 当前分支：`attention-residuals-session`
- 远端：`origin`
- 全量测试：`pytest -q` 通过，当前为 `127/127`
- 最近一轮重点成果：
  - 补了 `docs/ARCHITECTURE.md`
  - 在 `docs/knowledge-base.html` 新增 `s22` 动图章节
  - 生成 `docs/assets/self_learning_envelope.gif`
  - 修正 `AdaptiveCombiner` 对静态 bias 的覆盖问题
  - 给上述修正补了回归测试

---

## 2. 架构地图

### 2.1 两层主干

1. 论文实现层
   - `classic_residual.py`
   - `norm.py`
   - `hyper_connections.py`
   - `attn_residual.py`
   - `blocks.py`
   - `multi_head_vertical.py`
   - `layer_skip.py`
   - `transformer_layer.py`
   - `stack.py`

2. SRE 控制层
   - `sre_control.py`
   - `sre_adaptive.py`
   - `sre_safety.py`
   - `sre_math.py`
   - `sre_self_envelope.py`

### 2.2 交付层

- `docs/DEEP-DIVE.md`
- `docs/EQUATIONS-AND-SRE.md`
- `docs/SRE-CONTROL-PLAYBOOK.md`
- `docs/SELF-LEARNING-ENVELOPE.md`
- `docs/ARCHITECTURE.md`
- `docs/knowledge-base.html`
- `examples/`
- `tests/`

---

## 3. 已完成工作

### 3.1 架构文档

- 新增 [docs/ARCHITECTURE.md](./ARCHITECTURE.md)
- 内容包括：
  - Architecture
  - Requirements
  - Task Breakdown
  - Refinement
- 文档把“论文机制 -> SRE 原语 -> 交付物”串成了一张工程图。

### 3.2 知识库补强

- 在 `docs/knowledge-base.html` 中新增 `s22`：
  - 数据变化收益 GIF
  - learned envelope vs baseline 对比
  - 收益表
- 新增图像资产：
  - `docs/assets/self_learning_envelope.gif`

### 3.3 代码修正

- 修正 `attention_residuals/sre_adaptive.py`
  - 之前 `AdaptiveCombiner` 会把 operator static bias 覆盖掉
  - 现在改为 `static_bias + learner_logits`
- 补充测试：
  - `tests/test_sre_adaptive.py`
  - 新增 `test_adaptive_combiner_preserves_static_bias_under_learning`

---

## 4. 模块梳理

### 4.1 Paper Layer

- `attn_residual.py`
  - 核心纵向注意力
  - `AttentionResidual`
  - `AttentionResidualConnector`
- `blocks.py`
  - 分段式 Attention Residual
  - 默认 `inner_residual=False`
- `multi_head_vertical.py`
  - 多头纵向注意力
- `layer_skip.py`
  - 动态跳层门控
- `transformer_layer.py`
  - 横向 MHA + 纵向 AttnRes 的解耦层
- `stack.py`
  - 统一残差栈入口

### 4.2 SRE Control Plane

- `sre_control.py`
  - `WeightedConvexCombiner`
  - `AuditTrail`
  - `DecoupledControlLoop`
  - `HierarchicalBlockController`
  - `BudgetGate`
  - `MustAttendRegistry`
- `sre_adaptive.py`
  - Hedge / regret learner
  - 自适应 bias
- `sre_safety.py`
  - SafetyEnvelope
  - ShadowRunner
  - CounterfactualExplainer
  - WeightDriftDetector
- `sre_math.py`
  - scale normalization
  - temperature schedule
  - multi-view combiner
  - FTRL
  - contraction monitor
  - temporal credit
  - Wasserstein drift
- `sre_self_envelope.py`
  - LearnedSafetyEnvelope
  - ContractionAwareEnvelope
  - EnvelopeLearner

---

## 5. 需求拆解

### 5.1 Functional requirements

- 支持六种残差策略可互换
- 支持纵向注意力权重暴露
- 支持 Block 分段和复杂度降低
- 支持多头纵向注意力和 layer skip
- 支持 SRE 控制的 convex combine / audit / must-attend
- 支持自适应学习和安全闭环
- 支持自学习外壳与 contraction-aware 外壳

### 5.2 Invariants

- `sum(weights) == 1`
- `floor <= weight <= ceiling`
- `fit()` 只能收紧
- `relax()` 是唯一放宽路径
- hard bounds 永不被自动突破
- wrapper 不能污染 inner state
- audit trail 必须可回放

### 5.3 Non-functional

- `sre_control` 保持纯 `numpy`
- 论文层保持 `nn.Module`
- 所有新增原语都要有 test + demo
- 关键路径可在 CPU 上运行
- 文档要能解释机制、实现、风险

---

## 6. 任务拆解

### Epic A

- 论文机制实现
- 当前状态：完成主干
- 关注点：`share_key=False` 还未真正实现

### Epic B

- SRE control plane
- 当前状态：完成核心原语
- 关注点：后续可接真实 metric source

### Epic C

- 闭环学习
- 当前状态：Hedge / adaptive bias 已完成
- 关注点：static bias + learner bias 的叠加语义已修正

### Epic D

- safety / observability
- 当前状态：shadow、counterfactual、drift 已有

### Epic E

- self-learning envelope
- 当前状态：已完成闭环自学习和 GIF 证据
- 关注点：label 设计可继续细化

### Epic F

- 知识系统
- 当前状态：`docs/ARCHITECTURE.md` + `knowledge-base.html` 已加厚

---

## 7. 已知 finding

1. `AttentionResidual` 中 `share_key=False` 仍未实现。
2. 这个问题在 review 中重复出现了两次，本质上是同一个 finding。
3. 当前应把它视为唯一明确的开放正确性问题：
   - 要么实现独立 key
   - 要么正式删掉这个配置入口

---

## 8. 风险与边界

- Self-learning envelope 受 selection bias 限制，只能学习到被允许看到的动作。
- GIF 是 synthetic replay，展示的是工程收益，不是生产 trace。
- `sre_control` 目前只依赖 numpy，适合控制面，但不适合承载复杂训练逻辑。
- 文档已比代码更丰富，后续要注意文档与实现一致性。

---

## 9. 下一步建议

1. 先处理 `share_key=False`
2. 接真实指标源，做一版 live demo
3. 继续细化 self-learning envelope 的 label / quorum
4. 让知识库自动生成目录和章节索引

---

## 10. 当前可直接继续的文件

- `attention_residuals/sre_adaptive.py`
- `tests/test_sre_adaptive.py`
- `docs/ARCHITECTURE.md`
- `docs/knowledge-base.html`
- `docs/assets/self_learning_envelope.gif`

