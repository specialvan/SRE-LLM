# 07 · Observability Contract

Observability 是 SRE 系统的"显像剂"。本系统的契约是：

> 任何人都能从 **三件物证**（metric、log、trace）的任意一件追溯到另一件。

这份文档定义这三件物证的完整目录和跨维度对应关系。

## 1. 三件物证 at a glance

| 物证 | 载体 | 留存 | 查询方式 |
|---|---|---|---|
| **Metric** | Prometheus `/metrics` | scrape 间隔内 | Grafana / PromQL |
| **Log** | stderr JSONL | 按部署策略（loki / stackdriver） | `jq '.correlation_id=="X"'` |
| **Trace** | `Decision.trace` dict | SQLite 永久 | `SELECT trace_json FROM decisions WHERE correlation_id=?` |

**共同 key**: `correlation_id`。任何告警、日志、决策审计行都带这个字段。
这是"跨三件物证追溯"的唯一根基。

## 2. Metrics Catalog

所有 metric 在 `gan_matchmaking/sre/self_iteration.py::__post_init__` 注册。

### 2.1 Counter

| 名称 | 类型 | Labels | 含义 |
|---|---|---|---|
| `gan_decisions_total` | counter | `kind`, `risk_level` | 总决策数 |
| `gan_stage_failures_total` | counter | `stage` | stage 级异常降级次数 |
| `gan_shadow_diff_total` | counter | `suppressed_kind` | shadow 模式下原 kind 被改写成 HOLD 的次数 |
| `gan_lease_refresh_failures_total` | counter | `reason` | lease refresh 失败次数；失败会使 `/readyz` 进入 not-ready |

### 2.2 Gauge

| 名称 | 类型 | Labels | 含义 |
|---|---|---|---|
| `gan_service_confidence` | gauge | `service_id` | `μ - 2σ`，服务可靠性置信下界 |
| `gan_breaker_state` | gauge | — | 0=closed, 1=half_open, 2=open |

### 2.3 Histogram

| 名称 | 类型 | Labels | 含义 |
|---|---|---|---|
| `gan_stage_latency_seconds` | histogram | `stage` | 每个 stage 耗时 |

### 2.4 关键告警规则（示例 PromQL）

```promql
# 决策突然全变 ROLLBACK/HOLD（可能在误封）
rate(gan_decisions_total{kind=~"rollback|hold"}[5m])
  / ignoring(kind) rate(gan_decisions_total[5m]) > 0.5

# 某服务置信度骤降
gan_service_confidence < 0.5

# Breaker 开着
gan_breaker_state == 2

# Stage 失败率高
rate(gan_stage_failures_total[5m]) > 0.01

# Lease 续租失败
increase(gan_lease_refresh_failures_total[1m]) > 0
```

### 2.5 当前指标语义

`gan_decisions_total` 记录最终 enforced kind。shadow 模式下原 kind 被改写为
`HOLD` 时，`gan_shadow_diff_total{suppressed_kind=...}` 记录被压制的原始 kind。

## 3. Logs Catalog

### 3.1 日志格式

```jsonc
{
  "ts": "2026-05-10T12:34:56.789Z",
  "level": "INFO",
  "logger": "gan.sre.pipeline",
  "event": "<event_name>",
  "correlation_id": "<16 hex chars>",
  "payload": { /* 事件具体字段 */ }
}
```

### 3.2 事件目录

| Event | Level | Payload 关键字段 | 触发点 |
|---|---|---|---|
| `decide.started` | INFO | service_id, n_candidates, freeze_window | `decide()` 入口 |
| `decide.finished` | INFO | kind, risk_level, risk_prob, confidence, service_id, chosen_id, artifact_version | `_emit()` |
| `decide.short_circuited` | WARN | service_id, breaker | circuit open |
| `span.started` / `span.finished` / `span.failed` | INFO/WARN | span (stage 名), elapsed_ms, ok | `with span(...)` |
| `artifacts.loaded` | INFO | artifact_version, fitted | 启动 hydrate 成功 |
| `artifacts.retention.shape_mismatch` | WARN | expected_shape, got_shape | retention hydrate 失败 |
| `artifacts.retention.degraded` | WARN | error_type | retention 加载异常 |
| `artifacts.cox.shape_mismatch` | WARN | expected_dim, got_shape | cox hydrate 失败 |
| `artifacts.cox.degraded` | WARN | error_type | cox 加载异常 |
| `artifacts.recent_observations.degraded` | WARN | service_id, error_type | 读 observations 失败 |
| `stage.<name>.degraded` | WARN | error_type | 具体 stage 异常 |
| `http.listening` | INFO | host, port | HTTP server 启动 |
| `lease.refresh.failed` | ERROR | lease_path, owner, error_type | lease refresh failure callback |
| `decide.shadow_rewritten` | INFO | original_kind, final_kind, correlation_id | shadow 模式改写决策 |

