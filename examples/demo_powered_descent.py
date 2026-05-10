"""End-to-end demo : powered descent from 300 m to the pad.

Solves a single PDG problem with the §1 lossless-convex formulation,
then rolls the nonlinear :class:`RigidBody` under the resulting thrust
schedule to see how well the solution survives the full dynamics.
"""

from __future__ import annotations

import numpy as np

from starship import RigidBody, State6DOF
from starship.lossless_convex import LosslessPDG


def main() -> None:
    pdg = LosslessPDG(
        r0=np.array([0.0, 0.0, 300.0]),
        v0=np.array([0.0, 0.0, -80.0]),
        m0=250_000.0,
        T=6.0, N=20,
    )
    r, v, Gammas, info = pdg.solve()
    print("PDG solver status :", info)

    # Roll-out the nonlinear body with the thrust schedule to compare
    body = RigidBody()
    body.params.inertia = np.diag([1.0e8, 1.0e8, 5.0e6])
    state = State6DOF(r=pdg.r0.copy(), v=pdg.v0.copy(),
                       q=np.array([1, 0, 0, 0.0]), w=np.zeros(3),
                       m=pdg.m0)

    dt = pdg._dt()
    for k in range(pdg.N):
        # Γ lives in the inertial frame; body aligns with inertial because
        # q=identity, so force_body = Γ here.
        force_body = Gammas[k]
        state = body.step(state, force_body, np.zeros(3), dt)

    print(f"final altitude {state.r[2]:.2f} m  "
          f"vertical v {state.v[2]:+.2f} m/s  "
          f"mass {state.m:.0f} kg")
    print(f"PDG terminal  {r[-1]}  {v[-1]}")


if __name__ == "__main__":
    main()
