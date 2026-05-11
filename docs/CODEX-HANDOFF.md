# Codex Handoff - Attention-Residuals

> 面向下一位接手者的工程交接文档。本文记录当前分支、已完成能力、关键不变量、验证方式、已知风险和下一步建议。

## 1. 当前状态

- 工作目录：`D:\workspace\SRE-LLM\Attention-Residuals`
- 当前分支：`attention-residuals-session`
- 远端：`origin https://github.com/specialvan/SRE-LLM.git`
- 当前验证：`pytest -q` 全量通过，当前测试收集数为 `154`。
- 主要新增方向：
  - Round 7：软标签 + temporal credit 归因修正。
  - Round 8：`AuditTrail.to_jsonl()` 离线回放到 `TemporalCreditAssigner`。
  - Round 9：Prometheus / OpenTelemetry 指标源适配，真实指标进入 audit context。
  - Round 10：streaming audit replay，增量 tail JSONL 并持续更新 temporal credit。

## 2. 架构地图

### 2.1 论文机制实现层

- `classic_residual.py`：经典残差 `x + F(x)`。
- `norm.py`：Pre-Norm / Post-Norm。
- `hyper_connections.py`：HC / mHC 多通道残差。
- `attn_residual.py`：核心 Attention Residual。
- `blocks.py`：Block Attention Residuals。
- `multi_head_vertical.py`：多头纵向注意力。
- `layer_skip.py`：动态跳层门控。
- `transformer_layer.py`：横向 MHA + 纵向 AttnRes 解耦层。
- `stack.py`：统一残差策略入口。

### 2.2 SRE 控制工程层

- `sre_control.py`：凸组合控制器、审计轨迹、分层控制、预算门控、must-attend 注册表。
- `sre_adaptive.py`：Hedge / regret learner，自适应 bias。
- `sre_safety.py`：静态安全 envelope、shadow runner、反事实解释、权重漂移检测。
- `sre_math.py`：尺度归一、温度退火、FTRL、Jacobian 监控、temporal credit、Wasserstein 漂移、audit replay。
- `sre_self_envelope.py`：自学习 safety envelope、软标签、credit-aware labeler。
- `sre_metrics.py`：Prometheus / OpenTelemetry 指标源适配。

### 2.3 文档与 demo

- `docs/knowledge-base.html`：机制级知识库，当前包含 `s0` 到 `s26`。
- `docs/SRE-CONTROL-PLAYBOOK.md`：SRE 控制原语复用手册。
- `docs/SELF-LEARNING-ENVELOPE.md`：自学习 envelope 设计。
- `docs/SOFT-LABEL-CREDIT.md`：软标签与归因修正。
- `docs/AUDIT-CREDIT-REPLAY.md`：audit JSONL 回放到 temporal credit。
- `docs/STREAMING-AUDIT-REPLAY.md`：audit JSONL 增量 tail cursor 与 rotation 策略。
- `docs/METRIC-SOURCES.md`：Prometheus / OpenTelemetry 指标源接入。
- `examples/demo_credit_aware_envelope.py`：软标签 + credit-aware labeler。
- `examples/demo_audit_credit_replay.py`：Audit JSONL 离线归因回放。
- `examples/demo_streaming_audit_replay.py`：Audit JSONL tail 增量归因回放。
- `examples/demo_metric_source_replay.py`：指标源 -> audit context -> temporal credit。

## 3. Round 7：软标签 + 归因修正

核心文件：

- `attention_residuals/sre_self_envelope.py`
- `tests/test_sre_self_envelope.py`
- `examples/demo_credit_aware_envelope.py`
- `docs/SOFT-LABEL-CREDIT.md`

新增能力：

- `OutcomeEvidence(safety_score, confidence)`：
  - `safe_evidence = safety_score * confidence`
  - `unsafe_evidence = (1 - safety_score) * confidence`
- `LearnedSafetyEnvelope.observe(...)` 兼容旧的 `OutcomeLabel` 与新的 `OutcomeEvidence`。
- SAFE 样本使用加权分位数学习边界，低置信 outlier 不会轻易拖动 envelope。
- UNSAFE quorum 改成累计 evidence mass，不再按裸事件数机械触发。
- `CreditAwareLabeler` 使用 `TemporalCreditAssigner` 的 blame 分布削弱外因事故的 UNSAFE 证据。

关键 demo 现象：

- traffic 导致的硬 `UNSAFE` 被降成弱 unsafe evidence。
- controller 导致的 `UNSAFE` 保持高 evidence，并触发 envelope 收紧。

## 4. Round 8：Audit JSONL 回放

核心文件：

- `attention_residuals/sre_math.py`
- `tests/test_sre_math.py`
- `examples/demo_audit_credit_replay.py`
- `docs/AUDIT-CREDIT-REPLAY.md`

新增能力：

- `MetricLossSpec`：把 audit context 中的指标转成非负 loss。
- `MetricLossMapper`：按 signal name 生成 loss 向量。
- `AuditCreditReplay`：
  - `replay_record(record)`
  - `replay_records(records)`
  - `replay_jsonl(text)`
  - `replay_jsonl_file(path)`

完整链路：

