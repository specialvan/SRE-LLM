# Patch 01 · Barrier-aware Nominal Policy

- **Action item**：[AI-02](../05-action-items.md#ai-02)
- **Target**：降低 `planner_emergency_rate` 从 42.5% 到 ≤ 10%，同时保持 `collision_rate = 0`。
- **Non-goal**：不引入 ML 依赖。最小 numpy 实现。

## 动机

上一轮 `GradientPolicy` 按势能梯度给建议，**不感知 CBF barrier**。于是每次接近障碍，建议里都还带着 `jerk > 0`，CBF 只好降级到 fallback_brake。

下面提供两级实现，Codex 任选一级（推荐先做 PredictiveBrakePolicy）：

1. **PredictiveBrakePolicy**：在 GradientPolicy 基础上做 `t_lookahead` 秒前瞻，若预见会破 barrier 则主动减速；
2. **BarrierAwareMPC**：开环 MPC 解一个 3~5 步的 QP，把尾部动作收敛到刹停——更精确但更复杂。

## 1 · PredictiveBrakePolicy 实现骨架

### 新文件：`auto_decide/policies/__init__.py`

```python
"""Nominal policy implementations.

The default ``GradientPolicy`` (in planner.py) is kept for baseline.
New policies live here to keep planner.py purely an orchestrator.
"""
from .predictive_brake import PredictiveBrakePolicy

__all__ = ["PredictiveBrakePolicy"]
```

### 新文件：`auto_decide/policies/predictive_brake.py`

```python
"""Predictive-brake nominal policy (AI-02).

This policy extends ``GradientPolicy`` by:
- simulating the next ``t_lookahead`` seconds with the nominal command,
- checking any barrier's ``h`` at the predicted state,
- and throttling ``jerk`` downward if a violation is predicted.

It is intentionally simple (no QP, no ML) so the logic can be audited
by reviewer without domain expertise.

Invariants preserved:
- Output is still a ``Control``, still bounded by ``VehicleParams``;
- Does not bypass planner.step (this is a nominal, not executor);
- Degrades to the wrapped policy's output when no barrier is at risk.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional

from ..cbf import BarrierFunction
from ..dynamics import BicycleModel
from ..graph import InteractionIntentGraph
from ..planner import GradientPolicy
from ..types import Control, State, VehicleParams


@dataclass
class PredictiveBrakePolicy:
    """Wraps ``GradientPolicy`` with a barrier-aware pre-brake guard.

    The policy queries each provided barrier function with the state
    reached by applying the nominal command for ``t_lookahead`` seconds.
    If any barrier would turn negative, ``jerk`` is clamped to a
    conservative decelerating value before it reaches the CBF.

    Parameters
    ----------
    inner
        The underlying nominal policy (typically ``GradientPolicy``).
    barriers
        The same barrier list the CBF filter uses.
    dynamics
        Bicycle model used for short-horizon simulation.
    t_lookahead
        Horizon for the look-ahead simulation, seconds.
    brake_jerk
        Jerk used when a barrier violation is predicted.
    """
    inner: GradientPolicy
    barriers: List[BarrierFunction]
    dynamics: BicycleModel
    t_lookahead: float = 0.4
    brake_jerk: float = -3.0

    def __call__(self,
                 state: State,
                 graph: Optional[InteractionIntentGraph] = None) -> Control:
        u = self.inner(state, graph)
        # Short-horizon rollout with the nominal command held constant
        steps = max(1, int(self.t_lookahead / 0.1))
        ctrls = [u] * steps
        traj = self.dynamics.rollout(state, ctrls, dt=0.1)
        # Evaluate barriers on the predicted terminal state
        predicted = traj[-1]
        at_risk = any(b.h(predicted) < 0 for b in self.barriers)
        if at_risk:
            u = Control(u.steer, min(u.jerk, self.brake_jerk))
        return u
```

### 注入到 StructuralPlanner

在 `auto_decide/planner.py::StructuralPlanner.__post_init__` 末尾（在 `self.t_inv` 构造之后）加：

```python
        # If the caller did not override self.nominal, upgrade the
        # default GradientPolicy with the predictive-brake guard.
        from .policies import PredictiveBrakePolicy
        if isinstance(self.nominal, GradientPolicy):
            self.nominal = PredictiveBrakePolicy(
                inner=self.nominal,
                barriers=self.cbf.barriers,
                dynamics=self.dynamics,
            )
```

不要在 `__init__` 里写死，保持 "测试可以注入 raw GradientPolicy" 的能力。

## 2 · 新增测试：`tests/test_policies.py`

```python
"""Tests for nominal policy upgrades (AI-02)."""

import numpy as np

from auto_decide.dynamics import BicycleModel, CircleObstacle, Manifold
from auto_decide.cbf import make_obstacle_barriers
from auto_decide.graph import InteractionIntentGraph
from auto_decide.planner import GradientPolicy, StructuralPlanner
from auto_decide.policies import PredictiveBrakePolicy
from auto_decide.potential import PotentialField
from auto_decide.types import State


def test_predictive_brake_wraps_gradient_policy():
    manifold = Manifold(obstacles=[CircleObstacle(20.0, 0.0, 2.0)])
    pot = PotentialField(goal=np.array([50.0, 0.0]), w_goal=0.05)
    inner = GradientPolicy(pot, manifold, target_speed=12.0)
    barriers = make_obstacle_barriers(manifold, margin=1.5)
    wrapped = PredictiveBrakePolicy(
        inner=inner, barriers=barriers, dynamics=BicycleModel(),
    )
    state = State(px=0.0, py=0.0, psi=0.0, v=12.0, a=0.0, mu=1.0)
    graph = InteractionIntentGraph()
    graph.update()

    u = wrapped(state, graph)
    # Obstacle is 20m ahead at v=12: predictive brake should kick in.
    assert u.jerk <= -2.0


def test_predictive_brake_does_not_brake_when_no_obstacle_nearby():
    manifold = Manifold(obstacles=[CircleObstacle(200.0, 0.0, 2.0)])
    pot = PotentialField(goal=np.array([50.0, 0.0]), w_goal=0.05)
    inner = GradientPolicy(pot, manifold, target_speed=12.0)
    barriers = make_obstacle_barriers(manifold, margin=1.5)
    wrapped = PredictiveBrakePolicy(
        inner=inner, barriers=barriers, dynamics=BicycleModel(),
    )
    state = State(px=0.0, py=0.0, psi=0.0, v=8.0, a=0.0, mu=1.0)
    graph = InteractionIntentGraph()
    graph.update()

    u_inner = inner(state, graph)
    u_wrapped = wrapped(state, graph)
    # No barrier at risk: wrapped should equal inner
    assert u_wrapped.jerk == u_inner.jerk


def test_structural_planner_auto_wraps_gradient_policy():
    manifold = Manifold(obstacles=[CircleObstacle(20.0, 0.0, 2.0)])
    planner = StructuralPlanner(dynamics=BicycleModel(), manifold=manifold,
                                target_speed=12.0)
    # The planner __post_init__ should have upgraded the nominal
    assert isinstance(planner.nominal, PredictiveBrakePolicy)
```

## 3 · 预期效果

运行 `python -m examples.compare_e2e_vs_structural --n 50 --seed 0` 应看到：

- `planner_emergency_rate` 从 42% 降到 < 10%；
- `cbf_fallback_rate` 从 23% 降到 < 10%；
- `collision_rate` 仍为 0%；
- `avg_clearance_m` 可能略降（因为预刹早了），但 > 2 m；
- `avg_jerk_rms_mps3` 可能略升（更多主动减速），可接受。

## 4 · 如果达不到预期

两步调：
- **brake_jerk 调更狠**（如 -5）：更保守但可能过度干预；
- **t_lookahead 调更长**（如 0.8）：预见更远但延迟增大。

不要调：
- `cbf_alpha`；
- `game.base_buffer`；
- `GradientPolicy` 内部的势能权重；

这些都是绕过 AI-02 的做法。

## 5 · 后续演进（不在本 patch 范围）

- BarrierAwareMPC：真正的 3-step 开环 QP；
- 用 `planner.run()` 的 `u_safe` 数据训练一个 imitation policy 替换 PredictiveBrakePolicy；
- 加入 `game.WorstCaseGame` 的 belief 信号（AI-02 的下一级）。
