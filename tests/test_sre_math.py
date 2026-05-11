"""Tests for the deep-math SRE primitives."""

from __future__ import annotations

import numpy as np
import pytest

from attention_residuals.sre_control import SignalSpec
from attention_residuals.sre_math import (
    AuditCreditReplay,
    CreditEntry,
    FTRLLearner,
    JacobianContractionMonitor,
    MetricLossMapper,
    MetricLossSpec,
    MultiViewCombiner,
    ScaleInvariantNormalizer,
    TemperatureScheduler,
    TemporalCreditAssigner,
    ViewSpec,
    WassersteinDriftDetector,
)


# ---------------------------------------------------------------------------
# ScaleInvariantNormalizer
# ---------------------------------------------------------------------------

def test_scale_normalizer_passthrough_during_warmup():
    norm = ScaleInvariantNormalizer(n_signals=3, alpha=0.1, warmup=10)
    x = np.array([100.0, 0.001, 50.0])
    y = norm.observe_and_transform(x)
    assert np.allclose(y, x)
    assert not norm.ready


def test_scale_normalizer_zero_mean_unit_std_after_convergence():
    """Feed a large number of samples from a fixed (high-variance) distribution;
    steady-state z-scores should have ≈ 0 mean and ≈ 1 std."""
    rng = np.random.default_rng(0)
    true_mean = np.array([1000.0, 0.01, -50.0])
    true_std = np.array([200.0, 0.005, 10.0])
    norm = ScaleInvariantNormalizer(n_signals=3, alpha=0.02, warmup=20)
    zs = []
    for _ in range(3000):
        x = true_mean + true_std * rng.standard_normal(3)
        y = norm.observe_and_transform(x)
        if norm.ready:
            zs.append(y)
    Z = np.stack(zs[-1000:])
    # Use generous tolerance because EWMA introduces bias.
    assert np.abs(Z.mean(axis=0)).max() < 0.2
    assert np.abs(Z.std(axis=0) - 1.0).max() < 0.35


def test_scale_normalizer_constant_stream_does_not_divide_by_zero():
    norm = ScaleInvariantNormalizer(n_signals=2, warmup=2, eps=1e-3)
    for _ in range(50):
        norm.observe_and_transform(np.array([7.0, 7.0]))
    # std should not blow up to inf; transform must still be finite.
    y = norm.observe_and_transform(np.array([7.0, 7.0]))
    assert np.all(np.isfinite(y))


def test_scale_normalizer_param_errors():
    with pytest.raises(ValueError):
        ScaleInvariantNormalizer(n_signals=0)
    with pytest.raises(ValueError):
        ScaleInvariantNormalizer(n_signals=2, alpha=0.0)
    with pytest.raises(ValueError):
        ScaleInvariantNormalizer(n_signals=2, warmup=0)
    with pytest.raises(ValueError):
        ScaleInvariantNormalizer(n_signals=2, eps=0.0)
    norm = ScaleInvariantNormalizer(n_signals=3)
    with pytest.raises(ValueError):
        norm.observe(np.zeros(4))


# ---------------------------------------------------------------------------
# TemperatureScheduler
# ---------------------------------------------------------------------------

def test_temperature_scheduler_constant():
    sch = TemperatureScheduler(tau0=0.5, kind="constant")
    assert sch.tau(0) == 0.5
    assert sch.tau(1000) == 0.5


def test_temperature_scheduler_sqrt_decay():
    sch = TemperatureScheduler(tau0=1.0, tau_min=1e-3, kind="sqrt")
    assert sch.tau(0) == 1.0
    # τ_t = τ_0 / √(1+t); so τ(3) = 1/2, τ(99) = 0.1.
    assert np.isclose(sch.tau(3), 0.5)
    assert np.isclose(sch.tau(99), 0.1)


def test_temperature_scheduler_linear_reaches_min():
    sch = TemperatureScheduler(tau0=1.0, tau_min=0.01, kind="linear",
                               total_ticks=100)
    assert sch.tau(0) == 1.0
    assert sch.tau(50) == pytest.approx(0.505)
    assert sch.tau(100) == 0.01
    assert sch.tau(999) == 0.01  # clamped


