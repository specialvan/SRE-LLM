# Implementation Plan · B+A2 本轮

本文是唯一的 **编码活动** 清单。每条任务：

- 有唯一 task id（`T-XXX`）
- 显式引用需满足的 requirement id（`R-XXX`，来自
  [`requirements.md`](requirements.md)）
- 只命名要改的文件 / 符号 / 测试函数
- 不涉及审阅 / 状态更新 / 报告撰写（那些在本文末尾的「验收与收尾」中
  单独列出，不在编码活动内）

PR 依赖：`PR-fix-01` → `PR-fix-02` → `PR-fix-03`。三者代码路径不冲突，但
推荐顺序合入（F-001 是合入前 blocker）。

---

## PR-fix-01 · LeaseRefreshLoop 可见化续租失败

> 满足的 requirements: **R-001 / R-002 / R-003 / R-004 / R-005**

### T-101 · 给 LeaseRefreshLoop 加 on_failure 回调参数

- 文件: `gan_matchmaking/sre/leases.py`
- 符号: `LeaseRefreshLoop.__init__`
- 动作: 在签名新增关键字参数
  `on_failure: Optional[Callable[[BaseException], None]] = None`，保存为
  实例字段 `self.on_failure`
- 参考补丁: [`../patches/F-001-lease-refresh.md`](../patches/F-001-lease-refresh.md)
- Requirement: R-001 / R-002

### T-102 · 续租失败时调用 on_failure 并移除 pragma

- 文件: `gan_matchmaking/sre/leases.py`
- 符号: `LeaseRefreshLoop._run`
- 动作:
  1. `except BaseException as exc` 分支内在 `self.error = exc` 之后、
     `self._stop.set()` 之前，新增：
     ```python
     if self.on_failure is not None:
         try:
             self.on_failure(exc)
         except Exception:
             pass
     ```
  2. 删除 `# pragma: no cover - surfaced by ``error``.` 注释
- Requirement: R-001 / R-005

### T-103 · DecisionApp 新增 lease-healthy 状态字段

- 文件: `gan_matchmaking/service/app.py`
- 符号: `DecisionApp` dataclass
- 动作:
  1. 文件顶部新增辅助函数 `_make_healthy_event()` 返回 already-set
     的 `threading.Event`
  2. `DecisionApp` 新增 4 个 `field(..., init=False)` 字段：
     - `_lease_healthy: threading.Event` (factory = `_make_healthy_event`)
     - `_lease_unhealthy_details: dict = field(default_factory=dict, init=False)`
     - `_lease_path: Optional[str] = field(default=None, init=False)`
     - `_lease_owner: Optional[str] = field(default=None, init=False)`
- Requirement: R-001

### T-104 · 注册 lease refresh failures counter

- 文件: `gan_matchmaking/service/app.py`
- 符号: `DecisionApp.__post_init__` (新增或扩展现有 `__post_init__`)
- 动作: 在 metrics registry 上注册
  ```python
  self.m_lease_refresh_failures = self.pipeline.metrics.counter(
      "gan_lease_refresh_failures_total",
      "Number of lease refresh failures seen by the HTTP service.",
      label_names=("reason",),
  )
  ```
- 注意: `DecisionApp` 已有 `_lock: threading.Lock` 字段（参见补丁
  文档），新增字段应放在其附近，保持 init=False 字段集中
- Requirement: R-002

### T-105 · 实现 bind_lease_metadata 方法

- 文件: `gan_matchmaking/service/app.py`
- 符号: `DecisionApp.bind_lease_metadata(self, *, path: str, owner: str) -> None`
- 动作: 新增方法，填充 `self._lease_path` 和 `self._lease_owner` 两字段。
  放在 `handle_get_service` 之后
- Requirement: R-003

### T-106 · 实现幂等的 mark_lease_unhealthy 方法

- 文件: `gan_matchmaking/service/app.py`
- 符号: `DecisionApp.mark_lease_unhealthy(self, exc: BaseException) -> None`
- 动作: 新增方法，行为按 `design.md#f-001` 的 pseudocode：
  1. 取 `self._lock` 保证幂等
  2. 若 `_lease_healthy` 已被 clear，直接 return（**不**再 inc / log）
  3. 否则:
     - 计算 `reason = type(exc).__name__`
     - 填 `_lease_unhealthy_details = {"reason", "message"[:200]}`
     - `self.m_lease_refresh_failures.inc(labels={"reason": reason})`
     - `self._lease_healthy.clear()`
  4. 退出锁之后用 `self.pipeline.logger.error("lease.refresh.failed",
     lease_path=..., owner=..., error_type=reason)` 打日志
