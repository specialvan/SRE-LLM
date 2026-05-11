"""Tests for the self-learning safety envelope.

These tests are deliberately heavy on *invariant* checking: the whole
purpose of the module is that it can't accidentally loosen itself, can't
escape hard bounds, and can't self-lockdown to zero.
"""

from __future__ import annotations

import numpy as np
import pytest

from attention_residuals.sre_self_envelope import (
    ActionOutcome,
    ContractionAwareEnvelope,
    CreditAwareLabeler,
    EnvelopeLearner,
    LearnedSafetyEnvelope,
    OutcomeEvidence,
    OutcomeLabel,
)
from attention_residuals.sre_math import TemporalCreditAssigner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_env(**kwargs) -> LearnedSafetyEnvelope:
    defaults = dict(
        action_dim=1,
        hard_low=np.array([-10.0]),
        hard_high=np.array([+10.0]),
        hard_max_delta=np.array([5.0]),
        min_max_delta=np.array([0.5]),
        safe_quantile=0.95,
        hysteresis=0.1,
        unsafe_quorum=3,
        min_safe_samples=20,
        buffer_size=200,
    )
    defaults.update(kwargs)
    return LearnedSafetyEnvelope(**defaults)


# ---------------------------------------------------------------------------
# Construction & invariant checks
# ---------------------------------------------------------------------------

def test_construction_with_defaults_matches_hard_bounds():
    env = _fresh_env()
    b = env.current_bounds()
    assert np.allclose(b["low"], [-10.0])
    assert np.allclose(b["high"], [+10.0])
    assert np.allclose(b["max_delta"], [5.0])


def test_construction_rejects_inverted_hard_bounds():
    with pytest.raises(ValueError):
        _fresh_env(hard_low=np.array([5.0]), hard_high=np.array([-5.0]))


def test_construction_rejects_nonpositive_hard_max_delta():
    with pytest.raises(ValueError):
        _fresh_env(hard_max_delta=np.array([0.0]))


def test_construction_rejects_bad_quantile():
    with pytest.raises(ValueError):
        _fresh_env(safe_quantile=0.3)
    with pytest.raises(ValueError):
        _fresh_env(safe_quantile=1.0)


def test_construction_rejects_bad_min_max_delta():
    with pytest.raises(ValueError):
        _fresh_env(min_max_delta=np.array([0.0]))
    with pytest.raises(ValueError):
        _fresh_env(min_max_delta=np.array([10.0]))  # > hard_max_delta


def test_construction_rejects_buffer_smaller_than_min_samples():
    with pytest.raises(ValueError):
        _fresh_env(buffer_size=5, min_safe_samples=20)


def test_construction_rejects_bad_unsafe_quorum():
    with pytest.raises(ValueError):
        _fresh_env(unsafe_quorum=0)


# ---------------------------------------------------------------------------
# Core invariants: never escape hard bounds
# ---------------------------------------------------------------------------

def test_learned_bounds_never_exceed_hard_bounds_after_fit():
    env = _fresh_env()
    # Inject 100 SAFE actions clustered tightly near +8.0.
    rng = np.random.default_rng(0)
    for _ in range(100):
        a = 8.0 + 0.1 * rng.standard_normal(1)
        env.observe(a, OutcomeLabel.SAFE)
    for _ in range(5):                        # quorum=3 by default above
        env.observe(np.array([9.5]), OutcomeLabel.UNSAFE)
    env.fit()
    b = env.current_bounds()
    assert b["low"][0] >= -10.0 - 1e-9
    assert b["high"][0] <= +10.0 + 1e-9
    assert b["max_delta"][0] <= 5.0 + 1e-9
    assert b["max_delta"][0] >= 0.5 - 1e-9


