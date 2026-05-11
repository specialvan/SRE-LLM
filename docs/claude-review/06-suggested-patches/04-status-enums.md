# Patch 04 · 锁定 T_inv / CBF status 枚举

- **Action item**：[AI-03b](../05-action-items.md#ai-03b)
- **Target**：把 `status` / `cbf_status` 的合法值显式化，防止下一轮新增值时漏掉文档/测试。

## 改动 1 · `auto_decide/trace.py`

在 `TRACE_SCHEMA_VERSION` 常量下方加：

```python
PLANNER_STATUS_VALUES = frozenset({
    "stable",           # 首次即满足 dV/dt ≤ -γV
    "relaxed_exp",      # 松弛后满足指数衰减目标
    "relaxed",          # 松弛后只满足 dV/dt ≤ τ
    "non_increasing",   # 边缘稳定 |dV/dt| ≤ τ
    "emergency_brake",  # 兜底刹停
})

CBF_STATUS_VALUES = frozenset({
    "nom_ok",           # 名义命令直接满足所有 barrier
    "qp_ok",            # 网格搜到非平凡可行解
    "fallback_brake",   # 搜索失败，退化为刹停
})
```

在 `build_trace_record` 末尾（`return record` 之前）加断言（可通过关键字参数控制，保持向后兼容）：

```python
def build_trace_record(*, ..., strict: bool = True) -> dict:
    ...
    record = { ... }
    if strict:
        _validate_status(record)
    return record


def _validate_status(record: dict) -> None:
    status = record.get("status")
    if status is not None and status not in PLANNER_STATUS_VALUES:
        raise ValueError(
            f"Unknown planner status: {status!r}. "
            f"Allowed: {sorted(PLANNER_STATUS_VALUES)}"
        )
    cbf_status = record.get("cbf_status")
    if cbf_status is not None and cbf_status not in CBF_STATUS_VALUES:
        raise ValueError(
            f"Unknown cbf_status: {cbf_status!r}. "
            f"Allowed: {sorted(CBF_STATUS_VALUES)}"
        )
```

## 改动 2 · `auto_decide/__init__.py`

导出常量，便于外部引用：

```python
from .trace import (
    TRACE_SCHEMA_VERSION,
    PLANNER_STATUS_VALUES,
    CBF_STATUS_VALUES,
    build_trace_record,
)
```

## 改动 3 · `tests/test_trace.py`

追加：

```python
import pytest
from auto_decide.trace import (
    PLANNER_STATUS_VALUES,
    CBF_STATUS_VALUES,
    build_trace_record,
)


def test_planner_status_enum_contents():
    """INV-G12: planner status 枚举封闭。"""
    assert PLANNER_STATUS_VALUES == frozenset({
        "stable", "relaxed_exp", "relaxed", "non_increasing", "emergency_brake",
    })


def test_cbf_status_enum_contents():
    assert CBF_STATUS_VALUES == frozenset({
        "nom_ok", "qp_ok", "fallback_brake",
    })


def test_build_trace_record_rejects_unknown_planner_status():
    from auto_decide.types import Control, State
    state = State(px=0.0, py=0.0, psi=0.0, v=5.0, a=0.0, mu=1.0)
    with pytest.raises(ValueError, match="Unknown planner status"):
        build_trace_record(
            step_index=0, dt=0.1,
            state=state, next_state=state,
            u_nn=Control(0.0, 0.0), u_safe=Control(0.0, 0.0),
            info={"status": "totally_new_value", "cbf": {}},
            min_dist=10.0,
        )


def test_build_trace_record_rejects_unknown_cbf_status():
    from auto_decide.types import Control, State
    state = State(px=0.0, py=0.0, psi=0.0, v=5.0, a=0.0, mu=1.0)
    with pytest.raises(ValueError, match="Unknown cbf_status"):
        build_trace_record(
            step_index=0, dt=0.1,
            state=state, next_state=state,
            u_nn=Control(0.0, 0.0), u_safe=Control(0.0, 0.0),
            info={"status": "stable", "cbf": {"status": "weird"}},
            min_dist=10.0,
        )
```

## 改动 4 · `docs/trace-schema.md`

替换 `status` 和 `cbf_status` 两行为：

```markdown
| `status` | enum | `T_inv.apply` 的状态码，取值之一：<br>
  • `stable` — 首次即满足 dV/dt ≤ -γV <br>
  • `relaxed_exp` — 松弛后满足指数衰减目标 <br>
  • `relaxed` — 松弛后只满足 dV/dt ≤ τ <br>
  • `non_increasing` — 边缘稳定 \|dV/dt\| ≤ τ <br>
  • `emergency_brake` — 兜底刹停 |
| `cbf_status` | enum | `CBFQPFilter.filter` 的状态码，取值之一：<br>
  • `nom_ok` — 名义命令直接满足所有 barrier <br>
  • `qp_ok` — 网格搜到非平凡可行解 <br>
  • `fallback_brake` — 搜索失败，退化为刹停 |
```

## 改动 5 · `docs/codex-handoff.md`

把 §2.8 （以及其它列 status 的位置）改为：

```markdown
status code 的合法集合见 [trace-schema.md](./trace-schema.md) 的枚举表。
```

不要在 handoff 里自己维护副本（避免漂移）。

## 验收

- `pytest tests/test_trace.py -v` 新增的 4 个测试通过；
- `grep -rn "relaxed_exp\|non_increasing" docs/codex-handoff.md` 返回 0 行（handoff 不再自维护）；
- `trace-schema.md` 的 status / cbf_status 两行用 bullet list 展开 5 / 3 个值。
