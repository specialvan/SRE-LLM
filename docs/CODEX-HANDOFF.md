# Codex Handoff - Attention-Residuals

> 面向下一位 Codex 接手者的工程交接文档。本文只描述
> `D:\workspace\SRE-LLM\Attention-Residuals` 这条线，不混入其他子项目。

## 当前状态
- 工作目录：`D:\workspace\SRE-LLM\Attention-Residuals`
- 当前分支：`attention-residuals-session`
- 远端：`origin https://github.com/specialvan/SRE-LLM.git`
- 当前定位：库级 SRE 控制原语与 Attention Residuals 论文机制复用，不是 HTTP 服务型 runtime
- 当前验证：`pytest --collect-only -q` 收集 `154` 个测试；上一轮全量 `pytest -q` 通过
- 最近主线：
  - 修复 `AttentionResidual.share_key=False`，补齐 per-slot `W_K^{(k)}` ablation
  - 增加 soft label / temporal credit / credit-aware envelope
  - 增加 Audit JSONL 离线与流式 replay
  - 增加 Prometheus / OpenTelemetry 指标源适配
  - 更新 architecture、knowledge-base、GIF 和多份机制文档

## 项目本质
一句话概括：

> 它先把 Transformer 中“隐式纵向残差”显式化为可学习、可审计、受约束的 attention 结构，再把这套结构抽象成 SRE 控制工程中的“可学习但安全优先”的控制平面原语。

当前仓库不是完整生产服务。它提供的是可嵌入服务、任务、控制器或离线 replay job 的核心机制层。

## 模块地图

### 1. Paper Layer
- `classic_residual.py`：经典残差 `x + F(x)`
- `norm.py`：Pre-Norm / Post-Norm 包装
- `hyper_connections.py`：HC / mHC 多通道残差
- `attn_residual.py`：核心 Attention Residual，支持 shared key 与 per-slot key
- `blocks.py`：Block Attention Residuals
- `multi_head_vertical.py`：多头纵向注意力
- `layer_skip.py`：动态跳层门控
- `transformer_layer.py`：横向 MHA + 纵向 AttnRes 解耦层
- `stack.py`：统一残差策略入口

### 2. SRE Control Plane
- `sre_control.py`
  - `WeightedConvexCombiner`
  - `AuditTrail`
  - `DecoupledControlLoop`
  - `HierarchicalBlockController`
  - `BudgetGate`
  - `MustAttendRegistry`
- `sre_adaptive.py`
  - `HedgeRegretLearner`
  - `AdaptiveCombiner`
  - 静态 bias + learner logits，不能互相覆盖
- `sre_safety.py`
  - `SafetyEnvelope`
  - `ShadowRunner`
  - `CounterfactualExplainer`
  - `WeightDriftDetector`
- `sre_math.py`
  - scale normalization
  - temperature schedule
  - FTRL
  - contraction monitor
  - temporal credit
  - audit replay
  - streaming audit replay
  - Wasserstein drift
- `sre_self_envelope.py`
  - `OutcomeEvidence`
  - `LearnedSafetyEnvelope`
  - `ContractionAwareEnvelope`
  - `EnvelopeLearner`
  - `CreditAwareLabeler`
- `sre_metrics.py`
  - `PrometheusHTTPClient`
  - `PrometheusContextReader`
  - `OpenTelemetryJSONMetricReader`

### 3. Docs / Demos
- `docs/ARCHITECTURE.md`：架构图、requirements、task breakdown、refine
- `docs/SRE-CONTROL-PLAYBOOK.md`：SRE 控制原语手册
- `docs/SELF-LEARNING-ENVELOPE.md`：自学习 envelope 设计
- `docs/SOFT-LABEL-CREDIT.md`：soft label 与 credit-aware labeler
- `docs/AUDIT-CREDIT-REPLAY.md`：Audit JSONL -> temporal credit
- `docs/STREAMING-AUDIT-REPLAY.md`：增量 tail replay
- `docs/METRIC-SOURCES.md`：Prometheus / OpenTelemetry 接入
- `docs/knowledge-base.html`：单页知识库
- `examples/demo_*`：各机制可运行样例

## 当前闭环能力

### 已经闭上的链路
```text
WeightedConvexCombiner
  -> AuditTrail.to_jsonl()
  -> AuditCreditReplay / StreamingAuditCreditReplay
  -> TemporalCreditAssigner
  -> CreditAwareLabeler
  -> LearnedSafetyEnvelope
```

