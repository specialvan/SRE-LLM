"""Closed-loop adaptive SRE controller with the full industrial safety stack.

Scenario
--------
We run a single-region autoscaler through a long simulation in which the
"true" best signal changes partway through:

    * Ticks 0..39    — the P99 signal is the best predictor of load.
    * Ticks 40..79   — queue_depth becomes the best predictor.
    * Ticks 80..119  — error_budget becomes the best predictor.

An open-loop controller will be stuck with whatever static priorities the
operator wrote down. An Attention-Residual-style adaptive controller
should:

  1. Start without prior knowledge (uniform Hedge weights).
  2. Converge toward the currently-best signal within O(√T log n) ticks.
  3. Re-adapt when the environment changes.
  4. Never violate the safety envelope on the actuated action.
  5. Leave an audit trail + drift alerts + counterfactual explanations.

This demo instantiates all three layers — control / adaptive / safety —
and prints a condensed trace so the reader can see each one doing its job.

Run with::

    python -m examples.demo_sre_adaptive_safety
"""

from __future__ import annotations

from typing import List

import numpy as np

from attention_residuals.sre_adaptive import (
    AdaptiveCombiner,
    HedgeRegretLearner,
)
from attention_residuals.sre_control import MustAttendRegistry, SignalSpec
from attention_residuals.sre_safety import (
    CounterfactualExplainer,
    SafetyEnvelope,
    ShadowRunner,
    WeightDriftDetector,
)


# ---------------------------------------------------------------------------
# 1. Registry with one must-attend signal (error_budget ≥ 0.2).
# ---------------------------------------------------------------------------
reg = MustAttendRegistry()
reg.register("error_budget", 0.20)


# ---------------------------------------------------------------------------
# 2. Open-loop baseline: a fixed combiner with no learning.
# ---------------------------------------------------------------------------
from attention_residuals.sre_control import WeightedConvexCombiner

def make_signals() -> List[SignalSpec]:
    return [
        SignalSpec("p99"),
        SignalSpec("queue_depth"),
        reg.spec("error_budget"),
    ]

baseline = WeightedConvexCombiner(make_signals(), query_dim=3, rng_seed=0)


# ---------------------------------------------------------------------------
# 3. Adaptive combiner: Hedge learner on top of the same 3 signals.
# ---------------------------------------------------------------------------
learner = HedgeRegretLearner(n_signals=3, eta=0.5)
adaptive = AdaptiveCombiner(make_signals(), query_dim=3, learner=learner)


# ---------------------------------------------------------------------------
# 4. Industrial safety stack.
# ---------------------------------------------------------------------------
envelope = SafetyEnvelope(
    low=np.array([-2.0]),             # replica_delta ∈ [-2, +3] per tick
    high=np.array([+3.0]),
    max_delta=np.array([2.0]),        # rate-limit: change at most 2 per tick
)
drift = WeightDriftDetector(n_signals=3, fast_alpha=0.3, slow_alpha=0.03,
                             kl_threshold=0.2)
explainer = CounterfactualExplainer(adaptive.combiner)


def baseline_fn(query, values):
    action, _ = baseline.combine(query, values)
    return action


def shadow_fn(query, values):
    action, _ = adaptive.step(query, values, observed_losses=None)
    return action


shadow = ShadowRunner(baseline_fn, shadow_fn, divergence="l2")


# ---------------------------------------------------------------------------
# 5. Simulation.
# ---------------------------------------------------------------------------

def regime(tick: int) -> int:
    """Which signal is the ground-truth "best predictor" right now."""
    if tick < 40:
        return 0     # p99
    if tick < 80:
        return 1     # queue_depth
    return 2         # error_budget


