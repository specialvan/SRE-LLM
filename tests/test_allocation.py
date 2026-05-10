import numpy as np

from starship.catch_controller import ThrustAllocator
from starship.types import Thruster, ThrusterBank


def _bank():
    th = []
    R = 3.2
    for i in range(3):
        a = i * 2 * np.pi / 3
        th.append(Thruster(
            position=np.array([R * np.cos(a), R * np.sin(a), 0.0]),
            direction=np.array([0.0, 0.0, 1.0]),
            T_min=0.4e6, T_max=2.3e6))
    return ThrusterBank(th)


def test_allocation_reconstructs_pure_vertical_force():
    bank = _bank()
    alloc = ThrustAllocator(bank)
    t, res = alloc.allocate(np.array([0, 0, 3.0e6]), np.zeros(3))
    assert res < 1e-3
    assert np.all(t >= 0.0)
