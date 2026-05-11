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

.. note::
   **Sanctioned INV-G2 exception (AI-09).**
   :func:`_pure_e2e_step` intentionally calls ``dyn.step`` directly to
   establish a baseline *without* CBF / T_inv guarding. This is the
   only sanctioned caller of ``dynamics.step`` outside of
   ``auto_decide/{cbf,lyapunov,reachable,invariant,planner}.py``.
   Any static-analysis (e.g. ``scripts/check_invariants.py`` from
   [AI-11]) must whitelist this file. Do not copy this pattern into
   production code paths — the whole point of the benchmark is to
   *prove* the guarded pipeline is safer.

Run::

    python -m examples.compare_e2e_vs_structural

Machine-readable metrics for review dashboards::

    python -m examples.compare_e2e_vs_structural --metrics-out metrics.json
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
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

    def to_dict(self) -> dict:
        return {
            "mu": self.mu,
            "obstacle_x": self.obstacle_x,
            "obstacle_y": self.obstacle_y,
        }


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
    """Unfiltered policy — directly apply the nominal command.

    .. warning::
       Sanctioned **INV-G2** bypass (AI-09): this is the *only* function
       outside ``auto_decide.{planner,cbf,lyapunov,reachable,invariant}``
       that calls ``dyn.step`` directly. It exists solely to produce the
       baseline row in the benchmark. See module docstring.
    """
    u = policy(state, graph)
    return dyn.step(state, u, dt), u  # noqa: INV-G2 intentional baseline bypass


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
        states, controls, traces = planner.run(initial, graph,
                                               horizon_steps=horizon, dt=dt)
        elapsed = time.perf_counter() - t0
    else:
        policy = GradientPolicy(potential, manifold, target_speed=12.0)
        states = [initial]
        controls: List[Control] = []
        traces = []
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
        "steps": int(horizon),
        "cbf_status_counts": dict(Counter(
            tr.get("cbf_status") for tr in traces if tr.get("cbf_status")
        )),
        "planner_status_counts": dict(Counter(
            tr.get("status") for tr in traces if tr.get("status")
        )),
    }


def summarise_results(name: str, results: List[dict]) -> dict:
    n = len(results)
    collisions = sum(r["collided"] for r in results)
    min_clearances = [r["min_clear"] for r in results]
    avg_clear = float(np.mean(min_clearances)) if results else 0.0
    worst_clear = float(np.min(min_clearances)) if results else 0.0
    avg_jerk = float(np.mean([r["jerk_rms"] for r in results])) if results else 0.0
    avg_ms = float(np.mean([r["elapsed_ms"] for r in results])) if results else 0.0
    cbf_counts = Counter()
    planner_counts = Counter()
    total_steps = 0
    for result in results:
        cbf_counts.update(result.get("cbf_status_counts", {}))
        planner_counts.update(result.get("planner_status_counts", {}))
        total_steps += int(result.get("steps", 0))
    cbf_fallback_rate = (
        cbf_counts.get("fallback_brake", 0) / total_steps
        if total_steps else 0.0
    )
    planner_emergency_rate = (
        planner_counts.get("emergency_brake", 0) / total_steps
        if total_steps else 0.0
    )
    planner_best_effort_rate = (
        planner_counts.get("best_effort", 0) / total_steps
        if total_steps else 0.0
    )
    guard_intervention_rate = (
        1.0 - cbf_counts.get("nom_ok", 0) / total_steps
        if total_steps and cbf_counts else 0.0
    )
    return {
        "name": name,
        "scenarios": int(n),
        "collision_count": int(collisions),
        "collision_rate": float(collisions / n) if n else 0.0,
        "avg_clearance_m": avg_clear,
        "worst_clearance_m": worst_clear,
        "avg_jerk_rms_mps3": avg_jerk,
        "mean_step_time_ms": avg_ms,
        "guard_intervention_rate": float(guard_intervention_rate),
        "cbf_fallback_rate": float(cbf_fallback_rate),
        "planner_emergency_rate": float(planner_emergency_rate),
        "planner_best_effort_rate": float(planner_best_effort_rate),
        "cbf_status_counts": dict(cbf_counts),
        "planner_status_counts": dict(planner_counts),
    }


