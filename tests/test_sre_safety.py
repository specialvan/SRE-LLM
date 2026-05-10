"""Tests for the industrial safety layer."""

from __future__ import annotations

import numpy as np
import pytest

from attention_residuals.sre_control import SignalSpec, WeightedConvexCombiner
from attention_residuals.sre_safety import (
    CounterfactualExplainer,
    SafetyEnvelope,
    ShadowRunner,
    WeightDriftDetector,
)


# ---------------------------------------------------------------------------
# SafetyEnvelope
# ---------------------------------------------------------------------------

def test_envelope_clips_absolute_bounds():
    env = SafetyEnvelope(low=np.array([-1.0]), high=np.array([+1.0]))
    clipped, info = env.apply(np.array([+3.0]))
    assert clipped[0] == 1.0
    assert info["clipped"] is True
    assert env.violation_count == 1


def test_envelope_passthrough_when_action_in_range():
    env = SafetyEnvelope(low=np.array([-2.0]), high=np.array([+2.0]))
    out, info = env.apply(np.array([0.5]))
    assert out[0] == 0.5
    assert info["clipped"] is False
    assert env.violation_count == 0


def test_envelope_rate_limits_delta_between_ticks():
    env = SafetyEnvelope(
        low=np.array([-10.0]),
        high=np.array([+10.0]),
        max_delta=np.array([1.0]),
    )
    # First tick: no prior, just clipped to absolute range.
    a1, _ = env.apply(np.array([+3.0]))
    assert a1[0] == 3.0
    # Second tick: action asks for +6, but max_delta is 1 from previous (3).
    a2, info = env.apply(np.array([+6.0]))
    assert np.isclose(a2[0], 4.0)
    assert info["clipped"] is True


def test_envelope_shape_mismatch_raises():
    env = SafetyEnvelope(low=np.array([0.0]), high=np.array([1.0]))
    with pytest.raises(ValueError):
        env.apply(np.array([0.0, 0.0]))


def test_envelope_construction_invariants():
    with pytest.raises(ValueError):
        SafetyEnvelope(low=np.array([0.0, 2.0]), high=np.array([1.0]))
    with pytest.raises(ValueError):
        SafetyEnvelope(low=np.array([5.0]), high=np.array([1.0]))


# ---------------------------------------------------------------------------
# ShadowRunner
# ---------------------------------------------------------------------------

def test_shadow_returns_baseline_and_logs_both():
    runner = ShadowRunner(
        baseline_fn=lambda x: np.array([x]),
        shadow_fn=lambda x: np.array([2 * x]),
        divergence="l1",
    )
    acted, rec = runner.tick(3.0, context={"tick": 0.0})
    # The actuated action is always the baseline.
    assert acted[0] == 3.0
    # But the shadow is recorded alongside.
    assert rec.shadow[0] == 6.0
    assert rec.divergence == 3.0


def test_shadow_summary_reports_quantiles():
    np.random.seed(0)
    base = lambda: np.array([0.0])
    shd  = lambda: np.array([float(np.random.randn())])
    runner = ShadowRunner(base, shd, divergence="l2")
    for _ in range(200):
        runner.tick()
    s = runner.summary()
    assert s["n"] == 200
    assert s["divergence_max"] >= s["divergence_p95"] >= s["divergence_mean"]


def test_shadow_divergence_shape_mismatch_raises():
    runner = ShadowRunner(
        baseline_fn=lambda: np.array([1.0]),
        shadow_fn=lambda: np.array([1.0, 2.0]),
    )
    with pytest.raises(RuntimeError):
        runner.tick()


# ---------------------------------------------------------------------------
# CounterfactualExplainer
# ---------------------------------------------------------------------------

def test_counterfactual_returns_one_result_per_signal():
    signals = [SignalSpec("a"), SignalSpec("b"), SignalSpec("c")]
    c = WeightedConvexCombiner(signals, query_dim=3)
    q = np.array([1.0, 0.0, 0.0])
    vals = [np.array([+1.0]), np.array([-1.0]), np.array([0.5])]
    action, _ = c.combine(q, vals)
    explainer = CounterfactualExplainer(c)
    results = explainer.explain(q, vals, factual_action=action)
    assert len(results) == 3
    for r in results:
        assert r.alternate_action.shape == action.shape
        assert r.delta_norm >= 0
        # Weight shift must still satisfy Σ ≈ 0 because both sides sum to 1.
        assert abs(r.weight_shift.sum()) < 1e-6


def test_counterfactual_mass_redistributes_to_surviving_signals():
    signals = [SignalSpec("a"), SignalSpec("b")]
    c = WeightedConvexCombiner(signals, query_dim=2)
    q = np.array([1.0, 0.0])
    vals = [np.array([1.0]), np.array([0.0])]
    action, _ = c.combine(q, vals)
    results = CounterfactualExplainer(c).explain(q, vals, factual_action=action)
    # Masking signal 0 should push (almost) all mass to signal 1.
    mask_a = results[0]
    assert mask_a.weight_shift[0] < 0              # signal 0 loses mass
    assert mask_a.weight_shift[1] > 0              # signal 1 gains mass
    assert abs(mask_a.weight_shift[0] + mask_a.weight_shift[1]) < 1e-6


def test_counterfactual_does_not_persist_state():
    """After explain() returns, the combiner's visible bias should be
    exactly what it was before."""
    signals = [SignalSpec("a", bias=0.3), SignalSpec("b")]
    c = WeightedConvexCombiner(signals, query_dim=2)
    q = np.array([1.0, 0.0])
    vals = [np.array([1.0]), np.array([0.0])]
    _ = c.combine(q, vals)
    before_bias = [s.bias for s in c.signals]
    explainer = CounterfactualExplainer(c)
    explainer.explain(q, vals, factual_action=np.array([0.0]))
    after_bias = [s.bias for s in c.signals]
    assert before_bias == after_bias


# ---------------------------------------------------------------------------
# WeightDriftDetector
# ---------------------------------------------------------------------------

def test_drift_detector_silent_when_distribution_is_stable():
    det = WeightDriftDetector(n_signals=3, kl_threshold=0.05)
    stable = np.array([0.5, 0.3, 0.2])
    for t in range(300):
        alert = det.observe(stable, step=t)
    assert len(det.alerts()) == 0


def test_drift_detector_fires_on_abrupt_shift():
    det = WeightDriftDetector(n_signals=3,
                              fast_alpha=0.3, slow_alpha=0.03,
                              kl_threshold=0.1)
    initial = np.array([0.5, 0.3, 0.2])
    for t in range(200):
        det.observe(initial, step=t)
    # Abrupt distributional shift.
    shifted = np.array([0.05, 0.05, 0.9])
    alerted_steps = []
    for t in range(200, 260):
        alert = det.observe(shifted, step=t)
        if alert is not None:
            alerted_steps.append(t)
    assert len(alerted_steps) > 0
    # First alert must happen soon after the shift, not ~200 ticks later.
    assert alerted_steps[0] - 200 < 30


def test_drift_detector_shape_and_param_errors():
    with pytest.raises(ValueError):
        WeightDriftDetector(n_signals=2, fast_alpha=0.0)
    with pytest.raises(ValueError):
        WeightDriftDetector(n_signals=2, fast_alpha=0.1, slow_alpha=0.5)
    with pytest.raises(ValueError):
        WeightDriftDetector(n_signals=2, kl_threshold=0.0)
    det = WeightDriftDetector(n_signals=2)
    with pytest.raises(ValueError):
        det.observe(np.array([0.5, 0.3, 0.2]), step=0)
