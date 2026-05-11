# Verification · B+A2 本轮

codex 每完成一个 task checkbox，回这里跑对应小节的验证命令。
全部绿之后，finding 才能标 `resolved`。

所有命令假设 `cwd = <repo>/gan` 且 `pip install -e .[dev]` 已完成。

---

## F-001 · Lease refresh 可见化

### 命令

```bash
pytest tests/test_leases.py -v
```

**期望输出**（节选）：

```
tests/test_leases.py::test_file_lease_excludes_second_owner PASSED
tests/test_leases.py::test_file_lease_releases_to_next_owner PASSED
tests/test_leases.py::test_file_lease_takes_over_expired_owner PASSED
tests/test_leases.py::test_file_lease_refresh_extends_expiry PASSED
tests/test_leases.py::test_service_main_acquires_and_releases_lease PASSED
tests/test_leases.py::test_refresh_failure_flips_readiness PASSED       # 新增
tests/test_leases.py::test_refresh_failure_increments_metric PASSED     # 新增
tests/test_leases.py::test_refresh_failure_emits_structured_log PASSED  # 新增
tests/test_leases.py::test_refresh_failure_does_not_spam PASSED         # 新增
tests/test_leases.py::test_healthy_app_returns_ready PASSED             # 新增
tests/test_leases.py::test_loop_invokes_callback_on_refresh_failure PASSED  # 新增
```

### 静态检查

```bash
grep -n "pragma: no cover" gan_matchmaking/sre/leases.py
```

**期望输出**: 空输出（R-005）。

### 契约快照（R-001 的 details 字段）

在一个 Python REPL 中：

```python
from gan_matchmaking.service.app import build_app
from gan_matchmaking.core import MetricsRegistry
app = build_app(metrics=MetricsRegistry())
app.bind_lease_metadata(path="/tmp/state.lock", owner="test:1")
app.mark_lease_unhealthy(RuntimeError("simulated"))
code, body = app.handle_ready(None)
assert code == 503
assert body["status"] == "not_ready"
assert body["reason"] == "lease_unhealthy"
assert body["details"]["reason"] == "RuntimeError"
```

### Prometheus 可见性

```python
metric_text = app.pipeline.metrics.export_prometheus()
assert "gan_lease_refresh_failures_total" in metric_text
assert 'reason="RuntimeError"' in metric_text
```

### Log 快照（R-003）

日志行的结构（用 test 中的捕获），应匹配：

```json
{
  "event": "lease.refresh.failed",
  "level": "ERROR",
  "payload": {
    "lease_path": "/tmp/state.lock",
    "owner": "test:1",
    "error_type": "RuntimeError"
  }
}
```

### F-001 定义完成

所有上述检查通过 + `findings.md::F-001` 改 `resolved (commit <sha>)`。

---

## F-002 · Shadow metric/log 一致

### 命令

```bash
pytest tests/test_sre_self_iteration.py -v -k "shadow or advisory"
```

**期望（关键项）**：

```
test_shadow_mode_metric_reflects_enforced_kind PASSED              # 新增
test_shadow_mode_suppressed_kind_counter PASSED                    # 新增
test_shadow_mode_emits_rewrite_event PASSED                        # 新增
test_off_mode_unaffected_by_shadow_fix PASSED                      # 新增
test_advisory_mode_metric_uses_final_kind PASSED                   # 新增
test_shadow_rewrite_preserves_trace_fields PASSED                  # 新增
```

### 契约快照

```python
from gan_matchmaking.core import AppConfig, MetricsRegistry
from gan_matchmaking.sre import (
    SelfIterationPipeline, ReleaseCandidate, ReleaseContext,
    Service, ShadowMode, DecisionKind,
)

reg = MetricsRegistry()
p = SelfIterationPipeline(config=AppConfig(), metrics=reg,
                           shadow_mode=ShadowMode.SHADOW)
svc = Service(id="svc-shadow", mu=0.99, sigma=0.02, tier="standard")
ctx = ReleaseContext(
    service=svc,
    candidates=[ReleaseCandidate(id="c1", service_id=svc.id, strategy="canary",
                                 canary_fraction=0.1,
                                 rollback_budget_seconds=180,
                                 expected_success=0.99)],
    error_budget_remaining=0.0,  # 强制 ROLLBACK 路径
    correlation_id="verify-F002-1",
)
decision = p.decide(ctx)

# enforced kind = HOLD
assert decision.kind == DecisionKind.HOLD
# 指标反映 enforced
total = reg.get("gan_decisions_total").snapshot()
has_hold = any(dict(k).get("kind") == "hold" for k in total)
has_rollback = any(dict(k).get("kind") == "rollback" for k in total)
assert has_hold and not has_rollback
# 原 kind 在 diff 里
diff = reg.get("gan_shadow_diff_total").snapshot()
assert any(dict(k).get("suppressed_kind") == "rollback" for k in diff)
# trace 保留原 kind
assert decision.trace["shadow_mode"] == "shadow"
assert decision.trace["shadow_suppressed_kind"] == "rollback"
```