def test_fit_cannot_loosen_bounds_even_with_very_wide_safe_samples():
    """If the envelope has already narrowed to [-1, +1], presenting SAFE
    actions at ±9 should NOT widen it back out — that's the ratchet."""
    env = _fresh_env(
        initial_low=np.array([-1.0]),
        initial_high=np.array([+1.0]),
    )
    rng = np.random.default_rng(1)
    for _ in range(100):
        a = 9.0 * np.sign(rng.standard_normal(1))   # ±9, way outside
        env.observe(a, OutcomeLabel.SAFE)
    for _ in range(5):
        env.observe(np.array([9.5]), OutcomeLabel.UNSAFE)
    env.fit()
    b = env.current_bounds()
    # Bounds must not have grown past the [-1, +1] ratchet state.
    assert b["low"][0] >= -1.0 - 1e-9
    assert b["high"][0] <= +1.0 + 1e-9


def test_fit_does_nothing_without_unsafe_quorum():
    env = _fresh_env(unsafe_quorum=10)
    rng = np.random.default_rng(2)
    for _ in range(100):
        env.observe(0.1 * rng.standard_normal(1), OutcomeLabel.SAFE)
    # No UNSAFE events at all.
    summary = env.fit()
    assert summary["reason"] == "no_unsafe_quorum"
    assert not summary["tightened_high"]
    assert not summary["tightened_low"]
    # Bounds untouched.
    b = env.current_bounds()
    assert b["low"][0] == -10.0 and b["high"][0] == +10.0


def test_fit_does_nothing_below_min_safe_samples():
    env = _fresh_env(min_safe_samples=50)
    env.observe(np.array([0.0]), OutcomeLabel.SAFE)
    for _ in range(5):
        env.observe(np.array([9.5]), OutcomeLabel.UNSAFE)
    s = env.fit()
    assert s["reason"] == "insufficient_safe_samples"


def test_fit_tightens_after_quorum_and_enough_samples():
    env = _fresh_env(
        unsafe_quorum=3,
        min_safe_samples=30,
        hysteresis=0.1,
    )
    rng = np.random.default_rng(3)
    # SAFE cluster around [+1, +2]; so fitted high should come down well below 10.
    for _ in range(50):
        a = 1.5 + 0.2 * rng.standard_normal(1)
        env.observe(a, OutcomeLabel.SAFE)
    for _ in range(3):
        env.observe(np.array([9.0]), OutcomeLabel.UNSAFE)
    s = env.fit()
    b = env.current_bounds()
    assert s["tightened_high"] and s["tightened_low"]
    # 95th quantile of SAFE + 10% padding should be in the low single digits.
    assert b["high"][0] < 3.0
    assert b["low"][0] > 0.0


def test_max_delta_is_learned_from_safe_deltas_and_floored():
    env = _fresh_env(
        unsafe_quorum=3,
        min_safe_samples=30,
        min_max_delta=np.array([1.0]),        # floor deliberately non-trivial
    )
    rng = np.random.default_rng(4)
    prev = 0.0
    for _ in range(80):
        step = float(0.3 * rng.standard_normal())      # very small deltas
        cur = prev + step
        env.observe(np.array([cur]), OutcomeLabel.SAFE,
                    delta=np.array([step]))
        prev = cur
    for _ in range(3):
        env.observe(np.array([0.0]), OutcomeLabel.UNSAFE)
    env.fit()
    b = env.current_bounds()
    # Observed |delta| quantile is small, but min_max_delta floor clamps to 1.
    assert b["max_delta"][0] == pytest.approx(1.0)


def test_multiple_fits_never_widen_bounds():
    """Sanity: even under many fits with varying samples, bounds never grow."""
    env = _fresh_env(unsafe_quorum=2, min_safe_samples=10)
    rng = np.random.default_rng(5)
    prev_b = env.current_bounds()
    for round_i in range(5):
        for _ in range(30):
            env.observe(0.5 + 0.1 * rng.standard_normal(1), OutcomeLabel.SAFE)
        for _ in range(2):
            env.observe(np.array([0.9]), OutcomeLabel.UNSAFE)
        env.fit()
        b = env.current_bounds()
        assert b["low"][0] >= prev_b["low"][0] - 1e-9
        assert b["high"][0] <= prev_b["high"][0] + 1e-9
        assert b["max_delta"][0] <= prev_b["max_delta"][0] + 1e-9
        prev_b = b


# ---------------------------------------------------------------------------
# Application / clipping behaviour
# ---------------------------------------------------------------------------

