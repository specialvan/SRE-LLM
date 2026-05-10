import numpy as np

from starship.thrust_constraints import (ConeQPFilter,
                                         pointing_cone_constraint)


def test_inside_cone_untouched():
    filt = ConeQPFilter(n_hat=np.array([0, 0, 1.0]),
                        theta_max=np.deg2rad(15),
                        T_max=2.0)
    u = np.array([0.0, 0.0, 1.0])
    assert np.allclose(filt.filter(u), u)


def test_outside_cone_gets_pulled_in():
    filt = ConeQPFilter(n_hat=np.array([0, 0, 1.0]),
                        theta_max=np.deg2rad(15),
                        T_max=2.0)
    u = np.array([1.0, 0.0, 0.2])                  # way off axis
    u_new = filt.filter(u)
    # cone margin should now be ≥ 0 (non-negative, possibly 1e-8 tol)
    margin = pointing_cone_constraint(u_new, np.array([0, 0, 1.0]),
                                      np.deg2rad(15))
    assert margin > -1e-6


def test_magnitude_saturation():
    filt = ConeQPFilter(n_hat=np.array([0, 0, 1.0]),
                        theta_max=np.deg2rad(30),
                        T_max=1.0)
    u = np.array([0.0, 0.0, 5.0])
    u_new = filt.filter(u)
    assert np.linalg.norm(u_new) <= 1.0 + 1e-9