- Requirement: R-002 / R-003 / R-004

### T-107 · handle_ready 开头检查 lease-healthy

- 文件: `gan_matchmaking/service/app.py`
- 符号: `DecisionApp.handle_ready`
- 动作: 方法体第一条语句改为
  ```python
  if not self._lease_healthy.is_set():
      return 503, {"status": "not_ready",
                   "reason": "lease_unhealthy",
                   "details": dict(self._lease_unhealthy_details)}
  ```
  保留下面的 breaker 检查不动
- Requirement: R-001 / R-004

### T-108 · service/__main__ 把回调接入 LeaseRefreshLoop

- 文件: `gan_matchmaking/service/__main__.py`
- 动作: 在 `if args.lease_file:` 分支内，构造 `LeaseRefreshLoop` 之前调用
  `app.bind_lease_metadata(path=args.lease_file, owner=args.lease_owner)`，
  并把 `LeaseRefreshLoop(lease)` 改成
  `LeaseRefreshLoop(lease, on_failure=app.mark_lease_unhealthy)`
- Requirement: R-001 / R-003

### T-109 · 测试 test_refresh_failure_flips_readiness

- 文件: `tests/test_leases.py`（追加）
- 签名: `def test_refresh_failure_flips_readiness(tmp_path): ...`
- 断言:
  - `build_app(metrics=MetricsRegistry())` 构造 app
  - `app.bind_lease_metadata(path=str(tmp_path/"state.lock"), owner="test:1")`
  - `app.mark_lease_unhealthy(RuntimeError("boom"))`
  - `app.handle_ready(None)` 返回 `(503, body)`
  - `body["reason"] == "lease_unhealthy"`
  - `body["details"]["reason"] == "RuntimeError"`
- Requirement: R-001

### T-110 · 测试 test_refresh_failure_increments_metric

- 文件: `tests/test_leases.py`
- 签名: `def test_refresh_failure_increments_metric(tmp_path): ...`
- 断言:
  - `mark_lease_unhealthy(RuntimeError("..."))` 后
  - `registry.get("gan_lease_refresh_failures_total").snapshot()` 包含
    `(("reason","RuntimeError"),) == 1.0`
- Requirement: R-002

### T-111 · 测试 test_refresh_failure_emits_structured_log

- 文件: `tests/test_leases.py`
- 签名: `def test_refresh_failure_emits_structured_log(tmp_path, capsys): ...`
- 手法: 复用 `tests/test_core_logging_tracing.py` 的 `_logger_to_buffer`
  风格，把 `gan.sre.pipeline` 的 logger 替换为 in-memory handler
- 断言: 捕获到一条日志行，解析 JSON 后
  - `event == "lease.refresh.failed"`
  - `level == "ERROR"`
  - `payload["error_type"] == "RuntimeError"`
  - `payload["lease_path"]` / `payload["owner"]` 存在
- Requirement: R-003

### T-112 · 测试 test_refresh_failure_does_not_spam

- 文件: `tests/test_leases.py`
- 签名: `def test_refresh_failure_does_not_spam(tmp_path): ...`
- 断言:
  - 连续调 `mark_lease_unhealthy(RuntimeError(...))` 三次
  - metric 快照只有一条记录且值为 1
  - 捕获的日志中只出现一条 `lease.refresh.failed`
- Requirement: R-004

### T-113 · 测试 test_healthy_app_returns_ready

- 文件: `tests/test_leases.py`
- 签名: `def test_healthy_app_returns_ready(): ...`
- 断言: 新构造的 `DecisionApp`（未调 mark_lease_unhealthy）
  - `handle_ready(None)` 返回 `(200, {"status": "ready"})`
- Requirement: R-001（反向保护）

### T-114 · 测试 test_loop_invokes_callback_on_refresh_failure

- 文件: `tests/test_leases.py`
- 签名: `def test_loop_invokes_callback_on_refresh_failure(tmp_path): ...`
- 手法: 构造 `FileLease(path, owner=..., ttl_seconds=1)`，acquire
  后手动删除 lease 文件，然后 `lease.refresh()` 应抛 `LeaseNotAcquiredError`，
  用 `LeaseRefreshLoop(lease, on_failure=<spy>)` 不启线程，直接手动
  调 `loop._run(0.01)` 模拟内部循环一次，验证 spy 被调用一次且参数
  是 `LeaseNotAcquiredError` 实例