```text
Prometheus / OpenTelemetry JSON
  -> context dict
  -> WeightedConvexCombiner + AuditTrail
  -> replay + temporal credit
```

### 仍未闭上的链路
- 没有 HTTP 服务层
- 没有 SQLite / 外部 DB 持久化层
- 没有离线训练脚本产物 rollout 机制
- 没有完整的 collector 框架自动构造业务级 `ReleaseContext`
- Prometheus 目前是 instant query reader，不是长期 scrape / remote-read pipeline
- OpenTelemetry 目前解析 gauge / sum，不展开 histogram

这些缺口不应被写成“已经完成”。当前仓库的正确边界是：提供可复用核心原语，生产服务层需要另起 integration layer。

## 必须守住的不变量
- `WeightedConvexCombiner` 权重必须满足：
  - `sum(weights) == 1`
  - `floor <= weight <= ceiling`
- `AttentionResidual` 权重必须沿 layer axis softmax，`sum_k a_{l,k} == 1`
- `share_key=False` 必须保持 per-slot key bank 真实生效
- `LearnedSafetyEnvelope.fit()` 只能自动收紧，不能自动放宽
- `relax()` 是 envelope 唯一放宽路径
- learned bounds 永远不能越过 operator hard bounds
- `ContractionAwareEnvelope` 只能临时缩小 effective max_delta，不能污染 inner state
- `AuditTrail` 必须可 JSONL 回放
- streaming replay 只能消费 newline-complete JSONL 行，partial line 必须留在 `pending`
- soft label 只能调节 evidence 强度，不能绕过 hard bounds
- metric source 只负责读取指标并生成 context，不承载控制策略

## 验证命令
```bash
pytest -q
pytest tests/test_sre_metrics.py tests/test_sre_math.py tests/test_sre_self_envelope.py -q
python -m examples.demo_credit_aware_envelope
python -m examples.demo_audit_credit_replay
python -m examples.demo_streaming_audit_replay
python -m examples.demo_metric_source_replay
```

本次 handoff 更新前已执行：

```bash
pytest --collect-only -q
```

结果：收集 `154` 个测试。

## 风险与边界
1. Self-learning envelope 有 selection bias：只能学习已经被允许执行的动作。
2. Prometheus reader 当前只支持 instant query 的 `scalar` / `vector`，不支持 `matrix`。
3. OpenTelemetry reader 当前只解析 OTLP JSON 的 `gauge` / `sum`，未实现 histogram bucket 到 p95/p99 或 burn-rate 的转换。
4. Streaming replay 用 file size 判断截断；同大小 rotation 需要外部 inode / file identity 检查。
5. `sre_control` / `sre_math` / `sre_metrics` 应保持轻依赖，复杂服务编排、数据库、训练调度不应塞进这些模块。
6. knowledge-base 是手工维护 HTML，后续继续扩展时容易出现目录、章节编号或图示不同步。

## 下一步建议
1. 做一层 integration adapter，把发布记录、告警和指标统一转成 audit context 或更高层的控制输入。
2. 扩展 OpenTelemetry histogram 支持，把 bucket 转为 p95/p99 或 SLO burn loss。
3. 给 `CreditAwareLabeler` 增加最近窗口 credit cache，避免每次事故都全量 attribute。
4. 引入 per-dimension quorum，让不同 action 维度有不同 unsafe evidence 门槛。
5. 给 streaming replay 增加 cursor 持久化 helper，减少业务侧重复保存 offset 的样板代码。
6. 为 `knowledge-base.html` 做半自动目录与章节索引生成。

## 接手顺序
1. `docs/ARCHITECTURE.md`
2. `docs/SRE-CONTROL-PLAYBOOK.md`
3. `docs/AUDIT-CREDIT-REPLAY.md`
4. `docs/STREAMING-AUDIT-REPLAY.md`
5. `docs/METRIC-SOURCES.md`
6. `attention_residuals/sre_control.py`
7. `attention_residuals/sre_math.py`
8. `attention_residuals/sre_self_envelope.py`
9. `attention_residuals/sre_metrics.py`

## 提交前检查清单
- 新增 API 导出到 `attention_residuals/__init__.py`
- 新增代码有 deterministic tests
- 新增能力有 demo
- docs 与 knowledge-base 同步
- 不把服务化 runtime 误写进库级模块
