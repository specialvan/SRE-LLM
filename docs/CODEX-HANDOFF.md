# Codex Handoff - Attention-Residuals

> 面向下一位 Codex 接手者的工程交接文档。本文只描述
> `D:\workspace\SRE-LLM\Attention-Residuals` 这条线，不混入其他子项目。

---

## ✅ 2026-05-12 · Round 10 关闭 + Round 11 首笔落地

Claude 已完成 Rounds 7–9（commits `ba8fad8` → `3dbfd50`）评审 + 7 条 follow-up 全部关闭，并已在 Round 11 内线落下第一块能力：

- **Verdict**: ✅ Approved · all follow-ups closed · Round 11 capability landed
- **Tests**: **174 / 174 passing**（154 baseline + 11 close-out + 9 OTLP histogram）
- **Diagnostics**: 0
- **Demos**: 11 / 11 runnable（`demo_metric_source_replay` 现在演示 histogram p50/p95）
- **Follow-ups**: 2 P1 + 2 P2 + 3 P3 = **7 / 7 closed**
- **ADRs**: 1 written（[ADR-0001](./adr/0001-contraction-wrapper-uses-rlock.md)）
- **Open gaps closed**: `otel_no_histogram_expansion`（详见 [state.json.closed_gaps](./V2_Knowledge/state.json)）

**Codex 下一步**：把未提交的工作树改动 + 本次 OTLP 扩展 push 上去。commit 切分建议见
[`docs/claude-review/04-midflight-review.md`](./claude-review/04-midflight-review.md) §7（再加一条 `feat(sre_metrics): OTLP histogram expansion`）。

### 如果你是第一次接手（没有未提交的本地代码）

所有 Round 10 工作都已收尾：

1. 拉最新代码 → `pytest -q` 预期 174 passing
2. 读 [`docs/V3_Knowledge/index.html`](./V3_Knowledge/index.html) 建立全貌（9 个 zone，含依赖图 + 闭环流 + changelog）
3. 或读 [`docs/V2_Knowledge/index.html`](./V2_Knowledge/index.html)（7 zone 精简版）
4. 下一轮若要继续深挖，看 V3 Z6 backlog 或 Round 11 opening template

### 如果你要开 Round 11 新评审

完整 checklist 与模板已落在 [`docs/claude-review/05-round-11-opening.md`](./claude-review/05-round-11-opening.md)。
执行顺序：pre-flight（归档 + regenerate + pytest 基线）→ 按模板填 06/07 → 刷新 V2 + HANDOFF。

**严禁破坏**：`docs/V2_Knowledge/state.json` 的 13 条 `hard_invariants`（详见 SSOT）。若必须破坏，先写 ADR 到 [`docs/adr/`](./adr/) 再动手。

---

## 当前状态（as of 2026-05-12, Round 10 closed）
- 工作目录：`D:\workspace\SRE-LLM\Attention-Residuals`
- 当前分支：`attention-residuals-session`
- 远端：`origin https://github.com/specialvan/SRE-LLM.git`
- 当前定位：库级 SRE 控制原语与 Attention Residuals 论文机制复用，**不是** HTTP 服务型 runtime
- 当前验证：`pytest -q` → **174 / 174 通过**（baseline 154 + codex 8 close-out + Claude 3 dead-letter cap + Claude 9 histogram）
- 评审状态：Round 10 **已关闭**（7/7 follow-ups closed），等待 codex 推送工作树改动
- V3 Knowledge Base：`docs/V3_Knowledge/index.html` 为最新 agent-first 导航（9 zone + 依赖图 + 闭环流 + changelog）
- V2 Knowledge Base：`docs/V2_Knowledge/index.html` 为精简版导航（7 zone）
- V1 Knowledge Base：`docs/knowledge-base.html` 为深度拆解版（27 节 + 30 SVG）

## 最近主线
- 修复 `AttentionResidual.share_key=False`，补齐 per-slot `W_K^{(k)}` ablation
- 修复 `AdaptiveCombiner` 的静态 bias 合成语义（`static + learner_logit`）
- 新增 soft label（`OutcomeEvidence`）+ temporal credit-aware labeler
- 新增 Audit JSONL 离线与流式 replay
- 新增 Prometheus / OpenTelemetry 指标源适配
- 更新 architecture、knowledge-base、GIF 和多份机制文档
- **完成 Claude Round 10 评审，输出 claude-review + V2_Knowledge**

---

