"""Demo — ego vehicle negotiating an intersection with static + dynamic
obstacles using the structural planner (§4).

Run::

    python -m examples.demo_intersection
"""

from __future__ import annotations

import numpy as np

from auto_decide.dynamics import BicycleModel, CircleObstacle, Manifold
from auto_decide.graph import InteractionIntentGraph, Node
from auto_decide.planner import StructuralPlanner
from auto_decide.potential import PotentialField
from auto_decide.types import AgentType, State


def build_scene():
    # Static obstacles: a parked vehicle and a traffic island
    obstacles = [
        CircleObstacle(cx=22.0, cy=2.5, radius=1.8),
        CircleObstacle(cx=35.0, cy=-1.0, radius=1.5),
    ]
    manifold = Manifold(obstacles=obstacles)

    graph = InteractionIntentGraph()
    graph.add_node(Node("ego", AgentType.EGO,
                        position=np.array([0.0, 0.0]),
                        velocity=np.array([8.0, 0.0])))
    graph.add_node(Node("oncoming", AgentType.CAR,
                        position=np.array([40.0, 3.5]),
                        velocity=np.array([-9.0, 0.0]),
                        intent={"straight": 0.6, "left": 0.3, "right": 0.0,
                                "yield": 0.1, "stop": 0.0}))
    graph.update()
    return manifold, graph


def main() -> None:
    manifold, graph = build_scene()

    potential = PotentialField(goal=np.array([60.0, 3.5]),
                               w_goal=0.05, w_obs=15.0, w_interact=4.0)
    planner = StructuralPlanner(
        dynamics=BicycleModel(), manifold=manifold,
        target_speed=9.0, potential=potential,
    )

    start = State(px=0.0, py=0.0, psi=0.0, v=6.0, a=0.0, mu=1.0)
    states, controls, traces = planner.run(start, graph,
                                            horizon_steps=150, dt=0.1,
                                            trace_path="trace.jsonl")

    # Summary
    min_dist = min(manifold.min_distance(s) for s in states)
    final = states[-1]
    print(f"Ran {len(controls)} control steps.")
    print(f"Final (px, py, v) = ({final.px:.2f}, {final.py:.2f}, {final.v:.2f})")
    print(f"Minimum obstacle clearance: {min_dist:.2f} m")
    print(f"Number of emergency-brake steps: "
          f"{sum(1 for t in traces if t['status'] == 'emergency_brake')}")
    print("Trace logged to trace.jsonl")


if __name__ == "__main__":
    main()
