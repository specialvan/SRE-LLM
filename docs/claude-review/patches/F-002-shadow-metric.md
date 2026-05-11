# Patch · F-002 Shadow metric/log 一致

## 当前代码锚点

### `gan_matchmaking/sre/self_iteration.py::_emit` (L845 起)

```python
    def _emit(
        self,
        kind: DecisionKind,
        chosen: Optional[ReleaseCandidate],
        risk_level: RiskLevel,
        risk_p: float,
        service: Service,
        rationale: List[str],
        trace: Dict[str, Any],
        correlation_id: str,
    ) -> Decision:
        confidence = max(0.0, min(1.0, service.mu - _CONF_ALPHA * service.sigma))
        decision = Decision(
            kind=kind,
            chosen=chosen,
            risk_level=risk_level,
            risk_prob=risk_p,
            confidence=confidence,
            rationale=rationale,
            trace=trace,
            artifact_version=self.artifacts.version,
            correlation_id=correlation_id,
        )
        self.m_decisions.inc(labels={"kind": kind.value, "risk_level": risk_level.value})  # ← 删
        self.logger.info(                                                                    # ← 删整块
            "decide.finished",
            kind=kind.value,
            risk_level=risk_level.value,
            risk_prob=risk_p,
            confidence=confidence,
            service_id=service.id,
            chosen_id=chosen.id if chosen else None,
            artifact_version=self.artifacts.version,
        )
        return decision
```

**问题**：这两个"副作用"在 `_shadow_wrap` 之前发出，metric/log 反映的是原 kind，
但 `decision.kind` 之后会被改写成 HOLD，persist 的也是 HOLD。

### `_finalize_decision` (L881)

```python
    def _finalize_decision(self, decision: Decision) -> Decision:
        decision = self._shadow_wrap(decision)
        if self.store is not None:
            self.store.observations.record_decision(decision)
        return decision
```

## 目标代码

### `_emit` 改为只构造，不发副作用

```python
    def _emit(
        self,
        kind: DecisionKind,
        chosen: Optional[ReleaseCandidate],
        risk_level: RiskLevel,
        risk_p: float,
        service: Service,
        rationale: List[str],
        trace: Dict[str, Any],
        correlation_id: str,
    ) -> Decision:
        confidence = max(0.0, min(1.0, service.mu - _CONF_ALPHA * service.sigma))
        # Record service identity in trace so _publish_decision can reuse it
        # without rethreading the service object.
        trace.setdefault("_service_id", service.id)
        return Decision(
            kind=kind,
            chosen=chosen,
            risk_level=risk_level,
            risk_prob=risk_p,
            confidence=confidence,
            rationale=rationale,
            trace=trace,
            artifact_version=self.artifacts.version,
            correlation_id=correlation_id,
        )
```

> `_service_id` 以下划线开头表示"内部字段"，`_publish_decision` 消费后可以
> `pop` 掉，避免污染公开 trace。但也可以不 pop（现有 trace.input.context
> 已经有 service.id，算 redundancy），按洁癖选择。这里推荐 **pop**。

### 新增 `_publish_decision`（放在 `_finalize_decision` 之前）

```python
    def _publish_decision(
        self,
        decision: Decision,
        *,
        original_kind: DecisionKind,
    ) -> None:
        """Emit metrics + logs once, reflecting the ENFORCED kind."""
        service_id = decision.trace.pop("_service_id", "unknown")
        self.m_decisions.inc(labels={
            "kind": decision.kind.value,
            "risk_level": decision.risk_level.value,
        })
        self.logger.info(
            "decide.finished",
            kind=decision.kind.value,
            risk_level=decision.risk_level.value,
            risk_prob=decision.risk_prob,
            confidence=decision.confidence,
            service_id=service_id,
            chosen_id=decision.chosen.id if decision.chosen else None,
            artifact_version=decision.artifact_version,
        )
        if original_kind != decision.kind:
            self.logger.info(
                "decide.shadow_rewritten",
                original_kind=original_kind.value,
                final_kind=decision.kind.value,
                correlation_id=decision.correlation_id,
                service_id=service_id,
            )
```

### `_finalize_decision` 改为

```python
    def _finalize_decision(self, decision: Decision) -> Decision:
        original_kind = decision.kind
        decision = self._shadow_wrap(decision)
        self._publish_decision(decision, original_kind=original_kind)
        if self.store is not None:
            self.store.observations.record_decision(decision)
        return decision
```

## 测试函数签名