def test_temperature_scheduler_exp_respects_half_life():
    sch = TemperatureScheduler(tau0=1.0, tau_min=1e-6, kind="exp",
                               half_life=10)
    assert sch.tau(0) == 1.0
    assert np.isclose(sch.tau(10), 0.5)
    assert np.isclose(sch.tau(20), 0.25)


def test_temperature_scheduler_bad_args():
    with pytest.raises(ValueError):
        TemperatureScheduler(tau0=-1.0)
    with pytest.raises(ValueError):
        TemperatureScheduler(tau0=0.1, tau_min=1.0)
    with pytest.raises(ValueError):
        TemperatureScheduler(kind="cosine")
    sch = TemperatureScheduler()
    with pytest.raises(ValueError):
        sch.tau(-1)


# ---------------------------------------------------------------------------
# MultiViewCombiner
# ---------------------------------------------------------------------------

def test_multiview_single_view_matches_plain_combiner():
    """With one view, MultiViewCombiner should produce the same action
    as if we'd used its single inner combiner directly."""
    signals = [SignalSpec("a"), SignalSpec("b")]
    mv = MultiViewCombiner(
        views=[ViewSpec("only", signals=signals, weight=1.0)],
        query_dim=2, temperature=1.0,
    )
    q = np.array([1.0, 0.0])
    vs = [np.array([3.0]), np.array([-1.0])]
    action, mw = mv.combine([q], [vs])
    assert action.shape == (1,)
    assert np.allclose(mw, np.array([1.0]))


def test_multiview_each_view_keeps_sum_to_one():
    signals_a = [SignalSpec("a1"), SignalSpec("a2")]
    signals_b = [SignalSpec("b1"), SignalSpec("b2"), SignalSpec("b3")]
    mv = MultiViewCombiner(
        views=[ViewSpec("latency", signals_a, weight=2.0),
               ViewSpec("cost", signals_b, weight=1.0)],
        query_dim=2,
    )
    mv.combine(
        query_per_view=[np.ones(2), np.ones(2)],
        values_per_view=[
            [np.array([0.5]), np.array([-0.5])],
            [np.array([1.0]), np.array([0.0]), np.array([-1.0])],
        ],
    )
    per_view = mv.last_view_weights()
    assert len(per_view) == 2
    for w in per_view:
        assert np.isclose(w.sum(), 1.0, atol=1e-6)


def test_multiview_merge_weights_are_normalised():
    mv = MultiViewCombiner(
        views=[ViewSpec("v1", [SignalSpec("s")], weight=3.0),
               ViewSpec("v2", [SignalSpec("s")], weight=1.0)],
        query_dim=1,
    )
    _, mw = mv.combine([np.array([1.0]), np.array([1.0])],
                       [[np.array([0.0])], [np.array([0.0])]])
    assert np.isclose(mw.sum(), 1.0)
    assert np.isclose(mw[0], 0.75)


def test_multiview_rejects_zero_or_negative_weights():
    with pytest.raises(ValueError):
        MultiViewCombiner(
            [ViewSpec("bad", [SignalSpec("x")], weight=0.0)], query_dim=1,
        )


def test_multiview_length_mismatch_raises():
    mv = MultiViewCombiner(
        [ViewSpec("v", [SignalSpec("x")], weight=1.0)], query_dim=1,
    )
    with pytest.raises(ValueError):
        mv.combine([np.array([1.0]), np.array([1.0])],
                   [[np.array([0.0])]])


# ---------------------------------------------------------------------------
# FTRLLearner
# ---------------------------------------------------------------------------

def test_ftrl_entropy_matches_hedge_exactly():
    """FTRL(entropy) update should equal log-weights of Hedge."""
    from attention_residuals.sre_adaptive import HedgeRegretLearner
    hedge = HedgeRegretLearner(n_signals=3, eta=0.2)
    ftrl = FTRLLearner(n_signals=3, eta=0.2, regularizer="entropy")
    losses = np.array([0.2, 0.8, 0.5])
    for _ in range(10):
        hedge.update(losses)
        ftrl.update(losses)
    assert np.allclose(hedge.weights(), ftrl.weights())


