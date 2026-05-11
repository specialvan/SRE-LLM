# 02 · Decision Flow

`decide(ctx)` 一次调用的完整生命周期。本文是 review PR 时最常回来查的文档。

## 0. 调用前置（caller 责任）

1. 构造 `ReleaseContext`（含 service state、candidates、telemetry、dependencies、
   error_budget_remaining、freeze_window、correlation_id）
2. 调用 `pipeline.decide(ctx)`

Pipeline **永远同步返回** `Decision`，要么成功、要么抛 `GanError` 子类。
不会返回 `None`、不会 block 超过 lock 超时、不会在 decide 之后异步改状态。

## 1. 流程总览

```mermaid
flowchart TD
  START([decide(ctx) 入口]) --> V[1. validate ctx]
  V -->|DataError| E1([抛异常])
  V --> DEPS[2. setattr service._deps]
  DEPS --> BREAKER{3. circuit breaker 允许?}
  BREAKER -->|no| ESC1[返回 ESCALATE<br/>+ correlation_id]
  BREAKER -->|yes| LOCK[4. per-service lock 获取]
  LOCK -->|timeout| E2([抛 TimeoutError])
  LOCK --> LOCKED[5. _decide_locked]

  subgraph LOCKED_SUB["_decide_locked"]
    direction TB
    CID[with correlation_id] --> TRACE[初始化 trace]
    TRACE --> GUARD{6. guard clauses}
    GUARD -->|freeze| HOLD1[HOLD]
    GUARD -->|budget≤0| RB1[ROLLBACK]
    GUARD -->|pass| PCA[stage.pca]
    PCA --> SYN[stage.synergy]
    SYN --> ADJ[stage.adjusted_probs]
    ADJ --> ENT[stage.entropy]
    ENT -->|empty| HOLD2[HOLD]
    ENT --> EOMM[stage.eomm]
    EOMM --> RISK[stage.risk]
    RISK --> RESOLVE[resolve_decision]
    RESOLVE --> EMIT[_emit]
  end

  LOCKED --> BREAKER_UPDATE[breaker.record_success/failure]
  BREAKER_UPDATE --> FINALIZE[_finalize_decision]
  FINALIZE --> SHADOW[_shadow_wrap]
  SHADOW --> PERSIST[store.record_decision]
  PERSIST --> RETURN([返回 Decision])
```

## 2. 每个 stage 的契约

所有 stage 都遵循同一份契约：

| 契约项 | 要求 |
|---|---|
| **纯度** | 读写自己的 `trace["stages"][name]` + metrics，不修改 ctx 公开字段 |
| **超时** | 单 stage 不允许阻塞；数值失败用 `except Exception` 兜底 |
| **降级** | 失败时用保守默认值 + `stage_failures` counter + `stage.<name>.degraded` log |
| **可观测** | 必须 `with span(logger, "stage.<name>")`，latency 进 histogram |
| **时序** | 只能读上游 stage 的 trace，不能反向调用下游 |

### 2.1 stage.pca — Telemetry 压缩

- **输入**: `ctx.telemetry` (dict[str, float])
- **输出字段**:
  - `fused: float` — 当 telemetry 可用时是 `mu + β·||z||`；否则回落成 `mu`
  - `hidden_norm: float` — 隐藏向量范数（可选）
  - `keys: list[str]` — 被 PCA 看到的 telemetry key 顺序（审计用）
- **降级**: 如果 `fit` 抛异常 → 只填 `fused = mu`，`stage.pca.degraded` 日志
- **不变量**: `fused` 永远是 float，不会 NaN

### 2.2 stage.synergy — 依赖图得分

- **输入**: `self.synergy_graph`（hydrate 自 SQLite）+ `ctx.dependencies`
- **输出字段**:
  - `n_dependencies: int`
  - `score: float` — 当前服务与其依赖节点的嵌入内积平均
- **降级**: 节点不够或 GNN 异常 → `score = 0.0`
- **不变量**: `score` 是 float，即使图为空也有定义

### 2.3 stage.adjusted_probs — Dynamic K + Handicap

- **输入**: `ctx.service.win_streak`, `loss_streak`, `ctx.candidates[*].expected_success`,
  `canary_fraction`
- **输出字段**:
  - `penalty: float`
  - `probs: list[float]` — 每个候选的调整后成功概率
  - `k_factor: float`
- **不变量**: `probs` 长度等于 `ctx.candidates` 长度，每项 ∈ (0, 1)

### 2.4 stage.entropy — Information value 过滤

- **输入**: 上游 `probs`
- **输出字段**:
  - `entropies: list[float]`
  - `acceptable_idx: list[int]`
  - `min_entropy: float` — 当前阈值（来自 config）
  - `fallback_used: bool` — 如果所有候选都被过滤掉，用 argmax-H 兜底
- **短路**: 当 `fallback_used=False` 且 `acceptable_idx` 空时，pipeline 直接
  HOLD，不进入 EOMM
- **不变量**: `fallback_used=True` 时 `acceptable_idx` 至少 1 个

### 2.5 stage.eomm — 策略打分

