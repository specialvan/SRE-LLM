"""Self-learning SafetyEnvelope — audit trail feeds back into the envelope.

This demo focuses on *invariants*, not aggregate counts. What we want to
see explicitly:

  I. The envelope starts wide (operator hard bounds) and **never
     exceeds them** throughout the run.

  II. Before any UNSAFE evidence accumulates, the envelope stays at
      hard bounds (no premature self-constraint).

  III. After UNSAFE evidence crosses the quorum, the envelope
       **ratchets tighter** — and from that tick forward, actions that
       would have been UNSAFE are clipped before being applied.

  IV. The ratchet is **monotone**: once tightened, subsequent fit()
      calls never widen, even if new SAFE observations happen to sit
      outside the current interval (selection bias).

  V. :meth:`relax` is the only way to widen — and even it respects
     the operator-set hard bounds.

  VI. A :class:`ContractionAwareEnvelope` overlay additionally shrinks
      ``max_delta`` when the plant's empirical gain exceeds 1 — a
      second, model-free safety layer derived from §20 equation ⑤.

The plant model is intentionally simple so the invariants are the
thing the reader sees, not plant tuning artefacts.

Run with::

    python -m examples.demo_self_learning_envelope
"""

from __future__ import annotations

from typing import Dict, List

import numpy as np

from attention_residuals.sre_math import JacobianContractionMonitor
from attention_residuals.sre_self_envelope import (
    ContractionAwareEnvelope,
    EnvelopeLearner,
    LearnedSafetyEnvelope,
    OutcomeLabel,
)


# ---------------------------------------------------------------------------
# Fixed configuration
# ---------------------------------------------------------------------------

HARD_LOW = np.array([-5.0])
HARD_HIGH = np.array([+5.0])
HARD_MAX_DELTA = np.array([3.0])
SLO_QUEUE = 250.0
NUM_TICKS = 400
REGIME_SHIFT = 150


# ---------------------------------------------------------------------------
# Plant: very simple to keep the focus on the envelope behaviour.
# ---------------------------------------------------------------------------

def plant_step(queue: float, u: float, regime: int, tick: int, rng) -> float:
    """Plant with periodic bursts that force the controller into aggressive u.

    * Baseline arrivals ≈ 12 per tick.
    * Every 25 ticks a *burst* adds 80 units over one tick, pushing queue
      high enough for the controller's aggressive ``u=+4`` branch.
    * Regime 0 (stable): aggressive u drains the burst cleanly.
    * Regime 1 (post-shift): aggressive u triggers a quadratic downstream
      penalty ``40·max(0, |u|−2)²`` that compounds the problem.
    """
    burst = 80.0 if (tick > 10 and tick % 25 == 0) else 0.0
    arrivals = 12.0 + burst + rng.normal(0, 1.0)
    if regime == 0:
        capacity = 2.0 * (5.0 + u)
        penalty = 0.0
    else:
        capacity = 1.8 * (5.0 + u)
        penalty = 40.0 * max(0.0, abs(u) - 2.0) ** 2
    return max(0.0, queue + arrivals - max(0.5, capacity) + penalty)


def propose(queue: float) -> float:
    """Naive threshold-ladder controller, ignorant of regime changes."""
    if queue > 200:
        return +4.0
    if queue > 120:
        return +2.5
    if queue > 60:
        return +1.5
    if queue < 10:
        return -1.5
    return 0.5


def outcome_label(next_queue: float) -> OutcomeLabel:
    return OutcomeLabel.SAFE if next_queue < SLO_QUEUE else OutcomeLabel.UNSAFE


# ---------------------------------------------------------------------------
# Envelope factory
# ---------------------------------------------------------------------------

def make_learned() -> LearnedSafetyEnvelope:
    return LearnedSafetyEnvelope(
        action_dim=1,
        hard_low=HARD_LOW.copy(),
        hard_high=HARD_HIGH.copy(),
        hard_max_delta=HARD_MAX_DELTA.copy(),
        min_max_delta=np.array([0.3]),
        safe_quantile=0.9,
        hysteresis=0.1,
        unsafe_quorum=3,
        min_safe_samples=20,
        buffer_size=400,
    )