def test_ftrl_l2_stays_on_simplex():
    ftrl = FTRLLearner(n_signals=4, eta=0.1, regularizer="l2")
    for _ in range(50):
        ftrl.update(np.random.uniform(0, 1, size=4))
        w = ftrl.weights()
        assert np.isclose(w.sum(), 1.0, atol=1e-6)
        assert w.min() >= -1e-9


def test_ftrl_l2_concentrates_on_low_loss_signal():
    ftrl = FTRLLearner(n_signals=3, eta=0.5, regularizer="l2")
    for _ in range(100):
        ftrl.update(np.array([0.0, 1.0, 1.0]))
    w = ftrl.weights()
    assert w[0] > 0.95
    assert np.isclose(w.sum(), 1.0)


def test_ftrl_init_is_honoured():
    init = np.array([0.5, 0.3, 0.2])
    ftrl = FTRLLearner(n_signals=3, eta=0.3, regularizer="entropy", init=init)
    assert np.allclose(ftrl.weights(), init, atol=1e-6)


def test_ftrl_bad_args():
    with pytest.raises(ValueError):
        FTRLLearner(n_signals=2, eta=-1)
    with pytest.raises(ValueError):
        FTRLLearner(n_signals=2, regularizer="rkhs")
    with pytest.raises(ValueError):
        FTRLLearner(n_signals=2, init=np.array([0.0, 1.0]))    # zero entry
    L = FTRLLearner(n_signals=2)
    with pytest.raises(ValueError):
        L.update(np.zeros(3))


# ---------------------------------------------------------------------------
# JacobianContractionMonitor
# ---------------------------------------------------------------------------

def test_jacobian_monitor_stable_gain():
    mon = JacobianContractionMonitor(window=32, min_samples=8, threshold=1.0)
    # Δx = 0.5 · u + tiny noise → gain ≈ 0.5 (stable).
    rng = np.random.default_rng(42)
    for t in range(50):
        u = rng.standard_normal()
        dx = 0.5 * u + 0.02 * rng.standard_normal()
        mon.observe(u, dx, step=t)
    assert abs(mon.gain() - 0.5) < 0.1
    assert len(mon.alerts()) == 0


def test_jacobian_monitor_fires_on_amplifying_loop():
    mon = JacobianContractionMonitor(window=32, min_samples=8, threshold=1.0)
    rng = np.random.default_rng(0)
    for t in range(40):
        u = rng.standard_normal()
        dx = 1.5 * u + 0.05 * rng.standard_normal()   # gain > 1
        mon.observe(u, dx, step=t)
    assert len(mon.alerts()) > 0


def test_jacobian_monitor_needs_minimum_samples():
    mon = JacobianContractionMonitor(window=10, min_samples=5)
    for _ in range(3):
        mon.observe(1.0, 1.0)
    assert mon.gain() is None


def test_jacobian_monitor_zero_actions_returns_none_gain():
    mon = JacobianContractionMonitor(window=10, min_samples=3)
    for _ in range(5):
        mon.observe(0.0, 0.0)
    assert mon.gain() is None       # denominator uu = 0


def test_jacobian_monitor_bad_params():
    with pytest.raises(ValueError):
        JacobianContractionMonitor(window=1, min_samples=1)
    with pytest.raises(ValueError):
        JacobianContractionMonitor(window=10, min_samples=12)
    with pytest.raises(ValueError):
        JacobianContractionMonitor(threshold=0)


# ---------------------------------------------------------------------------
# TemporalCreditAssigner
# ---------------------------------------------------------------------------