## 项目本质
一句话概括：

> 它先把 Transformer 中"隐式纵向残差"显式化为可学习、可审计、受约束的 attention 结构，再把这套结构抽象成 SRE 控制工程中的"可学习但安全优先"的控制平面原语。

当前仓库不是完整生产服务。它提供的是可嵌入服务、任务、控制器或离线 replay job 的核心机制层。

---

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
  - `WeightedConvexCombiner` · `AuditTrail` · `DecoupledControlLoop`
  - `HierarchicalBlockController` · `BudgetGate` · `MustAttendRegistry`
- `sre_adaptive.py`
  - `HedgeRegretLearner` · `AdaptiveCombiner`
  - 静态 bias + learner logits，不能互相覆盖
- `sre_safety.py`
  - `SafetyEnvelope` · `ShadowRunner`
  - `CounterfactualExplainer` · `WeightDriftDetector`
- `sre_math.py`
  - scale normalization · temperature schedule · FTRL
  - contraction monitor · temporal credit
  - audit replay · streaming audit replay · Wasserstein drift
- `sre_self_envelope.py`
  - `OutcomeEvidence` · `LearnedSafetyEnvelope` · `ContractionAwareEnvelope`
  - `EnvelopeLearner` · `CreditAwareLabeler`
- `sre_metrics.py`
  - `PrometheusHTTPClient` · `PrometheusContextReader`
  - `OpenTelemetryJSONMetricReader`

### 3. Docs / Demos
- `docs/claude-review/` — **当前等待处理的评审反馈（最高优先级）**
- `docs/V2_Knowledge/` — **Agent-first 导航索引（推荐作为入口）**
- `docs/ARCHITECTURE.md`：架构图、requirements、task breakdown、refine
- `docs/SRE-CONTROL-PLAYBOOK.md`：SRE 控制原语手册
- `docs/SELF-LEARNING-ENVELOPE.md`：自学习 envelope 设计
- `docs/SOFT-LABEL-CREDIT.md`：soft label 与 credit-aware labeler
- `docs/AUDIT-CREDIT-REPLAY.md`：Audit JSONL -> temporal credit
- `docs/STREAMING-AUDIT-REPLAY.md`：增量 tail replay
- `docs/METRIC-SOURCES.md`：Prometheus / OpenTelemetry 接入
- `docs/knowledge-base.html`：V1 深度拆解单页知识库（27 节 / 30 SVG）
- `docs/DEEP-DIVE.md` / `docs/EQUATIONS-AND-SRE.md` / `docs/DESIGN.md` / `docs/FORMULA_MAP.md`
- `examples/demo_*`：11 个可运行样例

---

## 当前闭环能力

### 已闭上的链路
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

这些缺口不应被写成"已经完成"。当前仓库的正确边界是：**提供可复用核心原语，生产服务层需要另起 integration layer**。

---

## 必须守住的不变量

> **SSOT**: 权威来源是 [`docs/V2_Knowledge/state.json`](./V2_Knowledge/state.json) 的 `hard_invariants` 字段（13 条带 ID + enforced_at + primary_test）。
> `docs/V2_Knowledge/index.html` Z5 和 `docs/claude-review/README.md` §4 的 7 条 guardrails 都派生自它。
> 改动这里的清单前先改 state.json。

- **I-01** `WeightedConvexCombiner`: `sum(weights) == 1`
- **I-02** `WeightedConvexCombiner`: `floor <= weight <= ceiling`
- **I-03** `AttentionResidual`: 权重必须沿 layer axis softmax，`sum_k a_{l,k} == 1`
- **I-04** `share_key=False` 必须保持 per-slot key bank 真实生效
- **I-05** `LearnedSafetyEnvelope.fit()` 只能自动收紧，不能自动放宽
- **I-06** `relax()` 是 envelope 唯一放宽路径
- **I-07** learned bounds 永远不能越过 operator hard bounds
- **I-08** `ContractionAwareEnvelope` 只能临时缩小 effective max_delta，不能污染 inner state
- **I-09** `AuditTrail` 必须可 JSONL 回放且 append-only
- **I-10** streaming replay 只能消费 newline-complete JSONL 行，partial line 必须留在 `pending`
- **I-11** soft label 只能调节 evidence 强度，不能绕过 hard bounds
- **I-12** metric source 只负责读取指标并生成 context，不承载控制策略（tier 2）
- **I-13** `AdaptiveCombiner.step` 必须保持 `spec.bias = static_bias + learner.logits()`，learner 不能覆盖运维配置