```python
# tests/test_sre_self_iteration.py

def test_shadow_mode_metric_reflects_enforced_kind():
    reg = MetricsRegistry()
    p = SelfIterationPipeline(config=AppConfig(),
                               metrics=reg,
                               shadow_mode=ShadowMode.SHADOW)
    # error_budget=0 → ROLLBACK 路径
    ctx = _ctx(error_budget_remaining=0.0, correlation_id="t1")
    decision = p.decide(ctx)
    assert decision.kind == DecisionKind.HOLD
    snap = reg.get("gan_decisions_total").snapshot()
    # "hold" 被计数,"rollback" 不被计数
    assert any(dict(k).get("kind") == "hold" for k in snap)
    assert not any(dict(k).get("kind") == "rollback" for k in snap)

def test_shadow_mode_suppressed_kind_counter():
    reg = MetricsRegistry()
    p = SelfIterationPipeline(config=AppConfig(), metrics=reg,
                               shadow_mode=ShadowMode.SHADOW)
    ctx = _ctx(error_budget_remaining=0.0, correlation_id="t2")
    p.decide(ctx)
    snap = reg.get("gan_shadow_diff_total").snapshot()
    assert any(dict(k).get("suppressed_kind") == "rollback" for k in snap)

def test_shadow_mode_emits_rewrite_event(caplog_json):
    p = SelfIterationPipeline(config=AppConfig(),
                               metrics=MetricsRegistry(),
                               shadow_mode=ShadowMode.SHADOW)
    ctx = _ctx(error_budget_remaining=0.0, correlation_id="shadow-t3")
    p.decide(ctx)
    events = [e for e in caplog_json if e["event"] == "decide.shadow_rewritten"]
    assert len(events) == 1
    payload = events[0]["payload"]
    assert payload["original_kind"] == "rollback"
    assert payload["final_kind"] == "hold"
    assert payload["correlation_id"] == "shadow-t3"

def test_off_mode_unaffected_by_shadow_fix(caplog_json):
    reg = MetricsRegistry()
    p = SelfIterationPipeline(config=AppConfig(),
                               metrics=reg,
                               shadow_mode=ShadowMode.OFF)
    ctx = _ctx(error_budget_remaining=0.0, correlation_id="off-t4")
    p.decide(ctx)
    snap = reg.get("gan_decisions_total").snapshot()
    # OFF 模式下 rollback 正常计数
    assert any(dict(k).get("kind") == "rollback" for k in snap)
    # 不产生 shadow_rewritten 事件
    events = [e for e in caplog_json if e["event"] == "decide.shadow_rewritten"]
    assert events == []

def test_advisory_mode_metric_uses_final_kind():
    reg = MetricsRegistry()
    p = SelfIterationPipeline(config=AppConfig(), metrics=reg,
                               shadow_mode=ShadowMode.ADVISORY)
    ctx = _ctx(error_budget_remaining=0.0, correlation_id="adv-t5")
    p.decide(ctx)
    snap = reg.get("gan_decisions_total").snapshot()
    # advisory 不改 kind,metric 计入 rollback
    assert any(dict(k).get("kind") == "rollback" for k in snap)

def test_shadow_rewrite_preserves_trace_fields():
    p = SelfIterationPipeline(config=AppConfig(),
                               metrics=MetricsRegistry(),
                               shadow_mode=ShadowMode.SHADOW)
    ctx = _ctx(error_budget_remaining=0.0, correlation_id="t6")
    decision = p.decide(ctx)
    assert decision.trace["shadow_mode"] == "shadow"
    assert decision.trace["shadow_suppressed_kind"] == "rollback"
    # _service_id 内部字段应已被 pop
    assert "_service_id" not in decision.trace
```

### `conftest.py` 新增 fixture `caplog_json`

```python
# tests/conftest.py (新增或追加)

import io
import json
import logging
import pytest

from gan_matchmaking.core.logging import JsonLineFormatter


@pytest.fixture
def caplog_json():
    """Capture JSONL log lines emitted to the gan.* logger hierarchy."""
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JsonLineFormatter())
    logger = logging.getLogger("gan.sre.pipeline")
    prev_handlers = list(logger.handlers)
    logger.handlers = [handler]
    logger.propagate = False
    records: list[dict] = []

    yield records  # 测试中记录被 live-populated

    # 测试结束后 parse
    for line in buf.getvalue().splitlines():
        if line.strip():
            records.append(json.loads(line))
    logger.handlers = prev_handlers
```

> 该 fixture 有个时序细节：records 是 yield 时给测试的 **可变** list，但
> 内容要测试 body 执行完才有。为了让测试能"在 assert 时看到"日志，实现
> 改成在 yield 之前 parse 是不可能的；所以 API 选择是：**测试 body 结束
> 后 fixture teardown 时 parse，assert 在 finalize 之后**。
>
> 简化方案：让 fixture 直接返回一个"lazy list"，首次被访问时 parse buffer。
> 或者最简：**测试用 `with caplog_json()` 形式而不是 fixture**。
>
> 如果觉得太复杂，直接在每个测试里用 `io.StringIO` + `JsonLineFormatter` 手写，
> 和现有 `tests/test_core_logging_tracing.py` 保持一致风格。

## 预计 LOC

- `self_iteration.py`: +28 / -12 (删 `_emit` 两块，加 `_publish_decision`)
- `tests/test_sre_self_iteration.py`: +120 / -0
- `tests/conftest.py`: +25 / -0（如果选 fixture 方案）

总计约 +160 LOC。