def print_summary(summary: dict) -> None:
    name = summary["name"]
    n = summary["scenarios"]
    collisions = summary["collision_count"]
    print(f"=== {name} ===")
    print(f"  scenarios     : {n}")
    print(f"  collision rate: {summary['collision_rate']:.2%}  ({collisions}/{n})")
    print(f"  avg clearance : {summary['avg_clearance_m']:+.2f} m")
    print(f"  worst clearance: {summary['worst_clearance_m']:+.2f} m")
    print(f"  jerk RMS      : {summary['avg_jerk_rms_mps3']:.2f} m/s^3")
    print(f"  mean step time: {summary['mean_step_time_ms']:.2f} ms")
    if summary["cbf_status_counts"]:
        print(f"  guard touched : {summary['guard_intervention_rate']:.2%}")
        print(f"  CBF fallback  : {summary['cbf_fallback_rate']:.2%}")
        print(f"  CBF statuses  : {summary['cbf_status_counts']}")
    if summary["planner_status_counts"]:
        print(f"  emergency rate: {summary['planner_emergency_rate']:.2%}")
        print(f"  best effort   : {summary['planner_best_effort_rate']:.2%}")
        print(f"  planner status: {summary['planner_status_counts']}")


def build_metrics_payload(*,
                          scenarios: List[Scenario],
                          e2e_results: List[dict],
                          structural_results: List[dict],
                          seed: int,
                          horizon: int,
                          dt: float) -> dict:
    e2e_summary = summarise_results("Pure end-to-end (no filter)", e2e_results)
    structural_summary = summarise_results(
        "Structural (CBF + T_inv)", structural_results
    )
    return {
        "schema_version": "benchmark.metrics.v1",
        "generated_by": "examples.compare_e2e_vs_structural",
        "params": {
            "seed": int(seed),
            "n": len(scenarios),
            "horizon": int(horizon),
            "dt": float(dt),
        },
        "summaries": {
            "pure_e2e": e2e_summary,
            "structural": structural_summary,
        },
        "deltas": {
            "collision_rate_reduction": (
                e2e_summary["collision_rate"]
                - structural_summary["collision_rate"]
            ),
            "avg_clearance_gain_m": (
                structural_summary["avg_clearance_m"]
                - e2e_summary["avg_clearance_m"]
            ),
            "worst_clearance_gain_m": (
                structural_summary["worst_clearance_m"]
                - e2e_summary["worst_clearance_m"]
            ),
            "mean_step_time_delta_ms": (
                structural_summary["mean_step_time_ms"]
                - e2e_summary["mean_step_time_ms"]
            ),
        },
        "scenarios": [s.to_dict() for s in scenarios],
    }


def write_metrics(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )


def run_benchmark(n: int = 50, seed: int = 0, horizon: int = 100,
                  dt: float = 0.1) -> dict:
    scenarios = make_scenarios(n, seed=seed)
    e2e = [run_scenario(s, structural=False, horizon=horizon, dt=dt)
           for s in scenarios]
    struct = [run_scenario(s, structural=True, horizon=horizon, dt=dt)
              for s in scenarios]
    return build_metrics_payload(
        scenarios=scenarios,
        e2e_results=e2e,
        structural_results=struct,
        seed=seed,
        horizon=horizon,
        dt=dt,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--horizon", type=int, default=100)
    parser.add_argument("--dt", type=float, default=0.1)
    parser.add_argument("--metrics-out", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = run_benchmark(
        n=args.n,
        seed=args.seed,
        horizon=args.horizon,
        dt=args.dt,
    )
    print_summary(payload["summaries"]["pure_e2e"])
    print_summary(payload["summaries"]["structural"])
    if args.metrics_out:
        write_metrics(args.metrics_out, payload)
        print(f"Wrote metrics JSON: {args.metrics_out}")


if __name__ == "__main__":
    main()
