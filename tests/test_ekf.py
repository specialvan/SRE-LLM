import numpy as np

from starship.ekf import EKF


def test_1d_constant_velocity_tracks_truth():
    # x = [p, v], measurement = p
    def f(x, u, dt):
        return np.array([x[0] + x[1] * dt, x[1]])

    def F(x, u, dt):
        return np.array([[1.0, dt], [0.0, 1.0]])

    ekf = EKF(x=np.array([0.0, 0.0]),
              P=np.eye(2) * 10.0,
              process_noise=np.eye(2) * 1e-3,
              f=f, F_jac=F)

    rng = np.random.default_rng(0)
    truth = np.array([0.0, 1.5])
    dt = 0.1
    for _ in range(100):
        truth = f(truth, None, dt)
        ekf.predict(None, dt)
        z = truth[0] + rng.normal(0, 0.2)
        ekf.update(np.array([z]),
                   h=lambda x: np.array([x[0]]),
                   H=lambda x: np.array([[1.0, 0.0]]),
                   R=np.array([[0.04]]))
    assert abs(ekf.x[0] - truth[0]) < 0.5
    assert abs(ekf.x[1] - truth[1]) < 0.5
