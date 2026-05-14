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


def test_cox_model_baseline_properties():
    """Test CoxModel baseline hazard properties."""
    model = CoxModel(beta=np.array([1.0]), _baseline_t=np.array([1.0, 10.0]), _baseline_H=np.array([0.1, 0.5]))
    assert hasattr(model, '_baseline_t')
    assert hasattr(model, '_baseline_H')


def test_cox_model_survival():
    """Test CoxModel survival method."""
    model = CoxModel(
        beta=np.array([0.5, -0.3]),
        _baseline_t=np.array([1.0, 24.0, 48.0]),
        _baseline_H=np.array([0.01, 0.1, 0.3]),
    )
    X = np.array([[1.0, 0.5], [0.5, 1.0]])
    surv = model.survival(X, t=24.0)
    assert surv.shape == (2,)
    assert np.all(surv >= 0)
    assert np.all(surv <= 1)


def test_cox_model_partial_hazard():
    """Test CoxModel partial_hazard method."""
    model = CoxModel(
        beta=np.array([0.5, -0.3]),
        _baseline_t=np.array([1.0, 24.0]),
        _baseline_H=np.array([0.01, 0.1]),
    )
    X = np.array([[1.0, 0.5]])
    ph = model.partial_hazard(X)
    assert ph.shape == (1,)
    assert np.all(ph >= 0)


def test_cox_model_cumulative_hazard():
    """Test CoxModel cumulative_hazard method."""
    model = CoxModel(
        beta=np.array([0.5, -0.3]),
        _baseline_t=np.array([1.0, 24.0, 48.0]),
        _baseline_H=np.array([0.01, 0.1, 0.3]),
    )
    X = np.array([[1.0, 0.5]])
    ch = model.cumulative_hazard(X, t=12.0)
    assert ch.shape == (1,)


def test_churn_monitor_with_custom_threshold():
    """Test ChurnRiskMonitor with custom warning threshold."""
    mon = ChurnRiskMonitor(warn_threshold=0.3, alarm_threshold=0.6)
    assert mon.level(0.2) == "ok"
    assert mon.level(0.4) == "warn"
    assert mon.level(0.7) == "alarm"


def test_churn_monitor_predict_range():
    """Test ChurnRiskMonitor.predict returns values in [0, 1]."""
    mon = ChurnRiskMonitor()
    for features in [[0], [5], [10], [1, 2, 3, 4]]:
        p = mon.predict(features)
        assert 0.0 <= p <= 1.0


def test_cox_model_untrained():
    """Test CoxModel before fitting."""
    model = CoxModel()
    assert model.beta is None
    assert hasattr(model, '_baseline_t')
    assert hasattr(model, '_baseline_H')
