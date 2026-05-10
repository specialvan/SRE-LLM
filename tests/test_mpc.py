import numpy as np

from starship.mpc import LinearDiscretizer, QuadraticMPC


def test_double_integrator_regulation():
    A = np.array([[0.0, 1.0], [0.0, 0.0]])
    B = np.array([[0.0], [1.0]])
    Ad, Bd = LinearDiscretizer(A, B).zoh(0.1)
    mpc = QuadraticMPC(A=Ad, B=Bd,
                       Q=np.diag([10.0, 1.0]), R=np.array([[0.1]]),
                       P=np.diag([100.0, 10.0]),
                       N=15,
                       u_min=np.array([-1.0]), u_max=np.array([1.0]))
    x = np.array([5.0, 0.0])
    for _ in range(60):
        u = mpc.step(x)
        x = Ad @ x + Bd.flatten() * float(u[0])
    # Should have driven close to zero (minimum-time ≈ 4.5 s, horizon is
    # only 1.5 s so we need more steps + a bit of tolerance).
    assert np.linalg.norm(x) < 0.3