def test_credit_assigner_top_blame_is_largest_weight_loss_product():
    tca = TemporalCreditAssigner(decay=1.0)  # no decay
    for t in range(5):
        # Signal 1 always dominates weights & loss.
        w = np.array([0.1, 0.7, 0.2])
        L = np.array([0.1, 0.9, 0.1])
        tca.record(t, w, L, signal_names=["a", "b", "c"])
    blamed = tca.attribute(incident_tick=4, window=10, top_k=3)
    assert blamed[0].signal_name == "b"
    # And score == 0.7 * 0.9 = 0.63 for the latest tick.
    assert np.isclose(blamed[0].score, 0.63)


def test_credit_assigner_decay_reduces_old_scores():
    tca = TemporalCreditAssigner(decay=0.5)
    for t in range(3):
        w = np.array([1.0])
        L = np.array([1.0])
        tca.record(t, w, L, signal_names=["only"])
    # incident at t=2 → age 0, 1, 2 → scores 1, 0.5, 0.25.
    entries = tca.attribute(incident_tick=2, window=10)
    scores = [e.score for e in entries]
    assert scores[0] == pytest.approx(1.0)
    assert scores[1] == pytest.approx(0.5)
    assert scores[2] == pytest.approx(0.25)


def test_credit_assigner_window_filters_old_records():
    tca = TemporalCreditAssigner(decay=0.9)
    tca.record(0, np.array([1.0]), np.array([1.0]), ["s"])
    tca.record(100, np.array([1.0]), np.array([1.0]), ["s"])
    entries = tca.attribute(incident_tick=100, window=10)
    assert len(entries) == 1
    assert entries[0].tick == 100


def test_credit_assigner_param_errors():
    with pytest.raises(ValueError):
        TemporalCreditAssigner(decay=0.0)
    tca = TemporalCreditAssigner()
    with pytest.raises(ValueError):
        tca.record(0, np.zeros(2), np.zeros(3))
    with pytest.raises(ValueError):
        tca.record(0, np.zeros(2), np.zeros(2), signal_names=["only"])


# ---------------------------------------------------------------------------
# AuditCreditReplay
# ---------------------------------------------------------------------------

def test_metric_loss_spec_modes_and_clipping():
    ctx = {"high": 12.0, "low": 2.0, "target": 7.0, "raw": 3.0}
    assert MetricLossSpec("high", target=10.0, mode="above").evaluate(ctx) == 2.0
    assert MetricLossSpec("low", target=5.0, mode="below").evaluate(ctx) == 3.0
    assert MetricLossSpec("target", target=5.0, mode="distance").evaluate(ctx) == 2.0
    assert MetricLossSpec("raw", mode="raw", scale=2.0).evaluate(ctx) == 1.5
    assert MetricLossSpec("high", target=10.0, ceiling=1.0).evaluate(ctx) == 1.0
    assert MetricLossSpec("missing", missing_loss=0.25).evaluate(ctx) == 0.25


def test_metric_loss_mapper_strict_and_default_paths():
    mapper = MetricLossMapper(
        {"a": MetricLossSpec("a_loss", mode="raw")},
        default_loss=0.1,
    )
    losses = mapper({"context": {"a_loss": 2.0}}, ["a", "b"])
    assert np.allclose(losses, [2.0, 0.1])
    strict = MetricLossMapper({"a": MetricLossSpec("a_loss")}, strict=True)
    with pytest.raises(KeyError):
        strict({"context": {"a_loss": 2.0}}, ["a", "b"])


def test_audit_credit_replay_jsonl_populates_credit_assigner():
    jsonl = "\n".join([
        '{"step": 1, "signals": ["latency", "traffic"], '
        '"weights": [0.2, 0.8], "action": [1.0], '
        '"context": {"latency_excess": 0.1, "traffic_spike": 3.0}}',
        '{"step": 2, "signals": ["latency", "traffic"], '
        '"weights": [0.7, 0.3], "action": [2.0], '
        '"context": {"latency_excess": 4.0, "traffic_spike": 0.1}}',
    ])
    tca = TemporalCreditAssigner(decay=1.0)
    replay = AuditCreditReplay(
        tca,
        MetricLossMapper({
            "latency": MetricLossSpec("latency_excess", mode="raw"),
            "traffic": MetricLossSpec("traffic_spike", mode="raw"),
        }),
    )
    assert replay.replay_jsonl(jsonl) == 2
    blamed = tca.attribute(incident_tick=2, window=5, top_k=1)
    assert blamed[0].signal_name == "latency"
    assert blamed[0].score == pytest.approx(2.8)


