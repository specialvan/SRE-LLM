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


def test_update_keeps_covariance_symmetric_after_repeated_linear_updates():
    def f(x, u, dt):
        return x

    def F(x, u, dt):
        return np.eye(2)

    ekf = EKF(
        x=np.array([0.0, 0.0]),
        P=np.array([[1.0, 0.35], [0.35, 2.0]]),
        process_noise=np.eye(2) * 1e-6,
        f=f,
        F_jac=F,
    )

    for _ in range(40):
        ekf.predict(None, 1.0)
        ekf.update(
            np.array([0.1, -0.2]),
            h=lambda x: x,
            H=lambda x: np.eye(2),
            R=np.array([[1e-4, 2e-5], [2e-5, 2e-4]]),
        )

    assert np.allclose(ekf.P, ekf.P.T, atol=1e-12)


def test_update_keeps_covariance_psd_under_near_perfect_measurement():
    def f(x, u, dt):
        return x

    def F(x, u, dt):
        return np.eye(2)

    ekf = EKF(
        x=np.array([1.0, -1.0]),
        P=np.array([[2.0, 1.2], [1.2, 1.5]]),
        process_noise=np.eye(2) * 1e-8,
        f=f,
        F_jac=F,
    )

    for _ in range(25):
        ekf.predict(None, 1.0)
        ekf.update(
            np.array([1.0, -1.0]),
            h=lambda x: x,
            H=lambda x: np.eye(2),
            R=np.array([[1e-8, 0.0], [0.0, 1e-8]]),
        )

    assert np.min(np.linalg.eigvalsh(ekf.P)) >= -1e-12


def test_gated_update_leaves_state_and_covariance_unchanged():
    def f(x, u, dt):
        return x

    def F(x, u, dt):
        return np.eye(2)

    ekf = EKF(
        x=np.array([0.0, 0.0]),
        P=np.array([[1.0, 0.2], [0.2, 1.0]]),
        process_noise=np.eye(2) * 1e-6,
        f=f,
        F_jac=F,
    )
    x_before = ekf.x.copy()
    p_before = ekf.P.copy()

    result = ekf.update(
        np.array([50.0, -50.0]),
        h=lambda x: x,
        H=lambda x: np.eye(2),
        R=np.eye(2) * 1e-4,
        gate_threshold=3.0,
    )

    assert result["gated"] is True
    assert np.array_equal(ekf.x, x_before)
    assert np.array_equal(ekf.P, p_before)