### 3.3 日志级别契约

- **DEBUG**: 默认不开；仅本地调试
- **INFO**: 正常流程事件，必须带 `event` 字段
- **WARNING**: 降级 / 兜底发生，不影响 caller 拿到决策
- **ERROR**: 决策无法返回，或状态一致性有风险

## 4. Trace Catalog

见 [`03-trace-schema.md`](03-trace-schema.md) 的完整 schema。这里只列
**给告警 / 查询用**的常用 JSON path：

| JSON path | 含义 | 用途 |
|---|---|---|
| `kind` | 最终决策 | 匹配告警 |
| `artifact_version` | 模型身份 | 区分 code vs model drift |
| `trace.stages.eomm.source` | artifact / fallback | 排查 retention 为啥没生效 |
| `trace.stages.risk.prob` | Cox 给出的风险 | 事后分析 |
| `trace.artifacts.validation_errors` | artifact 校验错误 | 排查降级原因 |
| `trace.shadow_mode` | shadow / advisory / off | 确认是否在生产模式 |
| `trace.circuit_breaker.state` | 熔断状态（短路时才有） | 事故还原 |

## 5. 三件物证的关联查询

### 5.1 Metric → Log

Prometheus alert 触发后怎么找日志？

1. Alert payload 不包含 `correlation_id`（metric 是聚合的）
2. **按时间窗口 + label 维度**去 loki / stackdriver 查：
   ```
   {logger="gan.sre.pipeline", event="decide.finished", kind="rollback"}
   | time_window="last 5 minutes"
   ```
3. 拿到若干 correlation_id 后，进入下一步

### 5.2 Log → Trace

```sql
-- SQLite 里精确查
SELECT trace_json FROM decisions WHERE correlation_id = 'abc123def456...';
```

或者 HTTP:

```
GET /v1/decisions/<correlation_id>        # 🟡 **尚未实现**，建议开
```

### 5.3 Trace → Metric

从 trace 拿到 `artifact_version / kind / risk_level` 反推在 Grafana 上选
对应时段的 panel。

## 6. 可观测性成熟度评估

| 维度 | 目标 | 现状 |
|---|---|---|
| Correlation ID 贯穿 | 100% HTTP/CLI/内部调用 | ✅ 已达标 |
| 所有决策可回放 | Bootstrap + fitted 均可回放 | ✅ 已达标 |
| Stage 失败可归因 | 每个 stage 有独立 counter + 降级日志 | ✅ 已达标 |
| Metric 与决策语义一致 | 指标反映实际下发 | ✅ 已达标 |
| 敏感字段脱敏 | 默认不把 secret 写进 trace | ✅ 已达标 |
| Lease / breaker 可观测 | 所有状态暴露为 metric + log | ✅ 已达标 |

## 7. 建议补强

按优先级排：

1. **主动新增**：`GET /v1/decisions/<id>` 端点，便于 on-call 手动查
2. **主动新增**：`trace_id` 与 OpenTelemetry 对齐（当前只有 correlation_id）
3. **主动新增**：将 lease readiness / breaker / shadow 改写 dashboard 化

## 8. 参考

- 代码：`core/logging.py`, `core/metrics.py`, `core/tracing.py`,
  `sre/self_iteration.py`
- 架构：[`03-trace-schema.md`](03-trace-schema.md),
  [`04-state-and-failure-domains.md`](04-state-and-failure-domains.md)
- Findings：[`../claude-review/findings.md`](../claude-review/findings.md)
