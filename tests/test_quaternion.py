import numpy as np
from scipy.spatial.transform import Rotation

from starship.quaternion import Quaternion, integrate_quaternion


def test_multiplication_matches_scipy():
    q1 = Quaternion.from_axis_angle([0, 0, 1], 0.3)
    q2 = Quaternion.from_axis_angle([1, 0, 0], 0.5)
    q = q1 * q2
    # scipy uses [x, y, z, w] order
    r1 = Rotation.from_quat([q1.x, q1.y, q1.z, q1.w])
    r2 = Rotation.from_quat([q2.x, q2.y, q2.z, q2.w])
    expected = (r1 * r2).as_matrix()
    assert np.allclose(q.to_matrix(), expected, atol=1e-10)


def test_integration_preserves_unit_norm():
    q = np.array([1, 0, 0, 0.0])
    w = np.array([0.3, -0.2, 0.1])
    for _ in range(1000):
        q = integrate_quaternion(q, w, 0.01)
    assert abs(np.linalg.norm(q) - 1.0) < 1e-8


def test_identity_rotation():
    q = Quaternion.identity()
    assert np.allclose(q.to_matrix(), np.eye(3))