- **输入**: `acceptable_idx`、history vector、candidate match configs
- **分支**:
  - **artifact 路径**: 当 `self.artifacts.retention is not None` 时走
    `RetentionModel.prob` + `EOMMMatcher.best`，带 `artifact_version` 和
    `candidate_scores`，日志源 `"artifact"`
  - **fallback 路径**: 其他情况走规则式线性打分，日志源 `"fallback"`
- **输出字段**:
  - `source: "artifact" | "fallback"`
  - `artifact_version: str` (仅 artifact 分支)
  - `chosen_id: str`
  - `chosen_score: float`
  - `acceptable_idx: list[int]`
  - `history: list[float]` — 用于事后校准
  - `candidate_scores: list[{candidate_id, score, strategy}]`
- **降级**: artifact 路径里任何异常都会翻到 fallback，同时 `stage_failures` 递增

### 2.6 stage.risk — Cox 风险预测

- **输入**: `build_risk_feature_vector(service, chosen, ctx)` — 6 维
- **输出字段**:
  - `features: list[float]`
  - `prob: float` — P(incident within horizon)
  - `level: "ok" | "warn" | "alarm"`
- **降级**: `ChurnRiskMonitor.predict` 异常 → `prob = 0.5`, `level = "warn"`
- **不变量**: `prob ∈ [0, 1]`, `level` 与 `prob` 由 `_sre_risk_level` 阈值表确定

### 2.7 _resolve_decision — 策略解析（policy engine）

这是唯一一个**纯策略**的步骤。不做计算、不碰 store、不写 metric，只做 if/else：

```
if risk_level == ALARM:
    if loss_streak >= 2: ROLLBACK
    else: HOLD
elif risk_level == WARN:
    CANARY
elif confidence < 0.5:
    CANARY
elif tier_critical and strategy != "canary":
    CANARY
elif strategy == "full":
    GO
elif strategy == "canary":
    CANARY
elif strategy in ("shadow", "holdback"):
    HOLD
else:
    ESCALATE
```

**这张表是整个系统最昂贵的契约**。改任何一条都必须：

1. 开 ADR 说明为什么改
2. 至少加一个 replay fixture 覆盖新分支
3. 如果是"变严"方向，可以合入；如果是"变松"方向，必须走 PR-5-XX 重级评审

## 3. emit & finalize

```python
def _emit(...) -> Decision:
    # 递增 metrics、写 decide.finished 日志、构造 Decision 对象（含 artifact_version）
    return decision

def _finalize_decision(self, decision):
    decision = self._shadow_wrap(decision)      # off / advisory / shadow
    if self.store is not None:
        self.store.observations.record_decision(decision)
    return decision
```

### 3.1 Shadow wrap 的三种模式

| mode | 行为 | trace 标记 |
|---|---|---|
| `off` | 原样返回 | 无 |
| `advisory` | 原样返回 + rationale 追加 "shadow_mode=advisory" | `trace.shadow_mode="advisory"` |
| `shadow` | `kind` 改写成 HOLD，原 kind 计入 `gan_shadow_diff_total` | `trace.shadow_mode="shadow"`, `trace.shadow_suppressed_kind` |

**⚠️ 当前已知不一致**（F-002）: `_emit` 里的 `gan_decisions_total` counter 用的是
**改写前的 kind**，但返回给 caller 的是改写后的 kind。见 [claude-review/findings.md](../claude-review/findings.md#f-002)。

## 4. 短路路径

以下场景**不会**走完全部 7 个 stage：

| 触发条件 | 决策结果 | stage trace |
|---|---|---|
| `ctx.freeze_window=true` | HOLD | 空 `trace.stages` |
| `ctx.error_budget_remaining ≤ 0` | ROLLBACK | 空 `trace.stages` |
| circuit breaker open | ESCALATE | 空 `trace.stages` + `trace.circuit_breaker` |
| entropy fallback 失败且 acceptable_idx 空 | HOLD | 只到 entropy |
| `ctx.validate()` 失败 | 抛 DataError (不产 Decision) | — |

## 5. 并发视角

一次 decide 的**串行保证**仅在 **同一 service_id + 同一进程** 内成立：

- `PerServiceLock` 锁粒度 = service_id，跨服务并行无阻塞
- `LeaseRefreshLoop`（如果启用）保证进程级单写者
- **不保证**跨进程 / 跨节点串行，见 [06-concurrency-and-leases.md](06-concurrency-and-leases.md)

## 6. 性能预算

| 阶段 | p50 观测 | p99 观测 | budget |
|---|---|---|---|
| 全链路 | 0.83 ms | 1.73 ms | 50 ms |
| 单 stage | < 0.2 ms | < 0.5 ms | 无硬 budget |

（数据来自 `python -m bench.latency --quick`, n=200, 2026-05）

47× 余量足以吸收：artifact 文件系统加载、SQLite 写入、未来的 JSON schema 演进、
一次远程 lease refresh。

## 7. 参考实现

- 入口：`gan_matchmaking/sre/self_iteration.py::SelfIterationPipeline.decide`
- Stage 实现：同文件 `_stage_*` 方法
- 策略表：同文件 `_resolve_decision` 方法
- 测试：`tests/test_sre_self_iteration.py`
- Replay 回归：`tests/test_replay_corpus.py` + `tests/fixtures/replay/*.json`
