"""Tests for Cox survival model (§8)."""
from __future__ import annotations

import numpy as np

from gan_matchmaking import ChurnRiskMonitor, CoxModel


def test_cox_beta_sign_matches_truth():
    rng = np.random.default_rng(123)
    n = 400
    X = rng.normal(size=(n, 1))
    beta_true = np.array([1.2])
    # Generate exponential times with rate = exp(beta^T x).
    rates = np.exp(X @ beta_true)
    T = rng.exponential(1.0 / rates.ravel())
    events = np.ones(n)
    model = CoxModel().fit(X, T, events, lr=1.0, iters=2000)
    assert model.beta is not None
    # Sign should match and magnitude should be positive.
    assert model.beta[0] > 0.5


def test_churn_monitor_untrained_graceful():
    mon = ChurnRiskMonitor()
    p0 = mon.predict([0])
    p5 = mon.predict([5])
    assert p0 < p5
    assert 0.0 <= p0 <= 1.0 and 0.0 <= p5 <= 1.0
    assert mon.level(0.1) == "ok"
    assert mon.level(0.4) == "warn"
    assert mon.level(0.7) == "alarm"