**Tier 1**（I-01~I-11, I-13）违反即数据正确性崩溃，pytest 必然失败。
**Tier 2**（I-12）违反不一定立刻失败但会腐蚀架构边界，codex 需在 PR 描述里主动声明。

---

## 验证命令
```bash
# Core test suite
pytest -q                                     # 174/174 passing expected
pytest --collect-only -q                      # 174 tests collected (filter out tests/skill/)

# Specific suites (use when debugging a specific module)
pytest tests/test_sre_metrics.py tests/test_sre_math.py tests/test_sre_self_envelope.py -q

# Full demo sweep (see docs/V2_Knowledge/index.html Z4 for the fail-stop chain)
python -m examples.compare_residual_variants
python -m examples.demo_attn_residual
python -m examples.demo_block_attn_residual
python -m examples.demo_sre_autoscaler
python -m examples.demo_sre_math_primitives
python -m examples.demo_sre_adaptive_safety
python -m examples.demo_self_learning_envelope
python -m examples.demo_credit_aware_envelope
python -m examples.demo_audit_credit_replay
python -m examples.demo_streaming_audit_replay
python -m examples.demo_metric_source_replay

# Regenerate V2 state.json after an AI item closes
python docs/V2_Knowledge/_regenerate_state.py           # dry-run, see diff
python docs/V2_Knowledge/_regenerate_state.py --write   # persist
```

本次 handoff 更新前已执行：

```bash
python -m pytest tests\test_sre_math.py tests\test_sre_self_envelope.py tests\test_attn_residual.py tests\test_blocks.py tests\test_hyper_connections.py tests\test_norm.py tests\test_sre_adaptive.py tests\test_sre_control.py tests\test_sre_metrics.py tests\test_sre_safety.py tests\test_stack.py -q
```

结果：收集 **174** 个测试，全部通过（Round 10 close-out + Round 11 OTLP histogram expansion，2026-05-12）。

---

## 风险与边界
1. Self-learning envelope 有 selection bias：只能学习已经被允许执行的动作。
2. Prometheus reader 当前只支持 instant query 的 `scalar` / `vector`，不支持 `matrix`。
3. OpenTelemetry reader 当前只解析 OTLP JSON 的 `gauge` / `sum`，未实现 histogram bucket 到 p95/p99 或 burn-rate 的转换。
4. Streaming replay 用 file size 判断截断；同大小 rotation 需要外部 inode / file identity 检查。
5. `sre_control` / `sre_math` / `sre_metrics` 应保持轻依赖，复杂服务编排、数据库、训练调度不应塞进这些模块。
6. knowledge-base 是手工维护 HTML，后续继续扩展时容易出现目录、章节编号或图示不同步。
7. **Round 10 评审列出的 7 个 follow-up 已全部关闭**（details: `docs/claude-review/04-midflight-review.md` + `state.json.closed_actions`）：
   - ✅ P1 `TemporalCreditAssigner._history` 已有上限（default_window 10_000）
   - ✅ P1 `min_safe_samples` 在 soft label 下已拆分为 `min_safe_records` + `min_safe_evidence`
   - ✅ P2 `ContractionAwareEnvelope.apply` 默认 RLock（ADR-0001）
   - ✅ P2 Streaming replay 有 `skip_bad_lines` + `max_dead_letters` FIFO cap
   - ✅ P3 软标签双账记录 docstring 已补
   - ✅ P3 `_weighted_quantile` 空输入显式 raise
   - ✅ P3 `share_key=False` 在 DDP 下的 caveat 已在 docstring 指向 ARCHITECTURE.md

---

## 下一步建议

### 最近一轮（claude-review action items）
按 `docs/claude-review/02-action-items.md` 的 P1 → P2 → P3 顺序执行。

### 更远一点的方向
1. 做一层 integration adapter，把发布记录、告警和指标统一转成 audit context 或更高层的控制输入。
2. 扩展 OpenTelemetry histogram 支持，把 bucket 转为 p95/p99 或 SLO burn loss。
3. 给 `CreditAwareLabeler` 增加最近窗口 credit cache，避免每次事故都全量 attribute。
4. 引入 per-dimension quorum，让不同 action 维度有不同 unsafe evidence 门槛。
5. 给 streaming replay 增加 cursor 持久化 helper，减少业务侧重复保存 offset 的样板代码。
6. 为 `knowledge-base.html` 做半自动目录与章节索引生成。
7. Shadow envelope with policy gradient（Round 6 backlog #7.6）。
8. 跨服务 envelope 联邦（Round 6 backlog #7.7）。

