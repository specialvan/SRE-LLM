# Patch 03 · Benchmark SLO 红线断言

- **Action item**：[AI-01](../05-action-items.md#ai-01)
- **Target**：让 CI 把"结构化链路的可用性 SLO"变成强制门，防止 Codex 下一轮通过调宽硬约束来"好看"。

## 改动点

`tests/test_benchmark_metrics.py` 末尾追加：

```python
import pytest
from examples.compare_e2e_vs_structural import run_benchmark


@pytest.mark.xfail(
    strict=True,
    reason=(
        "AI-01 + AI-02: 当前 nominal policy 与 CBF 结构性不匹配。"
        " AI-02 完成后应移除 xfail。"
    ),
)
def test_structural_pipeline_respects_availability_budget():
    """INV-G13 / SLO: structural 链路在默认 benchmark 下应满足可用性预算。

    红线：
    - collision_rate == 0 （必须）
    - planner_emergency_rate <= 0.10
    - cbf_fallback_rate <= 0.10

    这里的 10% 是 demo 级松弛，真实生产 SLO 是 0.5%/5%。
    Codex 不允许通过调宽 cbf_alpha / game.base_buffer 让此测试通过，
    必须通过升级 nominal policy（AI-02）。
    """
    payload = run_benchmark(n=20, seed=0, horizon=100, dt=0.1)
    s = payload["summaries"]["structural"]
    assert s["collision_rate"] == 0.0, (
        f"collision_rate must be 0, got {s['collision_rate']}"
    )
    assert s["planner_emergency_rate"] <= 0.10, (
        f"planner_emergency_rate must be <= 10% (SLO demo tier), "
        f"got {s['planner_emergency_rate']:.2%}. "
        f"Fix by AI-02, not by loosening CBF."
    )
    assert s["cbf_fallback_rate"] <= 0.10, (
        f"cbf_fallback_rate must be <= 10%, got {s['cbf_fallback_rate']:.2%}"
    )
```

## 为什么用 `xfail(strict=True)`？

- AI-02 尚未完成时测试**预期失败**。xfail 让 CI 绿，提醒 reviewer 这是已知问题。
- `strict=True` 意味着：如果测试**意外**通过（即 AI-02 完成了），CI 会报 `XPASS strict` 错误——强制 Codex 删掉 xfail 标记。
- 这种模式比 `skip` 好：skip 完全不跑，xfail 会跑并监控。

## AI-02 完成后的清理

AI-02 patch 跑通后，最后一步就是：

```diff
-@pytest.mark.xfail(strict=True, reason="...")
 def test_structural_pipeline_respects_availability_budget():
```

## 在 benchmark-metrics.md 加 SLO 阈值表

```markdown
## SLO 阈值参考

| 指标 | Demo 阈值（pytest） | 生产 SLO | 处置 |
| --- | --- | --- | --- |
| `collision_rate` | 0 | < 10⁻⁶/mile | P0 回退 PR |
| `planner_emergency_rate` | ≤ 10% | < 0.5% | P1 告警 + 冻结 nominal 升级 |
| `cbf_fallback_rate` | ≤ 10% | < 5% | P1 告警 + 自动收紧 nominal |
| `mean_step_time_ms` P99 | < 15 ms | < 15 ms | P1 降频 |

> demo 阈值给 pytest 用；生产 SLO 来自 [knowledge-base.html §6.1](../knowledge-base.html#sre-slo)。
```

## 验收

- `pytest tests/test_benchmark_metrics.py::test_structural_pipeline_respects_availability_budget` 输出 `xfail`（当 AI-02 未完成时）；
- AI-02 完成后输出 `pass` 且 xfail 标记已被移除；
- `benchmark-metrics.md` 末尾有"SLO 阈值参考"表。