- Requirement: R-001 / R-005

---

## PR-fix-02 · Shadow rewrite 后 metric / log 与决策一致

> 满足的 requirements: **R-101 / R-102 / R-103 / R-104 / R-105**

### T-201 · 从 _emit 移除副作用（metric + log）

- 文件: `gan_matchmaking/sre/self_iteration.py`
- 符号: `SelfIterationPipeline._emit`（L845 起）
- 动作: 删除以下两个调用：
  ```python
  self.m_decisions.inc(labels={"kind": kind.value, "risk_level": risk_level.value})
  self.logger.info("decide.finished", kind=..., ...)
  ```
  保留 `Decision` 构造逻辑。返回值不变
- Requirement: R-101 / R-103

### T-202 · 在 trace 里暂存 service_id（供 _publish 使用）

- 文件: `gan_matchmaking/sre/self_iteration.py`
- 符号: `SelfIterationPipeline._emit`
- 动作: 在构造 `decision` 前新增一行
  ```python
  trace.setdefault("_service_id", service.id)
  ```
  使用下划线前缀表示"内部字段"
- Requirement: R-103（为了 log payload 能拿到 service_id）

### T-203 · 实现 _publish_decision 方法

- 文件: `gan_matchmaking/sre/self_iteration.py`
- 位置: 在 `_finalize_decision` 定义之前新增
- 签名: `def _publish_decision(self, decision: Decision, *, original_kind: DecisionKind) -> None`
- 行为:
  1. `service_id = decision.trace.pop("_service_id", "unknown")` （消费后
     pop，不污染公开 trace）
  2. `self.m_decisions.inc(labels={"kind": decision.kind.value,
     "risk_level": decision.risk_level.value})`
  3. `self.logger.info("decide.finished", kind=..., risk_level=...,
     risk_prob=..., confidence=..., service_id=service_id,
     chosen_id=..., artifact_version=decision.artifact_version)`
  4. **仅当** `original_kind != decision.kind` 时，补发
     `self.logger.info("decide.shadow_rewritten",
     original_kind=original_kind.value, final_kind=decision.kind.value,
     correlation_id=decision.correlation_id, service_id=service_id)`
- Requirement: R-101 / R-103 / R-105

### T-204 · 重写 _finalize_decision 使用 _publish_decision

- 文件: `gan_matchmaking/sre/self_iteration.py`
- 符号: `SelfIterationPipeline._finalize_decision`
- 动作: 改为
  ```python
  def _finalize_decision(self, decision: Decision) -> Decision:
      original_kind = decision.kind
      decision = self._shadow_wrap(decision)
      self._publish_decision(decision, original_kind=original_kind)
      if self.store is not None:
          self.store.observations.record_decision(decision)
      return decision
  ```
- Requirement: R-101 / R-102 / R-104

### T-205 · 测试 test_shadow_mode_metric_reflects_enforced_kind

- 文件: `tests/test_sre_self_iteration.py`
- 签名: `def test_shadow_mode_metric_reflects_enforced_kind(): ...`
- 手法: `shadow_mode=ShadowMode.SHADOW` + `error_budget_remaining=0.0`
  强制 ROLLBACK 分支
- 断言:
  - `decision.kind == DecisionKind.HOLD`
  - `gan_decisions_total` 快照里有 `kind="hold"` 一项
  - **没有** `kind="rollback"` 项
- Requirement: R-101

### T-206 · 测试 test_shadow_mode_suppressed_kind_counter

- 文件: `tests/test_sre_self_iteration.py`
- 签名: `def test_shadow_mode_suppressed_kind_counter(): ...`
- 断言: 同上场景下 `gan_shadow_diff_total` 快照里存在
  `suppressed_kind="rollback"` 项且值为 1
- Requirement: R-102

### T-207 · 测试 test_shadow_mode_emits_rewrite_event

- 文件: `tests/test_sre_self_iteration.py`
- 签名: `def test_shadow_mode_emits_rewrite_event(): ...`
- 手法: 用 `_logger_to_buffer` 捕获 `gan.sre.pipeline` 日志
- 断言: 捕获行中恰好一条 `event=decide.shadow_rewritten`，payload：
  - `original_kind == "rollback"`
  - `final_kind == "hold"`
  - `correlation_id == ctx.correlation_id`
- Requirement: R-103

### T-208 · 测试 test_off_mode_unaffected_by_shadow_fix