# ---------------------------------------------------------------------------
# Main simulation
# ---------------------------------------------------------------------------

def main() -> None:
    env = make_learned()
    contraction = JacobianContractionMonitor(window=48, min_samples=12, threshold=1.0)
    wrapper = ContractionAwareEnvelope(
        env, gain_provider=contraction.gain,
        target_gain=1.0, min_scale=0.3,
    )

    def label_fn(ctx: Dict[str, float]) -> OutcomeLabel:
        if "next_queue" not in ctx:
            return OutcomeLabel.UNKNOWN
        return outcome_label(ctx["next_queue"])

    learner = EnvelopeLearner(wrapper, labeler=label_fn, fit_every=10)

    rng = np.random.default_rng(7)
    queue = 40.0
    last_action = 0.0
    first_tighten: int | None = None

    trace: List[dict] = []
    for t in range(NUM_TICKS):
        regime = 0 if t < REGIME_SHIFT else 1
        u_prop = propose(queue)
        clipped, info = wrapper.apply(np.array([u_prop]))
        u = clipped[0]
        delta = np.array([u - last_action])

        next_queue = plant_step(queue, u, regime, t, rng)
        contraction.observe(u, next_queue - queue, step=t)

        fits_before = learner.stats.fits
        ctx = {"tick": float(t), "queue": float(queue),
               "next_queue": float(next_queue), "regime": float(regime)}
        learner.ingest(np.array([u]), ctx, delta=delta, step=t)
        fit_happened = learner.stats.fits > fits_before

        b = env.current_bounds()
        just_tightened = False
        if fit_happened:
            last_fit = env.fit_history()[-1]
            if (last_fit.get("tightened_high") or last_fit.get("tightened_low")
                    or last_fit.get("tightened_max_delta")):
                just_tightened = True
                if first_tighten is None:
                    first_tighten = t

        trace.append({
            "tick": t, "regime": regime,
            "u_prop": u_prop, "u_applied": u,
            "clipped": info["clipped"],
            "queue": queue, "next_queue": next_queue,
            "label": outcome_label(next_queue).value,
            "bounds_low": float(b["low"][0]),
            "bounds_high": float(b["high"][0]),
            "bounds_max_delta": float(b["max_delta"][0]),
            "tightened": just_tightened,
        })

        queue = next_queue
        last_action = u

    # -----------------------------------------------------------------------
    # Report
    # -----------------------------------------------------------------------
    print("=" * 78)
    print("Invariant I — bounds never exceed hard bounds")
    print("=" * 78)
    max_low_violation = min(r["bounds_low"] - HARD_LOW[0] for r in trace)     # ≥ 0 OK
    max_high_violation = max(r["bounds_high"] - HARD_HIGH[0] for r in trace)  # ≤ 0 OK
    max_md_violation = max(r["bounds_max_delta"] - HARD_MAX_DELTA[0] for r in trace)
    print(f"  low  always ≥ {HARD_LOW[0]}    : min margin = {max_low_violation:+.4f}  (need ≥ 0)")
    print(f"  high always ≤ {HARD_HIGH[0]}    : max excess = {max_high_violation:+.4f}  (need ≤ 0)")
    print(f"  max_δ always ≤ {HARD_MAX_DELTA[0]}: max excess = {max_md_violation:+.4f}  (need ≤ 0)")

    print()
    print("=" * 78)
    print("Invariant II — no premature tightening (no UNSAFE → no ratchet)")
    print("=" * 78)
    pre_regime_tighten = [r["tick"] for r in trace[:REGIME_SHIFT] if r["tightened"]]
    print(f"  Tightening events before regime shift (t < {REGIME_SHIFT}): {pre_regime_tighten}")
    print(f"  Expected: []  (no UNSAFE events should have accumulated yet)")

    print()
    print("=" * 78)
    print("Invariant III — ratchet fires after regime shift")
    print("=" * 78)
    print(f"  First tighten event   : tick {first_tighten}")
    # Bounds just after first tighten vs just before
    if first_tighten is not None:
        before = trace[first_tighten - 1]
        after = trace[first_tighten]
        print(f"  Bounds before tighten : [{before['bounds_low']:+.2f}, {before['bounds_high']:+.2f}]  Δ≤{before['bounds_max_delta']:.2f}")
        print(f"  Bounds after tighten  : [{after['bounds_low']:+.2f}, {after['bounds_high']:+.2f}]  Δ≤{after['bounds_max_delta']:.2f}")

    print()
    print("=" * 78)
    print("Invariant IV — monotone ratchet (never widens on its own)")
    print("=" * 78)
    prev = trace[0]
    widenings = []
    for r in trace[1:]:
        if (r["bounds_low"] < prev["bounds_low"] - 1e-9
                or r["bounds_high"] > prev["bounds_high"] + 1e-9
                or r["bounds_max_delta"] > prev["bounds_max_delta"] + 1e-9):
            widenings.append(r["tick"])
        prev = r
    print(f"  Automatic widening events: {widenings}")
    print(f"  Expected: []  (envelope can only tighten on its own)")

    print()
    print("=" * 78)
    print("Invariant V — relax() is the only path to widen")
    print("=" * 78)
    before_relax = env.current_bounds()
    env.relax(factor=1.5)
    after_relax = env.current_bounds()
    env.relax(to_hard=True)
    after_hard = env.current_bounds()
    print(f"  Before relax  : [{before_relax['low'][0]:+.2f}, {before_relax['high'][0]:+.2f}]  Δ≤{before_relax['max_delta'][0]:.2f}")
    print(f"  relax(1.5)    : [{after_relax['low'][0]:+.2f}, {after_relax['high'][0]:+.2f}]  Δ≤{after_relax['max_delta'][0]:.2f}")
    print(f"  relax(to_hard): [{after_hard['low'][0]:+.2f}, {after_hard['high'][0]:+.2f}]  Δ≤{after_hard['max_delta'][0]:.2f}   (= hard bounds)")

    print()
    print("=" * 78)
    print("Invariant VI — contraction scaling on-the-fly (never mutates inner state)")
    print("=" * 78)
    # Force one tick with a manually high gain via a lambda-swap for illustration.
    inner_md_before = env.current_max_delta.copy()
    test_wrapper = ContractionAwareEnvelope(
        env, gain_provider=lambda: 4.0,      # pretend gain = 4
        target_gain=1.0, min_scale=0.3,
    )
    _, info = test_wrapper.apply(np.array([+5.0]))
    inner_md_after = env.current_max_delta.copy()
    print(f"  inner max_δ before: {inner_md_before[0]:.3f}")
    print(f"  contraction scale : {info['contraction_scale']:.3f}")
    print(f"  effective max_δ   : {inner_md_before[0] * info['contraction_scale']:.3f}")
    print(f"  inner max_δ after : {inner_md_after[0]:.3f}   (must equal 'before')")

    # Summary table
    print()
    print("=" * 78)
    print("Summary of notable ticks")
    print("=" * 78)
    print(f"{'tick':>4} {'reg':>3} {'u_prop':>7} {'u_app':>7} "
          f"{'clip':>5} {'queue→next':>12} {'label':>7} "
          f"{'low..high':>18} {'max_δ':>6}")
    notable = (
        list(range(0, REGIME_SHIFT, 50))
        + list(range(REGIME_SHIFT, REGIME_SHIFT + 30, 5))
        + list(range(REGIME_SHIFT + 30, NUM_TICKS, 50))
    )
    for t in notable:
        r = trace[t]
        lbl = "safe" if r["label"] == "safe" else "UNSAFE"
        print(
            f"{t:>4} {r['regime']:>3} {r['u_prop']:>+7.2f} {r['u_applied']:>+7.2f} "
            f"{'Y' if r['clipped'] else ' ':>5} "
            f"{r['queue']:>4.0f}→{r['next_queue']:>4.0f}  {lbl:>7} "
            f"[{r['bounds_low']:+.2f}, {r['bounds_high']:+.2f}]   {r['bounds_max_delta']:>6.2f}"
        )


if __name__ == "__main__":
    main()