### Log 快照

捕获的日志里应该看到：

```json
{"event": "decide.finished", "payload": {"kind": "hold", ...}}
{"event": "decide.shadow_rewritten",
 "payload": {"original_kind": "rollback",
             "final_kind": "hold",
             "correlation_id": "verify-F002-1"}}
```

**不应**看到 `{"event": "decide.finished", "payload": {"kind": "rollback"}}`。

### 性能

```bash
python -m bench.latency --quick
```

**期望**: p99 < 2.5ms（额外一次 log 预算约 +0.1ms）。若 > 2.5ms，回滚
`_publish_decision`，改用条件调 `logger.info`（`if original_kind != ...`）。

### F-002 定义完成

所有检查 + `findings.md::F-002` 改 `resolved`。

---

## F-003 · Trace 配置 allowlist

### 命令

```bash
pytest tests/test_trace_privacy.py -v
pytest tests/test_replay_corpus.py -v     # 兼容性回归
```

**期望**：

```
tests/test_trace_privacy.py::test_trace_config_only_allowlisted_keys PASSED
tests/test_trace_privacy.py::test_trace_config_allowlist_snapshot PASSED
tests/test_trace_privacy.py::test_to_trace_dict_is_pure PASSED
tests/test_trace_privacy.py::test_to_trace_dict_missing_optional_section PASSED
```

```
tests/test_replay_corpus.py ... 8 passed
```

### 契约快照

```python
from gan_matchmaking.core import AppConfig
from gan_matchmaking.core.config import ObservabilityConfig

cfg = AppConfig(observability=ObservabilityConfig(
    log_sink="/var/log/secret.log",   # 应该被过滤
    log_level="INFO",
))
trace_cfg = cfg.to_trace_dict()
assert "log_sink" not in trace_cfg["observability"]
assert trace_cfg["observability"]["log_level"] == "INFO"
assert "seed" in trace_cfg
# 下游可变 allowlist 但不能随便 mutate 结果
snap_a = cfg.to_trace_dict()
snap_b = cfg.to_trace_dict()
assert snap_a == snap_b
```

### Allowlist snapshot（新增字段时会触发）

```python
from gan_matchmaking.core import AppConfig
snap = AppConfig.trace_allowlist_snapshot()
assert snap["observability"] == ["log_level", "service_name"]
assert snap["artifacts"] == [
    "directory", "retention_filename", "retention_metadata_filename",
    "cox_filename", "cox_metadata_filename",
]
assert snap["seed"] is None      # scalar top-level field
```

### Replay corpus 流程

若 `test_replay_corpus.py` 里某个 fixture 失败：

1. `pytest tests/test_replay_corpus.py::<fixture_name> -v` 看错误堆栈
2. 如果失败是因为 `load_config(fixture["config"])` 抛 `ConfigError`，说明
   fixture 里的 `config` 段含被 allowlist 过滤的字段，但 allowlist 逻辑在
   **写出**时生效、**读回**时 `load_config` 不认识这些字段
3. 解决方案：重录这个 fixture
   ```bash
   python -m gan_matchmaking.cli export-replay \
     --state-db <fixture 对应的 db> \
     --correlation-id <原 correlation_id> \
     --output tests/fixtures/replay/<name>.json
   ```
4. 提交重录版本时在 PR 描述中列明
   **切勿**为了让老 fixture 通过而放宽 allowlist。

### F-003 定义完成

所有检查 + `findings.md::F-003` 改 `resolved` + ADR 更新段落已写。

---

## 全局收尾

```bash
pytest -q                        # 全绿
python -m bench.latency --quick  # p99 < 2.5ms
grep -rn "pragma: no cover" gan_matchmaking/
```

`grep` 期望只剩以下允许的 pragma：

- `gan_matchmaking/service/app.py`: HTTP catch-all 500 branch
- `gan_matchmaking/cli.py`: `sys.exit(main())` 末尾（非测试路径）
- `gan_matchmaking/service/__main__.py`: 同上

其它位置全部应 **无** `# pragma: no cover`。

### 新建收尾文档

本轮全部完成后创建 `docs/claude-review/2026-05-spec-completion.md`：

```markdown
# 2026-05 Spec Completion · B+A2

Scope closed: F-001, F-002, F-003

- PR-fix-01 merged: <commit>
- PR-fix-02 merged: <commit>
- PR-fix-03 merged: <commit>
- Tests added: <count>
- pytest -q: PASSED
- bench p99: X.XXms  (budget 2.5ms)
- findings.md: F-001/F-002/F-003 status=resolved

Deferred to next round: F-004, F-005, F-006, F-007, F-008, F-009, F-010
```