---

## 接手顺序（agent-friendly 版本）

**第一次接手**请严格按此顺序：

1. [`docs/V2_Knowledge/index.html`](./V2_Knowledge/index.html) — 整体导航图，10 分钟建立全貌
2. [`docs/claude-review/README.md`](./claude-review/README.md) — 当前待处理反馈入口
3. [`docs/claude-review/02-action-items.md`](./claude-review/02-action-items.md) — 挑一条 P1 动手
4. [`docs/claude-review/01-detailed-architecture.md`](./claude-review/01-detailed-architecture.md) — 改代码时对照 invariant 序列

**深度研究**或复用机制时：

1. `docs/knowledge-base.html`（V1 深度版，27 节）
2. `docs/ARCHITECTURE.md`
3. `docs/DEEP-DIVE.md` / `docs/EQUATIONS-AND-SRE.md`
4. 对应模块源代码（`attention_residuals/sre_*.py`）

**生产接入**时：

1. `docs/METRIC-SOURCES.md`
2. `docs/SRE-CONTROL-PLAYBOOK.md`
3. `docs/SELF-LEARNING-ENVELOPE.md`
4. `docs/AUDIT-CREDIT-REPLAY.md` + `docs/STREAMING-AUDIT-REPLAY.md`
5. 对应 `examples/demo_*.py`

---

## 提交前检查清单
- [ ] 新增 API 导出到 `attention_residuals/__init__.py`
- [ ] 新增代码有 deterministic tests（mock time / RNG / I/O）
- [ ] 新增能力有 demo
- [ ] docs 与 knowledge-base（V1/V2）同步
- [ ] 不把服务化 runtime 误写进库级模块
- [ ] `pytest -q` 全绿
- [ ] `getDiagnostics` 无警告
- [ ] 如处理的是 claude-review action item，在对应文件里标注 `// closed by <commit-sha>`

---

## 变更日志（HANDOFF 级别）

| Date | By | What |
| --- | --- | --- |
| 2026-05-12 | Claude | Round 11 内线：OTLP histogram expansion（`OpenTelemetryJSONMetricReader(histogram_quantiles=, histogram_extras=)` + 公开 `quantile_from_histogram`）；+9 tests；demo_metric_source_replay 已演示 p50/p95；关闭 open_gap `otel_no_histogram_expansion` |
| 2026-05-12 | Claude | Round 11 opening kit：`docs/claude-review/05-round-11-opening.md` 模板 + V1 knowledge-base.html 同步 Round 10 签名（AI-2/3/4/5 体现到 §23/§24/§26） |
| 2026-05-12 | Claude | Round 10 close-out：AI-4 `max_dead_letters` 补丁 + RLock 注释 + AttentionResidual docstring 指针；ADR-0001 归档 RLock 决策；state.json 刷新 (165 tests, 0 open) |
| 2026-05-12 | Claude | Round 10 midflight review，新增 `docs/claude-review/04-midflight-review.md` + `docs/adr/` 目录 + ADR-0001 |
| 2026-05-12 | Codex | 本地实现 AI-1/2/3/5/6/7（6/7 条），测试从 154 涨到 162（未提交） |
| 2026-05-12 | Claude | Round 10 评审，新增 `docs/claude-review/` + `docs/V2_Knowledge/` |
| 2026-05-11 | Codex | Round 7/8/9，新增 soft labels / credit / audit replay / metric sources / streaming |
| 2026-05-11 | Codex | 修复 `AttentionResidual.share_key=False` 独立 key bank |
| 2026-05-11 | Codex | 修复 `AdaptiveCombiner` 静态 bias 合成；新增 ARCHITECTURE/HANDOFF |
| 2026-05-11 | Claude | Round 6，新增 `sre_self_envelope.py` + 自学习外壳 + 32 tests |
| 2026-05-11 | Claude | Round 5，新增 `sre_math.py` 7 条方程级原语 + 33 tests |
| 2026-05-11 | Claude | Round 4，新增 `sre_adaptive.py` + `sre_safety.py` 闭环学习与工业安全四锁 |
| 2026-05-11 | Claude | Round 3，新增 `sre_control.py` 7 条结构原语 + SRE 控制面 Playbook |