def test_audit_credit_replay_normalises_weights():
    tca = TemporalCreditAssigner(decay=1.0)
    replay = AuditCreditReplay(
        tca,
        MetricLossMapper({"a": MetricLossSpec("loss", mode="raw")}),
    )
    replay.replay_record({
        "step": 0,
        "signals": ["a"],
        "weights": [7.0],
        "context": {"loss": 2.0},
    })
    entry = tca.attribute(incident_tick=0)[0]
    assert entry.weight == pytest.approx(1.0)
    assert entry.score == pytest.approx(2.0)


def test_audit_credit_replay_rejects_bad_records():
    replay = AuditCreditReplay(
        TemporalCreditAssigner(),
        MetricLossMapper({"a": MetricLossSpec("loss", mode="raw")}),
    )
    with pytest.raises(ValueError):
        replay.replay_record({"step": 0, "signals": ["a"], "weights": [0.0],
                              "context": {"loss": 1.0}})
    with pytest.raises(ValueError):
        replay.replay_record({"step": 0, "signals": ["a", "b"], "weights": [1.0],
                              "context": {"loss": 1.0}})
    with pytest.raises(ValueError):
        replay.replay_jsonl("{bad-json}")


# ---------------------------------------------------------------------------
# WassersteinDriftDetector
# ---------------------------------------------------------------------------

def test_wasserstein_drift_silent_on_stable_stream():
    det = WassersteinDriftDetector(n_signals=3, threshold=0.05)
    stable = np.array([0.5, 0.3, 0.2])
    for t in range(500):
        det.observe(stable, step=t)
    assert len(det.alerts()) == 0


def test_wasserstein_drift_detects_regime_shift():
    det = WassersteinDriftDetector(n_signals=3, threshold=0.1,
                                    fast_alpha=0.3, slow_alpha=0.03)
    for t in range(200):
        det.observe(np.array([0.6, 0.3, 0.1]), step=t)
    fired = None
    for t in range(200, 260):
        a = det.observe(np.array([0.05, 0.1, 0.85]), step=t)
        if a is not None and fired is None:
            fired = t
    assert fired is not None and (fired - 200) < 30


def test_wasserstein_distance_matches_cdf_l1_on_two_point_example():
    """W1 of ([1,0,0], [0,0,1]) with default ordering = 2 (max on a 3-bin line)."""
    det = WassersteinDriftDetector(n_signals=3,
                                    fast_alpha=1.0, slow_alpha=1.0,
                                    threshold=0.01)
    p = np.array([1.0, 0.0, 0.0])
    q = np.array([0.0, 0.0, 1.0])
    # After one observation each side has its exact distribution.
    det.observe(p, step=0)
    det.slow = q.copy()     # override so we can assert the distance value
    det.fast = p.copy()
    assert np.isclose(det._w1(det.fast, det.slow), 2.0)


def test_wasserstein_ordering_permutes_axis():
    det = WassersteinDriftDetector(n_signals=3, ordering=[2, 0, 1])
    assert det.ordering.tolist() == [2, 0, 1]
    with pytest.raises(ValueError):
        WassersteinDriftDetector(n_signals=3, ordering=[2, 2, 1])


def test_wasserstein_bad_args():
    with pytest.raises(ValueError):
        WassersteinDriftDetector(n_signals=2, threshold=0.0)
    with pytest.raises(ValueError):
        WassersteinDriftDetector(n_signals=2, fast_alpha=0.0)
    with pytest.raises(ValueError):
        WassersteinDriftDetector(n_signals=2, fast_alpha=0.1, slow_alpha=0.5)
    det = WassersteinDriftDetector(n_signals=2)
    with pytest.raises(ValueError):
        det.observe(np.array([0.0, 0.0]), step=0)   # zero sum
