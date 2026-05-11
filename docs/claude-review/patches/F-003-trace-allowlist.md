# Patch · F-003 Trace 配置 allowlist

## 当前代码锚点

### `gan_matchmaking/sre/self_iteration.py::_decide_locked` (L515)

```python
            trace: Dict[str, Any] = {
                "input": {
                    "context": _context_payload(ctx),
                    "config": self.config.to_dict(),     # ← 全量序列化,隐患
                },
                "stages": {},
                "artifacts": self.artifacts.as_trace(),
            }
```

### `gan_matchmaking/core/config.py::AppConfig.to_dict` (L161)

```python
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
```

## 目标代码

### `config.py` 文件顶部附近新增模块级常量

```python
from typing import Mapping

# --- Trace allowlist ---------------------------------------------------
# Explicitly enumerate which config fields are safe to embed in the
# decision trace. Anything outside this allowlist is filtered out by
# AppConfig.to_trace_dict(). Scalar top-level fields use ``None`` as the
# allowed-subkey marker.
_TRACE_ALLOWLIST: Mapping[str, "tuple[str, ...] | None"] = {
    "seed": None,
    "observability": ("log_level", "service_name"),
    "trueskill": ("mu0", "sigma0", "beta", "tau", "draw_probability"),
    "dynamic_k": ("k_max", "k_min", "lam", "theta", "penalize_wins"),
    "handicap": ("max_penalty", "tau"),
    "entropy": ("min_entropy",),
    "eomm": ("epsilon", "lr", "iters", "l2"),
    "survival": ("horizon_hours", "warn_threshold", "alarm_threshold"),
    "gnn": ("hidden_dim", "layers", "seed"),
    "artifacts": ("directory", "retention_filename",
                  "retention_metadata_filename", "cox_filename",
                  "cox_metadata_filename"),
}
```

### `AppConfig` 新增方法（放在 `to_dict` 之后）

```python
    def to_trace_dict(self) -> dict[str, Any]:
        """Return the subset of config fields that is safe to embed in trace.

        Anything outside _TRACE_ALLOWLIST is filtered out. See ADR-0006
        "What must never enter trace" for the rationale.
        """
        full = self.to_dict()
        out: dict[str, Any] = {}
        for top_key, allowed in _TRACE_ALLOWLIST.items():
            if top_key not in full:
                continue
            value = full[top_key]
            if allowed is None:
                out[top_key] = value
                continue
            if isinstance(value, Mapping):
                out[top_key] = {k: value[k] for k in allowed if k in value}
            else:
                out[top_key] = value
        return out

    @classmethod
    def trace_allowlist_snapshot(cls) -> dict[str, "list[str] | None"]:
        """Stable dict form of _TRACE_ALLOWLIST for snapshot tests."""
        return {
            key: (None if allowed is None else list(allowed))
            for key, allowed in _TRACE_ALLOWLIST.items()
        }
```

### `sre/self_iteration.py::_decide_locked` (L515) 只改一行

```python
# before
"config": self.config.to_dict(),
# after
"config": self.config.to_trace_dict(),
```

## 新测试文件

### `tests/test_trace_privacy.py`