- 文件: `tests/test_sre_self_iteration.py`
- 签名: `def test_off_mode_unaffected_by_shadow_fix(): ...`
- 手法: `shadow_mode=ShadowMode.OFF` + 同样 ROLLBACK 场景
- 断言:
  - `gan_decisions_total` 快照里 `kind="rollback"` == 1
  - **没有** `decide.shadow_rewritten` 日志事件
- Requirement: R-105

### T-209 · 测试 test_advisory_mode_metric_uses_final_kind

- 文件: `tests/test_sre_self_iteration.py`
- 签名: `def test_advisory_mode_metric_uses_final_kind(): ...`
- 手法: `shadow_mode=ShadowMode.ADVISORY` + ROLLBACK 场景（ADVISORY
  模式不改 kind）
- 断言:
  - `gan_decisions_total` 快照里 `kind="rollback"` == 1
  - **没有** `decide.shadow_rewritten` 日志事件
- Requirement: R-105

### T-210 · 测试 test_shadow_rewrite_preserves_trace_fields

- 文件: `tests/test_sre_self_iteration.py`
- 签名: `def test_shadow_rewrite_preserves_trace_fields(): ...`
- 断言（回归保护 R-104）:
  - `decision.trace["shadow_mode"] == "shadow"`
  - `decision.trace["shadow_suppressed_kind"] == "rollback"`
  - `"_service_id" not in decision.trace`（已被 T-203 pop）
- Requirement: R-104

---

## PR-fix-03 · AppConfig trace-allowlist

> 满足的 requirements: **R-201 / R-202 / R-203 / R-204**

### T-301 · 定义 _TRACE_ALLOWLIST 常量

- 文件: `gan_matchmaking/core/config.py`
- 位置: 在 `AppConfig` 类定义之前，约 L150 附近
- 动作: 新增常量 `_TRACE_ALLOWLIST: Mapping[str, tuple[str, ...] | None]`，
  内容完全按 [`design.md#f-003`](design.md) 列出的 10 项
- Requirement: R-201 / R-204

### T-302 · AppConfig 新增 to_trace_dict 方法

- 文件: `gan_matchmaking/core/config.py`
- 符号: `AppConfig.to_trace_dict(self) -> dict[str, Any]`
- 动作: 按 [`../patches/F-003-trace-allowlist.md`](../patches/F-003-trace-allowlist.md)
  的片段实现；必须是 **纯函数**（不 mutate self）
- Requirement: R-201

### T-303 · AppConfig 新增 trace_allowlist_snapshot 类方法

- 文件: `gan_matchmaking/core/config.py`
- 符号: `AppConfig.trace_allowlist_snapshot() -> dict[str, list[str] | None]`
  （`@classmethod`）
- 动作: 把 `_TRACE_ALLOWLIST` 转成可比较的稳定形态（tuple → list），
  供 snapshot 测试对比
- Requirement: R-202

### T-304 · 替换 _decide_locked 的 trace 构造

- 文件: `gan_matchmaking/sre/self_iteration.py`
- 位置: L515 （`_decide_locked` 内部构造 `trace` 的地方）
- 动作: 把
  ```python
  "config": self.config.to_dict(),
  ```
  改为
  ```python
  "config": self.config.to_trace_dict(),
  ```
  **只改一行**
- Requirement: R-201 / R-203

### T-305 · 创建 tests/test_trace_privacy.py（测试 #1）

- 文件: **新建** `tests/test_trace_privacy.py`
- 签名: `def test_trace_config_only_allowlisted_keys(tmp_path): ...`
- 手法:
  - 构造 `AppConfig(observability=ObservabilityConfig(
      log_level="INFO", log_sink=str(tmp_path/"secret.log"),
      emit_metrics=True, service_name="svc-test"))`
  - 构造 `SelfIterationPipeline(config=cfg, metrics=MetricsRegistry())`，
    跑一次 `decide()`
- 断言:
  - `decision.trace["input"]["config"]["observability"]` **不** 含
    `log_sink` 与 `emit_metrics`
  - `trace_cfg["observability"]["log_level"] == "INFO"`
  - `trace_cfg["observability"]["service_name"] == "svc-test"`
  - `trace_cfg["seed"] == 0`
- Requirement: R-201 / R-204

### T-306 · 测试 test_trace_config_allowlist_snapshot

- 文件: `tests/test_trace_privacy.py`
- 签名: `def test_trace_config_allowlist_snapshot(): ...`
- 动作: 硬编码 `EXPECTED_ALLOWLIST` 字典（内容从 design.md 抄），断言
  `AppConfig.trace_allowlist_snapshot() == EXPECTED_ALLOWLIST`；失败
  message 指向 `_TRACE_ALLOWLIST` 定义位置与隐私 review 要求
