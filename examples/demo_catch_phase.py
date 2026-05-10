"""End-to-end demo : last 50 m of the chopstick-catch.

Starts with the booster at 50 m, ~6 m/s descent, 1 m lateral offset
and 5° tilt.  The :class:`RecoveryPipeline` closes the loop through
the :class:`CatchController` + :class:`ThrustAllocator`. At t = 5 s
we print position / velocity error.
"""

from __future__ import annotations

import numpy as np

from starship import (DEFAULT_STARSHIP, CatchGeometry, RecoveryPipeline,
                       RigidBody, State6DOF, ThrusterBank, Thruster)


def _default_bank() -> ThrusterBank:
    th = []
    R = 3.2
    for i in range(3):
        a = i * 2 * np.pi / 3
        th.append(Thruster(
            position=np.array([R * np.cos(a), R * np.sin(a), 0.0]),
            direction=np.array([0.0, 0.0, 1.0]),
            T_min=0.4e6, T_max=2.3e6))
    return ThrusterBank(th)


def main() -> None:
    bank = _default_bank()
    body = RigidBody(params=DEFAULT_STARSHIP, deplete_mass=False)
    pipe = RecoveryPipeline(truth=body, bank=bank, geometry=CatchGeometry())

    # Initial state: 50 m, light lateral offset
    state = State6DOF(
        r=np.array([1.0, 0.5, 50.0]),
        v=np.array([0.0, 0.0, -6.0]),
        q=np.array([1.0, 0.0, 0.0, 0.0]),
        w=np.zeros(3),
        m=200_000.0,
    )

    dt = 0.05
    steps = int(5.0 / dt)
    for k in range(steps):
        state, trace = pipe.step(state, dt)
        if k % 20 == 0:
            print(f"t={k*dt:4.2f}s  alt={state.r[2]:6.2f}m  "
                  f"lateral={trace['lateral_error']:.2f}m "
                  f"window={trace['window']:.2f}m  "
                  f"thrusts={[f'{x/1e6:.2f}MN' for x in trace['thrusts']]}")

    final_err = float(np.hypot(state.r[0], state.r[1]))
    print(f"\nfinal altitude={state.r[2]:.2f} m  lateral err={final_err:.3f} m")


if __name__ == "__main__":
    main()
