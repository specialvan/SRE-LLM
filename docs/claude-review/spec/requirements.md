# Requirements · B+A2 本轮

EARS-A2 简化句式：`WHEN <trigger> THE SYSTEM SHALL <observable behavior>`。
可选补充 `AND <additional assertion>` 连接多项。

每条 R-XXX 后面跟着：**finding**、**验证手段**、**反例**（不满足时会发生什么）。

---

## F-001 · Lease refresh 失败可见化

### R-001 · Readiness 反应

**WHEN** `LeaseRefreshLoop` 后台线程中 `self.lease.refresh()` 抛出任意异常,
**THE SYSTEM SHALL** 在 `interval + 2s` 之内将 lease-healthy 状态标记为 false,
**AND** 使 `DecisionApp.handle_ready()` 返回 `(503, {"status":"not_ready",...})`,
**AND** 在响应体的 `details` 字段或等价位置包含触发异常的 class name。

- finding: [F-001](../findings.md#f-001--leaserefreshloop-续租失败静默化)
- 验证: `tests/test_leases.py::test_refresh_failure_flips_readiness`
- 反例（当前行为）: 主循环继续接收请求并写 SQLite，另一个 pod 可以接管 lease → split-brain。

### R-002 · Metric 可观测

**WHEN** lease refresh 失败,
**THE SYSTEM SHALL** 将 `gan_lease_refresh_failures_total{reason=<exception class name>}` 计数器递增 1,
**AND** 该指标在 `GET /metrics` 的 Prometheus 输出中可见。

- finding: F-001
- 验证: `tests/test_leases.py::test_refresh_failure_increments_metric`
- 反例: 事件只留在进程内存，Grafana 告警无法触发。

### R-003 · 结构化日志事件

**WHEN** lease refresh 失败,
**THE SYSTEM SHALL** 发出一条 ERROR 级 JSONL 日志,
**AND** 日志事件名为 `lease.refresh.failed`,
**AND** 日志 payload 至少包含 `lease_path`、`owner`、`error_type` 三个字段。

- finding: F-001
- 验证: `tests/test_leases.py::test_refresh_failure_emits_structured_log`
- 反例: 事后排查只能看 stack trace 碎片。

### R-004 · 幂等与非破坏性

**WHEN** readiness 已经翻转为 false（即刚发生过 refresh 失败）,
**THE SYSTEM SHALL** 继续让后续 `handle_health()` 调用返回 200（liveness 不受影响）,
**AND** 不重复发出 `lease.refresh.failed` 日志（避免 log storm）,
**AND** 不让 metric 在单次失败事件上递增多次。

- finding: F-001（衍生要求）
- 验证: `tests/test_leases.py::test_refresh_failure_does_not_spam`
- 反例: log pipeline 被淹、alertmanager 频繁 flap。

### R-005 · `# pragma: no cover` 被移除

**WHEN** F-001 修复 PR 合入,
**THE SYSTEM SHALL** 在 `gan_matchmaking/sre/leases.py::LeaseRefreshLoop._run()`
中不再包含 `# pragma: no cover - surfaced by ``error``.` 注释,
**AND** 覆盖率工具能统计到该分支被 R-001/R-002/R-003 测试实际执行。

- finding: F-001（技术债清理）
- 验证: `grep -n "pragma: no cover" gan_matchmaking/sre/leases.py` 返回空。

---

## F-002 · Shadow rewrite 后监控与决策一致

### R-101 · 指标反映 enforced kind

**WHEN** `shadow_mode=shadow` 且 `_resolve_decision` 原始产出 kind `K_original != HOLD`,
**THE SYSTEM SHALL** 使 `gan_decisions_total{kind="hold"}` 的计数反映**最终下发**的 kind,
**AND** **不**使 `gan_decisions_total{kind=K_original}` 递增。

- finding: [F-002](../findings.md#f-002--shadow-rewrite-导致监控日志与最终决策不一致)
- 验证: `tests/test_sre_self_iteration.py::test_shadow_mode_metric_reflects_enforced_kind`
- 反例（当前行为）: shadow 期间 rollback kind 计数虚增，告警规则误触发。

### R-102 · Shadow diff metric 保留原 kind

**WHEN** `shadow_mode=shadow` 抑制了一个非 HOLD 决策,
**THE SYSTEM SHALL** 使 `gan_shadow_diff_total{suppressed_kind=K_original}` 递增 1,
**AND** 该指标的总和等于"被抑制的非 HOLD 决策总数"。

- finding: F-002
- 验证: `tests/test_sre_self_iteration.py::test_shadow_mode_suppressed_kind_counter`
- 反例: 无法回答"本来会有多少次 rollback"。

### R-103 · Decision finished 日志一致性

**WHEN** shadow rewrite 生效,
**THE SYSTEM SHALL** 让 `decide.finished` 日志事件里的 `kind` 字段等于 **最终下发** 的 kind（HOLD）,
**AND** 发出一条额外的 `decide.shadow_rewritten` INFO 级日志事件，payload 至少包含
`original_kind`、`final_kind`、`correlation_id` 三字段。

- finding: F-002
- 验证: `tests/test_sre_self_iteration.py::test_shadow_mode_emits_rewrite_event`
- 反例: loki 按 `event=decide.finished kind=rollback` 查询得到 N 条，但
  SQLite 审计只有 0 条对应 rollback。

### R-104 · Trace 可回溯原 kind

**WHEN** shadow rewrite 生效,
**THE SYSTEM SHALL** 使 `Decision.trace["shadow_mode"] == "shadow"`
**AND** `Decision.trace["shadow_suppressed_kind"] == K_original.value`。

- finding: F-002
- 验证: 已有 `_shadow_wrap` 的现有契约（此条为回归保护，写快照测试）
- 反例: on-call 无法回溯"本来系统想怎么做"。

### R-105 · Off / advisory 不受影响

**WHEN** `shadow_mode ∈ {off, advisory}`,
**THE SYSTEM SHALL** 保持现有 `gan_decisions_total` 语义不变,
**AND** 不发出 `decide.shadow_rewritten` 日志事件。

- finding: F-002（回归保护）
- 验证: `tests/test_sre_self_iteration.py::test_off_mode_unaffected_by_shadow_fix`
- 反例: 修复 shadow 同时伤到 production-enforce 路径。

---

## F-003 · Trace 配置 allowlist

### R-201 · Allowlist 生效

**WHEN** `SelfIterationPipeline._decide_locked` 构造 `trace["input"]["config"]`,
**THE SYSTEM SHALL** 使该字段的键集合严格等于
`AppConfig.trace_allowlist()` 返回的白名单,
**AND** 不包含任何未显式允许的子字段。

- finding: [F-003](../findings.md#f-003--traceinputconfig-无-allowlist未来易泄密)
- 验证: `tests/test_trace_privacy.py::test_trace_config_only_allowlisted_keys`
- 反例: 未来加 `redis_url` / `api_token` 字段会立即泄漏进 SQLite 审计行。

### R-202 · Snapshot 测试锁白名单

**WHEN** 开发者向 `AppConfig` 或其任何子 config 新增字段,
**THE SYSTEM SHALL** 通过一条 snapshot 测试在未显式更新白名单时失败,
**AND** 测试失败信息指向 `AppConfig.trace_allowlist()` 的定义位置。

- finding: F-003
- 验证: `tests/test_trace_privacy.py::test_trace_config_allowlist_snapshot`
- 反例: 字段被安静加入 config 又被安静写进 trace，review 时发现不了。

### R-203 · 现有 replay fixture 兼容

**WHEN** R-201 上线后跑 `tests/test_replay_corpus.py`,
**THE SYSTEM SHALL** 使所有现存 fixture 仍通过,
**OR** fixture 被明确标记为因 allowlist 收紧而需要重录（列入 task）。

- finding: F-003（兼容性）
- 验证: `pytest tests/test_replay_corpus.py -v`
- 反例: 8 个 fixture 批量失败，无法区分是这次改动还是别的破坏。

### R-204 · Trace 可见字段记录性足够

**WHEN** allowlist 生效,
**THE SYSTEM SHALL** 至少保留以下字段在 `trace.input.config` 里：
`seed`、`observability.log_level`、`entropy.min_entropy`、
`survival.warn_threshold`、`survival.alarm_threshold`、`artifacts.directory`,
**AND** 事后 replay / 审计能基于这些字段复现决策分支。

- finding: F-003（功能保留）
- 验证: 同 R-203 的 replay 能通过即算满足
- 反例: allowlist 收太严，replay 失去意义。

---

## 共同契约（本轮不放宽）

- 所有新增测试必须是 **deterministic**（不能依赖 sleep、不能依赖真实时钟 > `monkeypatch` / fake `now`）
- 所有新增日志事件必须用 `JsonLineLogger`，不允许 `print` 或 `logging.info` 直调
- 所有新增 metric 必须在 `__post_init__` 内注册，标签基数受控
- 本轮 PR 禁止改动现有 `trace["stages"]["*"]` 的字段语义（只加不删见
  [`docs/architecture/03-trace-schema.md`](../../architecture/03-trace-schema.md)）

---

## 需求编号与 finding 的反查

| requirement | finding | 关联测试文件 |
|---|---|---|
| R-001 ~ R-005 | F-001 | `tests/test_leases.py` |
| R-101 ~ R-105 | F-002 | `tests/test_sre_self_iteration.py` |
| R-201 ~ R-204 | F-003 | `tests/test_trace_privacy.py` + `tests/test_replay_corpus.py` |
