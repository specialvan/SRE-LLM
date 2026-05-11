# 03 · Trace Schema

Trace 是系统最重要的产物之一，它让每一次决策都可以事后重放、对拍、审计。
本文定义 trace 的 **公开 schema** 和 **向后兼容规则**。

## 0. Where trace lives

```
SelfIterationPipeline.decide(ctx) → Decision.trace: dict[str, Any]
                                                      │
                                                      ├─ JSONL log line (stderr)
                                                      ├─ SQLite decisions.trace_json
                                                      └─ HTTP response body "trace"
```

三处是**同一份 trace**，字节对等。任何一处读到的 trace 都可以喂回
`test_replay_corpus.py` 做回归。

## 1. 顶层 schema

```jsonc
{
  "input": {                       // 复现用的完整输入快照
    "context": { /* ReleaseContext 公开字段 */ },
    "config":  { /* AppConfig.to_dict() */ }  // ⚠️ 见 F-003，未来要走 allowlist
  },
  "artifacts": {                   // 运行时 artifact 身份
    "version": "retention@abc...+cox@def..." | "bootstrap",
    "fitted": true | false,
    "retention": { /* metadata */ } | null,
    "cox":       { /* metadata */ } | null,
    "validation_errors": {         // 可选；manifest 校验失败时出现
      "retention": ["weights_dim=8 expected 6", ...],
      "cox":       [ ... ]
    }
  },
  "stages": {                      // 各 stage 输出
    "pca":             { /* 见 §2.1 */ },
    "synergy":         { /* 见 §2.2 */ },
    "adjusted_probs":  { /* 见 §2.3 */ },
    "entropy":         { /* 见 §2.4 */ },
    "eomm":            { /* 见 §2.5 */ },
    "risk":            { /* 见 §2.6 */ }
  },
  "shadow_mode": "off" | "shadow" | "advisory",        // 仅非 off 时出现
  "shadow_suppressed_kind": "go" | "canary" | ...,     // 仅 shadow 时出现
  "circuit_breaker": { "state": "...", ... }           // 仅熔断短路时出现
}
```

## 2. Stage 字段明细

### 2.1 trace.stages.pca

```jsonc
{
  "fused": 0.95,              // float, 必有, 范围 [0, 1+]
  "hidden_norm": 0.03,        // float, 可选（无 telemetry 时缺失）
  "keys": ["error_rate", "latency", ...]  // list[str], 可选
}
```

- `fused` 是 PCA 融合出的综合可靠性分数
- 只要有 `fused` 就是 stage 正常运行；异常时仍有 `fused` 但退化成 `ctx.service.mu`

### 2.2 trace.stages.synergy

```jsonc
{
  "n_dependencies": 2,        // int
  "score": 0.15               // float, 可能是 0.0（图太小时）
}
```

### 2.3 trace.stages.adjusted_probs

```jsonc
{
  "penalty": 15.2,
  "probs": [0.48, 0.52, 0.60],   // 长度 = ctx.candidates 长度
  "k_factor": 28.9
}
```

### 2.4 trace.stages.entropy

```jsonc
{
  "entropies": [0.99, 0.98, 0.84],
  "acceptable_idx": [0, 1],       // 可能与 fallback_used 组合
  "min_entropy": 0.9,
  "fallback_used": false          // true 时 acceptable_idx 来自 argmax
}
```

### 2.5 trace.stages.eomm

**artifact 分支**：
```jsonc
{
  "source": "artifact",
  "artifact_version": "abc123...",
  "chosen_id": "canary-5pct",
  "chosen_score": 0.78,
  "acceptable_idx": [0, 1],
  "history": [3.0, 0.0, 45.0, 12.3],
  "candidate_scores": [
    { "candidate_id": "canary-5pct", "score": 0.78, "strategy": "canary" },
    { "candidate_id": "full",        "score": 0.42, "strategy": "full" }
  ]
}
```

**fallback 分支**：
```jsonc
{
  "source": "fallback",
  "artifact_used": false,          // 是否试过 artifact 但失败
  "chosen_id": "canary-5pct",
  "chosen_score": 0.71,
  "acceptable_idx": [0, 1],
  "history": [3.0, 0.0, 45.0, 12.3],
  "candidate_scores": [ ... ]      // 同上
}
```

### 2.6 trace.stages.risk

```jsonc
{
  "features": [3.0, 0.0, 0.01, 0.003, 0.05, 0.15],  // 6 维，与 RISK_FEATURE_NAMES 对齐
  "prob": 0.32,
  "level": "warn"
}
```

## 3. 向后兼容契约

Trace 是**半公开 schema**。定义如下契约：

### 3.1 只加字段，不删字段

- ✅ 可以新增 `trace.stages.<existing>.<new_field>`
- ✅ 可以新增 `trace.<new_top_level_key>`
- ❌ 不能删除已有字段（即使看起来没用）
- ❌ 不能改字段语义（例如把 `score` 从 0..1 改成 log odds）

### 3.2 值语义的向后兼容

- 数值类型字段保持稳定：不可从 float 变 string
- 枚举字段保持稳定：`level` 永远在 `{ok, warn, alarm}` 内
- 如果确需引入新值，先在 ADR 记录，再上线

### 3.3 schema 快照测试

- 每次决策 trace 的 key 集合通过 `test_replay_corpus` 隐式检查
- 建议补一个 `test_trace_schema_snapshot` 显式冻结顶层 key 集合

### 3.4 弃用字段的策略

- 标 `deprecated` 但保留 6 个月
- 在 trace 里仍然填值（可以是占位）
- 在 `docs/architecture/03-trace-schema.md` 和 ADR 里公告
- 6 个月后才真正删

## 4. 用于 replay 的最小字段集

`tests/test_replay_corpus.py` 依赖的最小字段：

```jsonc
{
  "input": { "context": {...}, "config": {...} },
  "artifacts": { "version": "...", "fitted": true|false },
  "stages": {
    "eomm": { "source": "artifact"|"fallback" }
  }
}
```

只要这个最小集合稳定，已有 golden fixture 就不会崩。其它字段可以自由演进。

## 5. 敏感性 & 隐私

### 5.1 当前风险

- `input.config` 目前是 `AppConfig.to_dict()`，包含全部配置字段
- 未来加 Redis URL / token / DSN 时会泄漏到 SQLite 审计表
- 见 **F-003**

### 5.2 推荐演进

- `AppConfig.to_trace_dict()` 基于 allowlist
- `ObservabilityConfig.trace_config_allowed_keys` 作为开关
- 快照测试锁 allowlist

## 6. 与 metrics / logs 的关系

```mermaid
flowchart LR
  DECIDE[decide(ctx)] --> TRACE[Decision.trace]
  TRACE --> LOG[JSONL log:<br/>decide.finished event]
  TRACE --> METRIC[Prometheus counter:<br/>gan_decisions_total]
  TRACE --> DB[SQLite decisions.trace_json]
  TRACE --> HTTP[HTTP response body]
```

三路都是从 trace 派生，不允许**任一路独立构造数据**。这样可以保证事后
用 SQLite 复查时，日志和响应体说的是同一件事。

## 7. 参考实现

- 构造：`gan_matchmaking/sre/self_iteration.py::_decide_locked`
- 序列化：`gan_matchmaking/sre/domain.py::Decision.to_dict`
- 存储：`gan_matchmaking/persistence/sqlite.py::SQLiteObservationRepository.record_decision`
- 回放：`tests/test_replay_corpus.py`