- Requirement: R-202

### T-307 · 测试 test_to_trace_dict_is_pure

- 文件: `tests/test_trace_privacy.py`
- 签名: `def test_to_trace_dict_is_pure(): ...`
- 断言:
  - 两次调 `cfg.to_trace_dict()` 返回相等
  - 修改返回结果不 mutate `cfg`
- Requirement: R-201（纯性保证）

### T-308 · 测试 test_to_trace_dict_missing_optional_section

- 文件: `tests/test_trace_privacy.py`
- 签名: `def test_to_trace_dict_missing_optional_section(): ...`
- 手法: 用 `ArtifactsConfig(directory=None, ...)` 构造
- 断言: `trace_cfg["artifacts"]["directory"] is None`，其它 artifact
  字段仍按白名单保留
- Requirement: R-201

### T-309 · ADR-0006 追加隐私规则段落

- 文件: `docs/adr/0006-runtime-artifact-versioning.md`
- 动作: 在文件末尾追加 `## Related: What must never enter trace` 段，
  内容照抄 [`../patches/F-003-trace-allowlist.md`](../patches/F-003-trace-allowlist.md)
  的 "ADR 补充" 节
- Requirement: R-201（治理文档）

---

## 任务依赖矩阵

```
PR-fix-01
  T-101 → T-102           (leases.py 内部)
  T-103 → T-104 → T-105 → T-106 → T-107  (app.py 内部, 线性)
  T-108 依赖 T-101/T-103/T-105/T-106      (service/__main__ 整合)
  T-109..T-114 依赖 T-103~T-107           (测试先于 T-108 的线上接线?)

PR-fix-02
  T-201 → T-202 → T-203 → T-204          (self_iteration.py 内部, 线性)
  T-205..T-210 依赖 T-204                 (测试基于最终状态)

PR-fix-03
  T-301 → T-302 → T-303                  (config.py 内部, 线性)
  T-304 依赖 T-302                        (self_iteration.py 一行改)
  T-305..T-308 依赖 T-302/T-303           (新测试文件)
  T-309 可与编码并行                       (文档)
```

---

## 验收与收尾（非编码活动）

以下**不是**编码任务，但列出以明确 PR 完结的判定与归档动作。实际跑的
命令与断言来自 [`verification.md`](verification.md)。

- **验收 1**: 执行 `pytest -q`，期望 `123 passed`（原 105 + 新增 18 左右）。
- **验收 2**: 执行 `python -m bench.latency --quick`，期望 `p99 < 2.5 ms`。
- **验收 3**: 执行 `grep -rn "pragma: no cover" gan_matchmaking/sre/leases.py`
  返回空。
- **验收 4**: 执行 `pytest tests/test_replay_corpus.py -v`，所有 fixture 通过。
- **归档 1**: 把 `docs/claude-review/findings.md` 中 F-001 / F-002 / F-003
  的 `status` 从 `open` 改为 `resolved (commit <sha>)`。
- **归档 2**: 新建 `docs/claude-review/2026-05-spec-completion.md`，按
  [`verification.md` 末尾的模板](verification.md#全局收尾)填写。
- **归档 3**: 更新 `docs/V2_Knowledge/knowledge-base.html` 的 "Findings
  状态" 表格中 F-001 / F-002 / F-003 行改成 `<span class="tag resolved">`。

---

## Requirement → Task 反查

| Requirement | Task(s) |
|---|---|
| R-001 | T-101, T-102, T-103, T-107, T-108, T-109, T-113, T-114 |
| R-002 | T-101, T-104, T-106, T-110 |
| R-003 | T-102, T-105, T-106, T-108, T-111 |
| R-004 | T-106, T-107, T-112 |
| R-005 | T-102, T-114 |
| R-101 | T-201, T-203, T-204, T-205 |
| R-102 | T-204, T-206 |
| R-103 | T-201, T-202, T-203, T-207 |
| R-104 | T-204, T-210 |
| R-105 | T-203, T-208, T-209 |
| R-201 | T-301, T-302, T-304, T-305, T-307, T-308, T-309 |
| R-202 | T-303, T-306 |
| R-203 | T-304 |
| R-204 | T-301, T-305 |

**所有 R-XXX 都有至少两条 Task 覆盖**（单测 + 实现各一条），符合"可执行
spec"的最低契约。
