"""Benchmark — pure end-to-end policy vs. structural planner (§3.3).

Runs ``N`` random long-tail scenarios (low friction + sudden obstacle)
and reports collision rate, comfort (jerk RMS), and mean compute time.

.. note::
   The scenarios here are deliberately **recoverable** — they give the
   ego enough runway to brake if it reacts correctly. Physically
   impossible configurations (μ=0.25 with an obstacle 12m ahead at
   12 m/s) would collide even with a perfect planner, so the contrast
   with the pure end-to-end policy would be blurred. The §2.2 "dead
   zone" detector is the right tool for that kind of scenario.

Run::

    python -m examples.compare_e2e_vs_structural
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np

from auto_decide.dynamics import BicycleModel, CircleObstacle, Manifold
from auto_decide.graph import InteractionIntentGraph
from auto_decide.planner import GradientPolicy, StructuralPlanner
from auto_decide.potential import PotentialField
from auto_decide.types import Control, State


@dataclass
class Scenario:
    mu: float
    obstacle_x: float
    obstacle_y: float


def make_scenarios(n: int, seed: int = 0) -> List[Scenario]:
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        out.append(Scenario(
            mu=float(rng.uniform(0.35, 0.9)),
            obstacle_x=float(rng.uniform(25.0, 45.0)),
            obstacle_y=float(rng.uniform(-1.5, 1.5)),
        ))
    return out


def _pure_e2e_step(policy: GradientPolicy, state: State,
                   graph: InteractionIntentGraph,
                   dyn: BicycleModel, dt: float
                   ) -> Tuple[State, Control]:
    """Unfiltered policy — directly apply the nominal command."""
    u = policy(state, graph)
    return dyn.step(state, u, dt), u


def run_scenario(scn: Scenario, structural: bool, horizon: int = 100,
                 dt: float = 0.1) -> dict:
    obstacles = [CircleObstacle(scn.obstacle_x, scn.obstacle_y, 1.8)]
    manifold = Manifold(obstacles=obstacles)
    potential = PotentialField(goal=np.array([60.0, 0.0]), w_goal=0.05,
                               w_obs=20.0)
    dyn = BicycleModel()

    graph = InteractionIntentGraph()
    graph.update()
    initial = State(px=0.0, py=0.0, psi=0.0, v=12.0, a=0.0, mu=scn.mu)

    if structural:
        planner = StructuralPlanner(
            dynamics=dyn, manifold=manifold, target_speed=12.0,
            potential=potential,
        )
        t0 = time.perf_counter()
        states, controls, _ = planner.run(initial, graph,
                                           horizon_steps=horizon, dt=dt)
        elapsed = time.perf_counter() - t0
    else:
        policy = GradientPolicy(potential, manifold, target_speed=12.0)
        states = [initial]
        controls: List[Control] = []
        cur = initial
        t0 = time.perf_counter()
        for _ in range(horizon):
            cur, u = _pure_e2e_step(policy, cur, graph, dyn, dt)
            states.append(cur)
            controls.append(u)
        elapsed = time.perf_counter() - t0

    min_clear = min(manifold.min_distance(s) for s in states)
    jerks = np.array([c.jerk for c in controls])
    return {
        "collided": bool(min_clear < 0.0),
        "min_clear": float(min_clear),
        "jerk_rms": float(np.sqrt(np.mean(jerks * jerks))) if len(jerks) else 0.0,
        "elapsed_ms": elapsed * 1000.0 / max(horizon, 1),
    }


def summarise(name: str, results: List[dict]) -> None:
    n = len(results)
    collisions = sum(r["collided"] for r in results)
    avg_clear = np.mean([r["min_clear"] for r in results])
    avg_jerk = np.mean([r["jerk_rms"] for r in results])
    avg_ms = np.mean([r["elapsed_ms"] for r in results])
    print(f"=== {name} ===")
    print(f"  scenarios     : {n}")
    print(f"  collision rate: {collisions / n:.2%}  ({collisions}/{n})")
    print(f"  avg clearance : {avg_clear:+.2f} m")
    print(f"  jerk RMS      : {avg_jerk:.2f} m/s^3")
    print(f"  mean step time: {avg_ms:.2f} ms")


def main(n: int = 50) -> None:
    scenarios = make_scenarios(n)
    e2e = [run_scenario(s, structural=False) for s in scenarios]
    struct = [run_scenario(s, structural=True) for s in scenarios]
    summarise("Pure end-to-end (no filter)", e2e)
    summarise("Structural (CBF + T_inv)", struct)


if __name__ == "__main__":
    main()