def test_apply_clips_to_current_bounds():
    env = _fresh_env(
        initial_low=np.array([-2.0]),
        initial_high=np.array([+2.0]),
    )
    clipped, info = env.apply(np.array([+5.0]))
    assert clipped[0] == 2.0
    assert info["clipped"] is True
    assert env.violation_count == 1


def test_apply_respects_rate_limit():
    env = _fresh_env(initial_max_delta=np.array([1.0]))
    # First call sets last_action.
    c1, _ = env.apply(np.array([0.0]))
    assert c1[0] == 0.0
    # Second call asks for +5, max_delta=1 → clamp to +1.
    c2, info = env.apply(np.array([+5.0]))
    assert c2[0] == 1.0
    assert info["rate_limited"]


def test_apply_returns_current_bounds_in_info():
    env = _fresh_env()
    _, info = env.apply(np.array([0.0]))
    assert "current_low" in info and "current_high" in info
    assert "current_max_delta" in info


# ---------------------------------------------------------------------------
# Relaxation (operator-invoked widening)
# ---------------------------------------------------------------------------

def test_relax_widens_but_stays_inside_hard_bounds():
    env = _fresh_env(
        initial_low=np.array([-1.0]),
        initial_high=np.array([+1.0]),
        initial_max_delta=np.array([1.0]),
    )
    env.relax(factor=100.0)                  # huge factor; hard bounds must cap
    b = env.current_bounds()
    assert b["low"][0] >= -10.0 - 1e-9
    assert b["high"][0] <= +10.0 + 1e-9
    assert b["max_delta"][0] <= 5.0 + 1e-9


def test_relax_to_hard_jumps_to_hard_bounds():
    env = _fresh_env(
        initial_low=np.array([-1.0]),
        initial_high=np.array([+1.0]),
    )
    env.relax(to_hard=True)
    b = env.current_bounds()
    assert np.isclose(b["low"][0], -10.0)
    assert np.isclose(b["high"][0], +10.0)


def test_relax_per_dim_only_affects_target_dim():
    env = LearnedSafetyEnvelope(
        action_dim=2,
        hard_low=np.array([-10.0, -10.0]),
        hard_high=np.array([+10.0, +10.0]),
        hard_max_delta=np.array([5.0, 5.0]),
        initial_low=np.array([-1.0, -1.0]),
        initial_high=np.array([+1.0, +1.0]),
        unsafe_quorum=3,
        min_safe_samples=20,
    )
    env.relax(to_hard=True, dim=0)
    b = env.current_bounds()
    assert b["low"][0] == -10.0 and b["high"][0] == 10.0
    # dim 1 untouched.
    assert b["low"][1] == -1.0 and b["high"][1] == +1.0


def test_relax_rejects_factor_below_one():
    env = _fresh_env()
    with pytest.raises(ValueError):
        env.relax(factor=0.5)


def test_relax_rejects_bad_dim():
    env = _fresh_env()
    with pytest.raises(ValueError):
        env.relax(dim=5)


# ---------------------------------------------------------------------------
# ContractionAwareEnvelope
# ---------------------------------------------------------------------------

def test_contraction_wrapper_no_shrink_when_gain_below_target():
    env = _fresh_env(initial_max_delta=np.array([2.0]))
    wrapper = ContractionAwareEnvelope(env, gain_provider=lambda: 0.5,
                                        target_gain=1.0)
    # Ask for a jump > max_delta to exercise the rate limit.
    wrapper.apply(np.array([0.0]))         # seed last_action
    c, info = wrapper.apply(np.array([+5.0]))
    assert info["contraction_scale"] == 1.0
    # Effective max_delta = 2.0 (unchanged).
    assert c[0] == 2.0


def test_contraction_wrapper_shrinks_when_gain_exceeds_target():
    env = _fresh_env(initial_max_delta=np.array([2.0]),
                      min_max_delta=np.array([0.1]))
    wrapper = ContractionAwareEnvelope(env, gain_provider=lambda: 4.0,
                                        target_gain=1.0, min_scale=0.1)
    wrapper.apply(np.array([0.0]))
    c, info = wrapper.apply(np.array([+5.0]))
    assert info["contraction_scale"] == pytest.approx(0.25, rel=1e-6)
    # Effective max_delta = 2.0 * 0.25 = 0.5.
    assert c[0] == pytest.approx(0.5)