```python
"""Tests for the trace-config allowlist (F-003)."""
from __future__ import annotations

import pytest

from gan_matchmaking.core import AppConfig, MetricsRegistry
from gan_matchmaking.core.config import (
    ArtifactsConfig,
    ObservabilityConfig,
    SurvivalConfig,
)
from gan_matchmaking.sre import (
    DecisionKind,
    ReleaseCandidate,
    ReleaseContext,
    SelfIterationPipeline,
    Service,
)


EXPECTED_ALLOWLIST = {
    "seed": None,
    "observability": ["log_level", "service_name"],
    "trueskill": ["mu0", "sigma0", "beta", "tau", "draw_probability"],
    "dynamic_k": ["k_max", "k_min", "lam", "theta", "penalize_wins"],
    "handicap": ["max_penalty", "tau"],
    "entropy": ["min_entropy"],
    "eomm": ["epsilon", "lr", "iters", "l2"],
    "survival": ["horizon_hours", "warn_threshold", "alarm_threshold"],
    "gnn": ["hidden_dim", "layers", "seed"],
    "artifacts": ["directory", "retention_filename",
                  "retention_metadata_filename", "cox_filename",
                  "cox_metadata_filename"],
}


def _sample_ctx():
    svc = Service(id="svc-priv", mu=0.99, sigma=0.02, tier="standard")
    cand = ReleaseCandidate(
        id="c1", service_id=svc.id, strategy="canary",
        canary_fraction=0.05, rollback_budget_seconds=180,
        expected_success=0.99,
    )
    return ReleaseContext(service=svc, candidates=[cand],
                          correlation_id="priv-1")


def test_trace_config_only_allowlisted_keys(tmp_path):
    cfg = AppConfig(
        observability=ObservabilityConfig(
            log_level="INFO",
            log_sink=str(tmp_path / "secret.log"),   # 不应出现在 trace
            emit_metrics=True,
            service_name="svc-test",
        ),
    )
    pipeline = SelfIterationPipeline(config=cfg, metrics=MetricsRegistry())
    decision = pipeline.decide(_sample_ctx())

    trace_cfg = decision.trace["input"]["config"]
    assert "log_sink" not in trace_cfg["observability"]
    assert "emit_metrics" not in trace_cfg["observability"]
    assert trace_cfg["observability"]["log_level"] == "INFO"
    assert trace_cfg["observability"]["service_name"] == "svc-test"
    # 标量 top-level 字段仍保留
    assert trace_cfg["seed"] == 0


def test_trace_config_allowlist_snapshot():
    snap = AppConfig.trace_allowlist_snapshot()
    assert snap == EXPECTED_ALLOWLIST, (
        "AppConfig._TRACE_ALLOWLIST 改动了。如果这是有意的,"
        "请更新 EXPECTED_ALLOWLIST 并 review 新字段的隐私暴露面。"
    )


def test_to_trace_dict_is_pure():
    cfg = AppConfig()
    a = cfg.to_trace_dict()
    b = cfg.to_trace_dict()
    assert a == b
    # 修改结果不 mutate config
    a["seed"] = 999
    assert cfg.seed == 0


def test_to_trace_dict_missing_optional_section():
    cfg = AppConfig(
        artifacts=ArtifactsConfig(
            directory=None,
            retention_filename="r.npz",
            retention_metadata_filename="r.json",
            cox_filename="c.npz",
            cox_metadata_filename="c.json",
        ),
    )
    trace_cfg = cfg.to_trace_dict()
    # directory=None 仍在 dict 里,值是 None
    assert "artifacts" in trace_cfg
    assert trace_cfg["artifacts"]["directory"] is None
    assert trace_cfg["artifacts"]["retention_filename"] == "r.npz"
```

## Replay corpus 兼容处理

现有 `tests/fixtures/replay/*.json` 有几类 `config` 字段形态：

1. `{}` 空对象（多数 fixture） → **不受影响**
2. `{"artifacts": {"directory": "..."}}` → **不受影响**（directory 在白名单内）
3. 嵌入完整 config（如果有） → 运行时 `load_config(fixture["config"])`
   只读 fixture 里实际存在的字段，不会因为 allowlist 而报错

→ **不预期有 fixture 需要重录**。如果 `pytest tests/test_replay_corpus.py`
失败，按 [`verification.md#F-003`](../spec/verification.md#f-003-trace-配置-allowlist)
的重录流程处理，**严禁**为了让老 fixture 通过而放宽 allowlist。

## ADR 补充

`docs/adr/0006-runtime-artifact-versioning.md` 末尾追加：

```markdown
## Related: What must never enter trace

Independent of model artifacts, the trace itself is an audit surface.
`AppConfig.to_trace_dict()` enforces an allowlist so the following are
**never** embedded:

- any URL, host, DSN, or network path (exposes internal topology)
- any API token, password, or other secret
- any PII or customer identifier
- log sink paths (exposes local filesystem layout)
- any config field added after this ADR unless the allowlist is
  explicitly updated with a privacy-review note

Adding a field to `_TRACE_ALLOWLIST` requires:
1. A snapshot-test update (`test_trace_config_allowlist_snapshot`).
2. A PR-description note stating why the field is safe to log.
```

## 预计 LOC

- `core/config.py`: +45 / -0
- `sre/self_iteration.py`: +1 / -1 (一行改)
- `tests/test_trace_privacy.py`: +95 / -0
- `docs/adr/0006-runtime-artifact-versioning.md`: +25 / -0

总计约 +165 LOC。
