import numpy as np

from starship.rigid_body import RigidBody
from starship.types import State6DOF, VehicleParams


def test_free_fall_with_zero_forces():
    body = RigidBody(VehicleParams(), deplete_mass=False)
    s = State6DOF(r=np.array([0, 0, 100.0]), v=np.zeros(3))
    dt = 0.01
    for _ in range(200):                  # 2 s of free fall
        s = body.step(s, np.zeros(3), np.zeros(3), dt)
    # z(2) = z0 + 0.5 g t^2
    expected = 100 + 0.5 * (-9.80665) * 4.0
    assert abs(s.r[2] - expected) < 0.2


def test_pure_z_torque_spins_body():
    body = RigidBody(VehicleParams(inertia=np.diag([1.0, 1.0, 1.0])),
                     deplete_mass=False)
    s = State6DOF()
    s.m = 1.0
    # Note : we give the torque in body frame — zero initial ω keeps the
    # Euler term ω × Jω zero.
    for _ in range(100):
        s = body.step(s, np.zeros(3), np.array([0, 0, 0.5]), 0.01)
    # expected ω_z = 0.5 rad/s
    assert abs(s.w[2] - 0.5) < 1e-6