def test_contraction_wrapper_honours_min_scale():
    env = _fresh_env(initial_max_delta=np.array([2.0]),
                      min_max_delta=np.array([0.01]))
    wrapper = ContractionAwareEnvelope(env, gain_provider=lambda: 1e9,
                                        target_gain=1.0, min_scale=0.2)
    wrapper.apply(np.array([0.0]))
    _, info = wrapper.apply(np.array([+5.0]))
    assert info["contraction_scale"] == pytest.approx(0.2)


def test_contraction_wrapper_does_not_mutate_inner_state():
    env = _fresh_env(initial_max_delta=np.array([2.0]))
    before = env.current_bounds()["max_delta"].copy()
    wrapper = ContractionAwareEnvelope(env, gain_provider=lambda: 3.0,
                                        target_gain=1.0)
    wrapper.apply(np.array([0.0]))
    wrapper.apply(np.array([+5.0]))
    after = env.current_bounds()["max_delta"].copy()
    assert np.allclose(before, after), "wrapper must not mutate inner max_delta"


def test_contraction_wrapper_no_gain_behaves_as_inner():
    env = _fresh_env(initial_max_delta=np.array([2.0]))
    wrapper = ContractionAwareEnvelope(env, gain_provider=lambda: None)
    wrapper.apply(np.array([0.0]))
    c, info = wrapper.apply(np.array([+5.0]))
    assert info["contraction_scale"] == 1.0
    assert c[0] == 2.0


def test_contraction_wrapper_bad_params():
    env = _fresh_env()
    with pytest.raises(ValueError):
        ContractionAwareEnvelope(env, gain_provider=lambda: 0, target_gain=0)
    with pytest.raises(ValueError):
        ContractionAwareEnvelope(env, gain_provider=lambda: 0, min_scale=1.5)


# ---------------------------------------------------------------------------
# EnvelopeLearner orchestration
# ---------------------------------------------------------------------------

def test_envelope_learner_routes_labels_correctly():
    env = _fresh_env(unsafe_quorum=3, min_safe_samples=20)
    calls: list[str] = []

    def labeler(ctx: dict) -> OutcomeLabel:
        label = OutcomeLabel.SAFE if ctx.get("ok", True) else OutcomeLabel.UNSAFE
        calls.append(label.value)
        return label

    learner = EnvelopeLearner(env, labeler, fit_every=5)
    for i in range(25):
        ctx = {"ok": (i % 7 != 0)}
        learner.ingest(np.array([0.5]), ctx)
    assert learner.stats.ingested == 25
    assert learner.stats.safe > 0
    assert learner.stats.unsafe > 0
    assert learner.stats.fits == 5             # ceil(25/5) == 5


def test_envelope_learner_fit_every_validation():
    env = _fresh_env()
    with pytest.raises(ValueError):
        EnvelopeLearner(env, labeler=lambda c: OutcomeLabel.SAFE, fit_every=0)


def test_envelope_learner_unknown_records_do_not_feed_state():
    env = _fresh_env()
    learner = EnvelopeLearner(env, labeler=lambda c: OutcomeLabel.UNKNOWN, fit_every=100)
    for _ in range(50):
        learner.ingest(np.array([0.0]), {})
    assert learner.stats.unknown == 50
    assert learner.stats.safe == 0 and learner.stats.unsafe == 0
    # Envelope bounds must not have moved — no observation was recorded.
    assert env.current_bounds()["high"][0] == 10.0


# ---------------------------------------------------------------------------
# Soft labels and temporal-credit-aware labels
# ---------------------------------------------------------------------------

def test_soft_unsafe_evidence_accumulates_towards_quorum():
    env = _fresh_env(unsafe_quorum=2, min_safe_samples=5)
    for _ in range(10):
        env.observe(np.array([0.0]), OutcomeLabel.SAFE)

    env.observe(np.array([9.0]), OutcomeEvidence(0.0, confidence=0.75))
    env.observe(np.array([9.0]), OutcomeEvidence(0.0, confidence=0.75))
    s1 = env.fit()
    assert s1["reason"] == "no_unsafe_quorum"

    env.observe(np.array([9.0]), OutcomeEvidence(0.0, confidence=0.5))
    s2 = env.fit()
    assert "reason" not in s2
    assert s2["tightened_high"]


