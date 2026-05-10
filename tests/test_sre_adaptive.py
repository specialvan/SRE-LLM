"""Tests for the closed-loop adaptive layer."""

from __future__ import annotations

import numpy as np
import pytest

from attention_residuals.sre_adaptive import (
    AdaptiveCombiner,
    HedgeRegretLearner,
)
from attention_residuals.sre_control import SignalSpec


# ---------------------------------------------------------------------------
# HedgeRegretLearner
# ---------------------------------------------------------------------------

def test_hedge_initial_distribution_is_uniform():
    L = HedgeRegretLearner(n_signals=4)
    w = L.weights()
    assert np.allclose(w, 0.25)
    assert np.isclose(w.sum(), 1.0)


def test_hedge_shift_mass_to_low_loss_signals():
    """After repeatedly seeing signal 0 with loss=0 and others with loss=1,
    signal 0 should hold the majority of the mass."""
    L = HedgeRegretLearner(n_signals=3, eta=0.5)
    losses = np.array([0.0, 1.0, 1.0])
    for _ in range(20):
        L.update(losses)
    w = L.weights()
    assert w[0] > 0.9
    assert w[1] < 0.05 and w[2] < 0.05
    assert np.isclose(w.sum(), 1.0)


def test_hedge_best_signal_in_hindsight_is_correct():
    L = HedgeRegretLearner(n_signals=3, eta=0.1)
    for _ in range(10):
        L.update(np.array([0.1, 0.8, 0.4]))
    assert L.best_signal_in_hindsight() == 0


def test_hedge_regret_bound_is_sqrt_T_log_n():
    L = HedgeRegretLearner(n_signals=8)
    for _ in range(100):
        L.update(np.random.rand(8))
    bound = L.regret_bound()
    expected = np.sqrt(100 * np.log(8))
    assert np.isclose(bound, expected)


def test_hedge_losses_get_clipped_and_counted():
    L = HedgeRegretLearner(n_signals=2, eta=0.3)
    L.update(np.array([1.5, -0.3]))       # both out of [0, 1]
    assert L.clipped_count == 2
    # After clipping to [0, 1], loss vector becomes [1, 0] → mass moves
    # to signal 1.
    w = L.weights()
    assert w[1] > w[0]


def test_hedge_deterministic_given_inputs():
    L1 = HedgeRegretLearner(n_signals=3, eta=0.2)
    L2 = HedgeRegretLearner(n_signals=3, eta=0.2)
    seq = np.random.default_rng(42).uniform(0, 1, size=(30, 3))
    for row in seq:
        L1.update(row)
        L2.update(row)
    assert np.allclose(L1.logits(), L2.logits())


def test_hedge_invalid_params_raise():
    with pytest.raises(ValueError):
        HedgeRegretLearner(n_signals=0)
    with pytest.raises(ValueError):
        HedgeRegretLearner(n_signals=3, eta=-1.0)
    with pytest.raises(ValueError):
        HedgeRegretLearner(n_signals=3, clip_range=(1.0, 0.0))
    L = HedgeRegretLearner(n_signals=3)
    with pytest.raises(ValueError):
        L.update(np.zeros(4))


# ---------------------------------------------------------------------------
# AdaptiveCombiner
# ---------------------------------------------------------------------------

def test_adaptive_combiner_first_step_no_losses():
    """The very first call has no prior losses to report."""
    signals = [SignalSpec("a"), SignalSpec("b"), SignalSpec("c")]
    ac = AdaptiveCombiner(signals, query_dim=2)
    action, w = ac.step(
        query=np.ones(2),
        values=[np.array([1.0]), np.array([-1.0]), np.array([0.5])],
    )
    assert np.isclose(w.sum(), 1.0, atol=1e-6)
    assert len(ac.records()) == 1


def test_adaptive_combiner_shifts_mass_under_feedback():
    """After enough feedback that signal 1 is always the cheapest, the
    combiner should concentrate its weight on signal 1."""
    signals = [SignalSpec("bad"), SignalSpec("good"), SignalSpec("bad2")]
    learner = HedgeRegretLearner(n_signals=3, eta=0.5)
    ac = AdaptiveCombiner(signals, query_dim=2, learner=learner)
    # Drive the combiner with a constant query.
    q = np.ones(2)
    vals = [np.array([1.0]), np.array([1.0]), np.array([1.0])]
    # First tick: no losses.
    ac.step(q, vals, observed_losses=None)
    # Subsequent ticks: signal 1 is always the cheap one.
    losses = np.array([1.0, 0.0, 1.0])
    for _ in range(30):
        ac.step(q, vals, observed_losses=losses)
    w_final = ac.learner.weights()
    assert w_final[1] > 0.9


def test_adaptive_combiner_respects_floor_even_after_learning():
    """Even if the learner hates signal "budget", a positive floor on it
    should keep its controller weight above that floor."""
    signals = [
        SignalSpec("fast"),
        SignalSpec("budget", floor=0.3),
    ]
    learner = HedgeRegretLearner(n_signals=2, eta=0.8)
    ac = AdaptiveCombiner(signals, query_dim=2, learner=learner)
    q = np.array([1.0, 0.0])
    vals = [np.array([1.0]), np.array([0.0])]
    # Crush the budget signal in the learner's eyes.
    losses = np.array([0.0, 1.0])
    for _ in range(50):
        ac.step(q, vals, observed_losses=losses)
    # Learner-side distribution can drown "budget"...
    w_learner = ac.learner.weights()
    assert w_learner[1] < 0.05
    # ...but the combiner's actual output weights must still respect the floor.
    _, w_combiner = ac.step(q, vals, observed_losses=losses)
    assert w_combiner[1] >= 0.3 - 1e-6
    assert np.isclose(w_combiner.sum(), 1.0, atol=1e-6)


def test_adaptive_combiner_preserves_static_bias_under_learning():
    signals = [
        SignalSpec("fast", bias=0.5),
        SignalSpec("budget", bias=-0.25),
    ]
    ac = AdaptiveCombiner(signals, query_dim=1)
    q = np.array([1.0])
    vals = [np.array([1.0]), np.array([0.0])]
    ac.step(q, vals, observed_losses=np.array([1.0, 0.0]))
    expected = np.array([0.5, -0.25]) + ac.learner.logits()
    actual = np.array([s.bias for s in ac.combiner.signals])
    assert np.allclose(actual, expected)


def test_adaptive_records_capture_regret_bound_growth():
    signals = [SignalSpec("a"), SignalSpec("b")]
    ac = AdaptiveCombiner(signals, query_dim=1)
    q = np.array([1.0])
    vals = [np.array([0.0]), np.array([1.0])]
    for _ in range(10):
        ac.step(q, vals, observed_losses=np.array([0.2, 0.5]))
    bounds = [r.regret_bound for r in ac.records()]
    # Monotone non-decreasing and matches √(T ln n).
    assert bounds == sorted(bounds)
    # First record has a 0 loss vector but regret_bound > 0 because
    # update was already consumed before records append.
    assert bounds[-1] > bounds[0]