```text
AuditTrail.to_jsonl()
  -> AuditCreditReplay
  -> TemporalCreditAssigner
  -> CreditAwareLabeler
  -> LearnedSafetyEnvelope
```

## 5. Round 9：指标源接入

核心文件：

- `attention_residuals/sre_metrics.py`
- `tests/test_sre_metrics.py`
- `examples/demo_metric_source_replay.py`
- `docs/METRIC-SOURCES.md`

新增能力：

- `PrometheusHTTPClient`：标准库实现的 Prometheus instant query client。
- `PrometheusContextReader`：把一组 Prometheus query 读成 audit context。
- `PrometheusQuery`：声明 `context_key / query / reducer`。
- `OpenTelemetryJSONMetricReader`：解析 OTLP JSON export 中的 gauge / sum datapoints。
- `reduce_points`：支持 `first / sum / max / min / avg / callable`。

完整链路：

```text
Prometheus / OpenTelemetry
  -> context dict
  -> WeightedConvexCombiner + AuditTrail
  -> AuditCreditReplay + MetricLossMapper
  -> TemporalCreditAssigner
  -> CreditAwareLabeler + LearnedSafetyEnvelope
```

## 6. Round 10：Streaming audit replay

核心文件：

- `attention_residuals/sre_math.py`
- `tests/test_sre_math.py`
- `examples/demo_streaming_audit_replay.py`
- `docs/STREAMING-AUDIT-REPLAY.md`

新增能力：

- `AuditReplayCursor`：记录 `path / offset / pending / resets`，作为 JSONL tail 的最小状态，可由外部持久化后传回 tailer。
- `StreamingAuditCreditReplay.poll()`：
  - 从上次 byte offset 后读取新增内容；
  - 只回放 newline-complete JSONL 行；
  - 将尾部 partial line 保存在 `pending`；
  - 检测文件截断并 reset cursor；
  - `missing_ok=True` 时缺失文件返回 `0`，适合 watcher 启动早于日志创建的场景。

完整链路：

```text
AuditTrail append JSONL
  -> StreamingAuditCreditReplay.poll()
  -> AuditCreditReplay.replay_record()
  -> TemporalCreditAssigner
  -> CreditAwareLabeler / incident ranking
```

## 7. 必须守住的不变量

- `WeightedConvexCombiner` 权重必须满足：
  - `sum(weights) == 1`
  - `floor <= weight <= ceiling`
- `LearnedSafetyEnvelope.fit()` 只能自动收紧，不能自动放宽。
- `relax()` 是唯一放宽 envelope 的路径。
- learned bounds 永远不能越过 operator hard bounds。
- `ContractionAwareEnvelope` 只能临时缩小 effective max_delta，不能污染 inner envelope 状态。
- `AuditTrail` 必须可 JSONL 回放。
- Streaming replay 只能消费完整 JSONL 行，partial line 必须留在 `pending`。
- 软标签只能调节 evidence 强度，不能绕过 hard bounds。
- 指标源适配层只负责读指标并生成 context，不承载控制策略。

## 8. 验证命令

```bash
pytest -q
pytest tests/test_sre_metrics.py tests/test_sre_math.py tests/test_sre_self_envelope.py -q
python -m examples.demo_credit_aware_envelope
python -m examples.demo_audit_credit_replay
python -m examples.demo_streaming_audit_replay
python -m examples.demo_metric_source_replay
```

当前已验证：

- `pytest -q` 全量通过。
- `pytest --collect-only` 收集 `154` 个测试。
- `docs/knowledge-base.html` section 与 svg 闭合数一致。
- 四个 Round 7/8/9/10 demo 均可运行。

## 9. 已知风险与边界

- Self-learning envelope 仍然受 selection bias 限制：它只能学习已经被允许执行的动作。
- Prometheus reader 当前支持 instant query 的 `scalar` 和 `vector`，不支持 `matrix`。
- OpenTelemetry reader 当前解析 OTLP JSON 的 `gauge` 与 `sum`，没有实现 histogram 展开。
- Metric source demo 使用 fake transport 和 synthetic OTLP payload，不是生产 trace。
- Streaming replay 目前用 file size 判断截断；同大小 rotation 需要外层 inode / file identity 检查。
- `sre_control` / `sre_math` / `sre_metrics` 保持轻依赖，适合控制面；复杂训练逻辑仍不应塞进这些模块。

## 10. 下一步建议

1. 给 `CreditAwareLabeler` 增加“最近 N 秒 credit cache”接口，避免每次事故都全量 attribute。
2. 扩展 OpenTelemetry histogram 支持，把 bucket 转成 p95/p99 或 SLO burn loss。
3. 做一版真实 Prometheus 配置示例：autoscaling / rate-limit / circuit-break 三种场景各一套 query。
4. 引入 per-dimension quorum：不同 action 维度可以有不同的 unsafe evidence 门槛。
5. 给 streaming replay 增加一层 cursor 持久化文件 helper，减少业务侧重复保存 offset 的样板代码。

## 11. 提交前检查清单

- 新增 API 已导出到 `attention_residuals/__init__.py`。
- 新增代码均有单元测试。
- 新增能力均有 demo。
- README 与知识库入口已更新。
- 本文件已更新到最新状态。