def test_low_confidence_safe_outlier_has_little_quantile_power():
    env = _fresh_env(unsafe_quorum=1, min_safe_samples=10,
                     safe_quantile=0.9, hysteresis=0.0)
    for _ in range(12):
        env.observe(np.array([1.0]), OutcomeLabel.SAFE)
    # A single "safe" outlier with tiny confidence should not drag the
    # weighted quantile close to 9.
    env.observe(np.array([9.0]), OutcomeEvidence(1.0, confidence=0.01))
    env.observe(np.array([9.0]), OutcomeLabel.UNSAFE)
    env.fit()
    assert env.current_bounds()["high"][0] < 2.0


def test_envelope_learner_accepts_soft_labeler_and_tracks_evidence():
    env = _fresh_env(unsafe_quorum=10, min_safe_samples=5)
    learner = EnvelopeLearner(
        env,
        labeler=lambda ctx: OutcomeEvidence(ctx["safety"], confidence=0.5),
        fit_every=100,
    )
    e = learner.ingest(np.array([0.0]), {"safety": 0.2})
    assert e.unsafe_weight == pytest.approx(0.4)
    assert learner.stats.soft == 1
    assert learner.stats.safe_evidence == pytest.approx(0.1)
    assert learner.stats.unsafe_evidence == pytest.approx(0.4)


def test_outcome_evidence_from_weights_normalises_large_evidence():
    evidence = OutcomeEvidence.from_weights(2.0, 1.0)
    assert evidence.confidence == pytest.approx(1.0)
    assert evidence.safety_score == pytest.approx(2.0 / 3.0)


def test_credit_aware_labeler_downgrades_exogenous_unsafe():
    tca = TemporalCreditAssigner(decay=1.0)
    tca.record(
        10,
        weights=np.array([0.1, 0.9]),
        losses=np.array([1.0, 1.0]),
        signal_names=["controller", "traffic"],
    )
    labeler = CreditAwareLabeler(
        base_labeler=lambda ctx: OutcomeLabel.UNSAFE,
        credit_assigner=tca,
        controllable_signals=["controller"],
        window=5,
    )
    evidence = labeler({"tick": 10})
    assert evidence.unsafe_weight == pytest.approx(0.1)
    assert labeler.last_adjustment()["controllable_ratio"] == pytest.approx(0.1)


def test_credit_aware_labeler_preserves_action_caused_unsafe():
    tca = TemporalCreditAssigner(decay=1.0)
    tca.record(
        3,
        weights=np.array([0.8, 0.2]),
        losses=np.array([1.0, 1.0]),
        signal_names=["controller", "traffic"],
    )
    labeler = CreditAwareLabeler(
        base_labeler=lambda ctx: OutcomeLabel.UNSAFE,
        credit_assigner=tca,
        controllable_signals=["controller"],
        window=10,
    )
    evidence = labeler({"tick": 3})
    assert evidence.unsafe_weight == pytest.approx(0.8)


def test_credit_aware_labeler_without_credit_leaves_label_unchanged():
    labeler = CreditAwareLabeler(
        base_labeler=lambda ctx: OutcomeLabel.UNSAFE,
        credit_assigner=TemporalCreditAssigner(),
        controllable_signals=["controller"],
    )
    evidence = labeler({"tick": 99})
    assert evidence.unsafe_weight == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# ActionOutcome dataclass smoke
# ---------------------------------------------------------------------------

def test_action_outcome_serialisable():
    a = ActionOutcome(
        step=7, action=np.array([0.1, -0.2]),
        outcome=OutcomeLabel.SAFE,
        delta=np.array([0.05, -0.05]),
        context={"qps": 123.0},
    )
    d = a.as_dict()
    assert d["step"] == 7
    assert d["action"] == [0.1, -0.2]
    assert d["outcome"] == "safe"
    assert d["context"]["qps"] == 123.0
