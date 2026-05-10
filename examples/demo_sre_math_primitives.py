"""End-to-end demo of the deep-math SRE primitives.

Scenario: an SRE controller managing one service across three views ——
latency / reliability / cost —— each with its own signals on wildly
different native scales. Every new primitive from :mod:`sre_math`
participates in one visible role:

    ScaleInvariantNormalizer     normalises raw signals to comparable scale
    TemperatureScheduler         anneals τ from exploration → exploitation
    ViewSpec / MultiViewCombiner decomposes the decision into 3 heads
    FTRLLearner(regularizer=...) picks entropy vs l2 geometry
    JacobianContractionMonitor   detects positive-feedback amplification
    TemporalCreditAssigner       attributes blame after an incident
    WassersteinDriftDetector     flags priority shifts with bounded distance

Run with::

    python -m examples.demo_sre_math_primitives
"""

from __future__ import annotations

import numpy as np

from attention_residuals.sre_control import SignalSpec
from attention_residuals.sre_math import (
    FTRLLearner,
    JacobianContractionMonitor,
    MultiViewCombiner,
    ScaleInvariantNormalizer,
    TemperatureScheduler,
    TemporalCreditAssigner,
    ViewSpec,
    WassersteinDriftDetector,
)


# ---------------------------------------------------------------------------
# 1. Views & signals
# ---------------------------------------------------------------------------
latency_view = ViewSpec(
    "latency",
    signals=[
        SignalSpec("p99_ms"),            # native range ~ 10..1000 ms
        SignalSpec("queue_depth"),       # native range ~ 0..5000
    ],
    weight=2.0,                         # matters most
)
reliability_view = ViewSpec(
    "reliability",
    signals=[
        SignalSpec("error_rate", floor=0.15),      # must-attend
        SignalSpec("saturation"),
    ],
    weight=1.5,
)
cost_view = ViewSpec(
    "cost",
    signals=[
        SignalSpec("spend_usd_hr"),              # native range ~ 100..10_000
        SignalSpec("spot_availability", ceiling=0.4),
    ],
    weight=1.0,
)

mv = MultiViewCombiner([latency_view, reliability_view, cost_view],
                       query_dim=2, temperature=1.0)

# ---------------------------------------------------------------------------
# 2. Scale normalisers — one per view so each view keeps its own statistics
# ---------------------------------------------------------------------------
view_normalisers = {
    v.name: ScaleInvariantNormalizer(n_signals=len(v.signals),
                                     alpha=0.05, warmup=20)
    for v in [latency_view, reliability_view, cost_view]
}

# ---------------------------------------------------------------------------
# 3. Temperature schedule — start exploratory, anneal to exploitation
# ---------------------------------------------------------------------------
tau_sched = TemperatureScheduler(tau0=2.0, tau_min=0.3, kind="sqrt")

# ---------------------------------------------------------------------------
# 4. Per-view FTRL learners — entropy geometry (Hedge) for latency,
#    l2 geometry (smoother) for cost; reliability stays with entropy.
# ---------------------------------------------------------------------------
learners = {
    "latency":     FTRLLearner(n_signals=2, eta=0.5, regularizer="entropy"),
    "reliability": FTRLLearner(n_signals=2, eta=0.5, regularizer="entropy"),
    "cost":        FTRLLearner(n_signals=2, eta=0.3, regularizer="l2"),
}

# ---------------------------------------------------------------------------
# 5. Contraction monitor (1D: action = replica_delta, state = queue_depth)
# ---------------------------------------------------------------------------
contraction = JacobianContractionMonitor(window=32, min_samples=8,
                                          threshold=1.0)

# ---------------------------------------------------------------------------
# 6. Blame store + drift detector
# ---------------------------------------------------------------------------
tca = TemporalCreditAssigner(decay=0.9)
drift = WassersteinDriftDetector(
    n_signals=3,                          # detect drift on *merge weights*
    threshold=0.2,
    fast_alpha=0.3, slow_alpha=0.03,
)

# ---------------------------------------------------------------------------
# 7. Simulation harness
# ---------------------------------------------------------------------------
rng = np.random.default_rng(42)
last_queue = 0.0

print(f"{'tick':>4} {'τ':>5} {'view merges':>20} "
      f"{'loc_w (lat/rel/cost)':>28} {'Δreplicas':>10} "
      f"{'queue':>7} {'gain':>6}")