def synth(tick: int) -> tuple[np.ndarray, list[np.ndarray], np.ndarray]:
    """Generate (query, values, per-signal losses).

    Losses are 0 on the best signal and increase as we move away from it.
    """
    rng = np.random.default_rng(42 + tick)
    r = regime(tick)
    noise = 0.05 * rng.standard_normal(3)
    # Each signal's proposed replica delta — all roughly sensible but with
    # the right-for-the-moment signal being the most accurate.
    vals = [
        np.array([float(np.sin(tick / 10) + 1.0 + noise[0])]),
        np.array([float(np.cos(tick / 7) + 1.0 + noise[1])]),
        np.array([float(1.5 - 0.01 * tick + noise[2])]),
    ]
    q = np.array([vals[0].item(), vals[1].item(), vals[2].item()])
    # Losses: best = 0.05, worst ≈ 0.8.
    losses = np.full(3, 0.8)
    losses[r] = 0.05 + float(abs(noise[r]))
    return q, vals, losses


# First step: no losses yet. AdaptiveCombiner expects observed_losses=None.
prev_losses = None

print(f"{'tick':>4} {'regime':>7} {'learner (p99,q,b)':<22} "
      f"{'comb. weights':<22} {'baseline Δ':>12} {'adaptive Δ':>12} "
      f"{'safe Δ':>10} {'violations':>12}")

recorded_divergences = []
for tick in range(120):
    q, vals, losses = synth(tick)

    # Closed-loop adaptive step — feeds previous-tick losses into the learner.
    adaptive_action, comb_weights = adaptive.step(q, vals, observed_losses=prev_losses)
    baseline_action, _ = baseline.combine(q, vals)

    # Safety envelope is applied to the adaptive action.
    safe_action, env_info = envelope.apply(adaptive_action)

    # Shadow runner logs the pair for comparison — note: we already advanced
    # the adaptive learner above, so we call the shadow with a dummy baseline
    # function that just returns the already-computed baseline_action.
    recorded_divergences.append(float(np.linalg.norm(baseline_action - adaptive_action)))

    # Drift detector sees the controller's actual output weights.
    drift_alert = drift.observe(comb_weights, step=tick)

    if tick % 10 == 0 or tick in (39, 40, 79, 80):
        print(
            f"{tick:>4} {regime(tick):>7} "
            f"[{learner.weights()[0]:.2f}, {learner.weights()[1]:.2f}, {learner.weights()[2]:.2f}]   "
            f"[{comb_weights[0]:.2f}, {comb_weights[1]:.2f}, {comb_weights[2]:.2f}]   "
            f"{baseline_action.item():>+12.2f} {adaptive_action.item():>+12.2f} "
            f"{safe_action.item():>+10.2f} {env_info['violation_count']:>12d}"
        )
        if drift_alert is not None:
            print(f"     ⚑ drift alert at tick {tick}: KL={drift_alert['kl']:.3f}")

    prev_losses = losses


# ---------------------------------------------------------------------------
# 6. Post-run diagnostics.
# ---------------------------------------------------------------------------
print()
print("=" * 72)
print("Post-run diagnostics")
print("=" * 72)

best = learner.best_signal_in_hindsight()
print(f"Best signal in hindsight (cumulative loss): index {best}")
print(f"Hedge regret bound after T=120: {learner.regret_bound():.2f}")
print(f"Envelope violation count      : {envelope.violation_count}")
print(f"Drift alerts                  : {len(drift.alerts())}")
print(f"Mean baseline-adaptive divergence : {np.mean(recorded_divergences):.3f}")
print(f"  p95 divergence              : {np.quantile(recorded_divergences, 0.95):.3f}")

# Counterfactual explanation on the final tick.
print()
print("Counterfactual on final tick (factual = adaptive_action):")
q_last, v_last, _ = synth(119)
factual_action, _ = adaptive.combiner.combine(q_last, v_last)
cfs = explainer.explain(q_last, v_last, factual_action)
for r in cfs:
    print(f"  mask {r.signal_name:>14}: alt_Δ = {r.alternate_action.item():+.3f}, "
          f"||delta||={r.delta_norm:.3f}, weight_shift="
          f"[{r.weight_shift[0]:+.2f}, {r.weight_shift[1]:+.2f}, {r.weight_shift[2]:+.2f}]")