HISTORY = []
for tick in range(120):
    # --- 7a. Synthesise raw signals on very different native scales ---
    # Regime flip at tick 60: reliability suddenly matters most.
    regime = 0 if tick < 60 else 1
    noise = 0.1 * rng.standard_normal(6)
    p99_raw       = 200 + (150 if regime == 0 else 50) * np.sin(tick / 8) + 30 * noise[0]
    queue_raw     = 500 + 400 * abs(np.sin(tick / 10)) + 80 * noise[1]
    err_raw       = (0.005 if regime == 0 else 0.03) + 0.005 * noise[2]
    saturation    = 0.5 + 0.2 * np.sin(tick / 6) + 0.05 * noise[3]
    spend_raw     = 3000 + 500 * np.cos(tick / 15) + 200 * noise[4]
    spot_avail    = 0.7 + 0.1 * np.sin(tick / 20) + 0.05 * noise[5]

    # --- 7b. Normalise per-view ---
    lat_z = view_normalisers["latency"].observe_and_transform(
        np.array([p99_raw, queue_raw]),
    )
    rel_z = view_normalisers["reliability"].observe_and_transform(
        np.array([err_raw, saturation]),
    )
    cost_z = view_normalisers["cost"].observe_and_transform(
        np.array([spend_raw, spot_avail]),
    )

    # --- 7c. Build per-view queries and values (proposed replica deltas) ---
    # Values follow "large positive z → scale up more aggressively".
    lat_vals = [np.array([3.0 * lat_z[0]]),        np.array([2.0 * lat_z[1]])]
    rel_vals = [np.array([6.0 * rel_z[0]]),        np.array([4.0 * rel_z[1]])]
    cost_vals = [np.array([-1.5 * cost_z[0]]),     np.array([1.0 * cost_z[1]])]

    # --- 7d. Inject learner priors as per-view bias (tilt the softmax) ---
    for view_name, combiner in zip(
        ["latency", "reliability", "cost"], mv._combiners,
    ):
        logits = learners[view_name].logits()
        for spec, lg in zip(combiner.signals, logits):
            spec.bias = float(lg)
        combiner.temperature = tau_sched.tau(tick)

    # --- 7e. Merge across views ---
    action, merge_w = mv.combine(
        query_per_view=[lat_z, rel_z, cost_z],
        values_per_view=[lat_vals, rel_vals, cost_vals],
    )
    per_view = mv.last_view_weights()

    # --- 7f. Observe "queue" dynamics so the contraction monitor works ---
    u = action.item()
    # Synthetic plant : queue next = 0.7·queue + scale·u + noise
    next_queue = 0.7 * last_queue + 25.0 * u + rng.normal(0, 5)
    dq = next_queue - last_queue
    last_queue = next_queue
    contraction.observe(u, dq, step=tick)

    # --- 7g. Pretend losses proportional to |raw signal excess| ---
    losses = {
        "latency":     np.array([min(1.0, max(0.0, lat_z[0] / 3.0)),
                                 min(1.0, max(0.0, lat_z[1] / 3.0))]),
        "reliability": np.array([min(1.0, max(0.0, rel_z[0] / 3.0)),
                                 min(1.0, max(0.0, rel_z[1] / 3.0))]),
        "cost":        np.array([min(1.0, max(0.0, abs(cost_z[0]) / 3.0)),
                                 min(1.0, max(0.0, abs(cost_z[1]) / 3.0))]),
    }
    for name, L in losses.items():
        learners[name].update(L)

    # --- 7h. Record blame and drift observations ---
    tca.record(tick, weights=merge_w, losses=np.array(
        [losses["latency"].mean(),
         losses["reliability"].mean(),
         losses["cost"].mean()]),
        signal_names=["latency", "reliability", "cost"])
    drift.observe(merge_w, step=tick)

    # --- 7i. Print condensed trace ---
    if tick % 10 == 0 or tick in (59, 60):
        g = contraction.gain()
        g_str = f"{g:.2f}" if g is not None else "—"
        print(
            f"{tick:>4} {tau_sched.tau(tick):>5.2f} "
            f"[{merge_w[0]:.2f},{merge_w[1]:.2f},{merge_w[2]:.2f}]       "
            f"lat={per_view[0][0]:.2f}/{per_view[0][1]:.2f}  "
            f"rel={per_view[1][0]:.2f}/{per_view[1][1]:.2f}  "
            f"{u:>+10.2f} {next_queue:>7.0f} {g_str:>6}"
        )


# ---------------------------------------------------------------------------
# 8. Post-run diagnostics
# ---------------------------------------------------------------------------
print("\n=== Post-run diagnostics =====================================")

print(f"\nFinal temperature : {tau_sched.tau(119):.3f}  (started at 2.00)")
print(f"Contraction gain  : {contraction.gain():.3f} (stable if |.| < 1.0)")
print(f"Contraction alerts: {len(contraction.alerts())}")
print(f"Drift alerts      : {len(drift.alerts())}")

print("\nBlame for an incident at tick 90 (top 5):")
top5 = tca.attribute(incident_tick=90, window=30, top_k=5)
for e in top5:
    print(f"  tick={e.tick:>3}  {e.signal_name:>11}  "
          f"score={e.score:.3f}  w={e.weight:.2f}  loss={e.loss:.2f}")

print("\nLatency learner final weights (entropy geometry):")
print(" ", learners["latency"].weights().round(3).tolist())
print("Cost learner final weights (l2 geometry):")
print(" ", learners["cost"].weights().round(3).tolist())
