"""End-to-end SRE story GIF.

Animates a realistic release timeline:

    t = 0..30  healthy releases,  mu/sigma tighten
    t = 30..40 error rate creeps up, Cox risk starts warming
    t = 40..48 alarm triggers, pipeline emits ROLLBACK

Output: ``docs/images/story_end_to_end.gif``
"""
from __future__ import annotations

import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FuncAnimation, PillowWriter

from gan_matchmaking.core import AppConfig, MetricsRegistry
from gan_matchmaking.sre import (
    ReleaseCandidate,
    ReleaseContext,
    SelfIterationPipeline,
    Service,
)


OUT_DIR = Path(__file__).parent / "images"
OUT_DIR.mkdir(exist_ok=True, parents=True)

PRIMARY = "#2f6feb"
ACCENT = "#f04e65"
GREEN = "#2ca05b"
ORANGE = "#f59f3d"
SOFT = "#8c8c8c"


def _candidate():
    return ReleaseCandidate(
        id="canary-5pct",
        service_id="payments-api",
        strategy="canary",
        canary_fraction=0.05,
        rollback_budget_seconds=300,
        expected_success=0.996,
    )


def _ctx(service: Service, error_rate: float, budget_remaining: float):
    telemetry = {"error_rate_p99": float(error_rate),
                 "latency_p99_ms": 120 + 50 * float(error_rate) * 20,
                 "throughput_rps": 5000.0,
                 "memory_rss_mb": 512.0}
    return ReleaseContext(
        service=service,
        candidates=[_candidate()],
        telemetry=telemetry,
        dependencies=["billing-worker"],
        error_budget_remaining=float(budget_remaining),
        correlation_id=None,
    )


def main() -> None:
    pipeline = SelfIterationPipeline(config=AppConfig(seed=7),
                                     metrics=MetricsRegistry())
    svc = Service(id="payments-api", mu=0.99, sigma=0.02, tier="critical")
    pipeline.register_service(svc)

    rng = np.random.default_rng(1)
    n_frames = 48
    series_mu, series_sigma, series_conf = [], [], []
    series_err, series_risk, series_kind = [], [], []

    # Reserve the latest context so the final frame shows the decision.
    latest_trace = None
    for t in range(n_frames):
        if t < 30:
            # Healthy era — small error rate, mostly successful releases.
            err = rng.uniform(0.001, 0.004)
            success = rng.random() < 0.98
            budget = 0.95 - 0.005 * t
        elif t < 40:
            # Degradation starts.
            err = 0.004 + (t - 30) * 0.002 + rng.normal(0, 0.0005)
            success = rng.random() < 0.85
            budget = max(0.0, 0.85 - 0.02 * (t - 30))
        else:
            # Severe incident.
            err = 0.025 + (t - 40) * 0.005 + rng.normal(0, 0.001)
            success = rng.random() < 0.4
            budget = max(0.0, 0.65 - 0.04 * (t - 40))

        pipeline.observe_release("payments-api", success=success,
                                  duration_seconds=15.0)
        decision = pipeline.decide(_ctx(svc, err, budget))
        latest_trace = decision

        series_mu.append(svc.mu)
        series_sigma.append(svc.sigma)
        series_conf.append(svc.mu - 2 * svc.sigma)
        series_err.append(err)
        series_risk.append(decision.risk_prob)
        series_kind.append(decision.kind.value)

    series_mu = np.array(series_mu)
    series_sigma = np.array(series_sigma)
    series_conf = np.clip(np.array(series_conf), 0.0, 1.0)
    series_err = np.clip(np.array(series_err), 0.0, 0.08)
    series_risk = np.array(series_risk)

    # Build animation.
    fig, axes = plt.subplots(2, 2, figsize=(10.5, 6.2))
    fig.suptitle("End-to-end SRE story · reliability drift → Cox alarm → ROLLBACK",
                 fontsize=13)

    ax_tel, ax_conf, ax_risk, ax_kind = axes[0, 0], axes[0, 1], axes[1, 0], axes[1, 1]

    xs = np.arange(n_frames)
    tel_line, = ax_tel.plot([], [], color=ACCENT, lw=2.1)
    ax_tel.set_xlim(0, n_frames - 1); ax_tel.set_ylim(0, 0.08)
    ax_tel.axhline(0.01, color=SOFT, ls=":", lw=1, label="SLO threshold")
    ax_tel.set_title("Telemetry · error_rate_p99")
    ax_tel.set_xlabel("release #"); ax_tel.set_ylabel("error rate")
    ax_tel.legend(fontsize=8, loc="upper left")

    conf_line, = ax_conf.plot([], [], color=PRIMARY, lw=2.1)
    ax_conf.set_xlim(0, n_frames - 1); ax_conf.set_ylim(0.5, 1.02)
    ax_conf.set_title("Reliability · μ − 2σ (confidence)")
    ax_conf.set_xlabel("release #"); ax_conf.set_ylabel("confidence")

    risk_line, = ax_risk.plot([], [], color=ORANGE, lw=2.1)
    ax_risk.axhline(0.3, color=SOFT, ls=":", lw=1, label="warn")
    ax_risk.axhline(0.6, color=ACCENT, ls=":", lw=1, label="alarm")
    ax_risk.set_xlim(0, n_frames - 1); ax_risk.set_ylim(0, 1.0)
    ax_risk.set_title("Cox risk · P(incident ≤ 24h)")
    ax_risk.set_xlabel("release #"); ax_risk.set_ylabel("risk")
    ax_risk.legend(fontsize=8, loc="upper left")

    kind_colors = {"go": GREEN, "canary": ORANGE, "hold": SOFT,
                   "rollback": ACCENT, "escalate": "#7a1cad"}
    kind_bars = ax_kind.bar(
        xs, np.zeros_like(xs, dtype=float),
        color=[kind_colors.get(k, SOFT) for k in series_kind]
    )
    ax_kind.set_xlim(0, n_frames - 1); ax_kind.set_ylim(0, 4)
    ax_kind.set_title("Decision kind timeline")
    ax_kind.set_xlabel("release #"); ax_kind.set_ylabel("")
    ax_kind.set_yticks([1, 2, 3]); ax_kind.set_yticklabels(["CANARY", "HOLD", "ROLLBACK"])
    label = ax_kind.text(1, 3.6, "", fontsize=10)

    def update(i):
        tel_line.set_data(xs[:i + 1], series_err[:i + 1])
        conf_line.set_data(xs[:i + 1], series_conf[:i + 1])
        risk_line.set_data(xs[:i + 1], series_risk[:i + 1])
        for j, b in enumerate(kind_bars):
            if j <= i:
                height = {"canary": 1, "hold": 2, "rollback": 3,
                          "go": 0.5, "escalate": 4}.get(series_kind[j], 0.2)
                b.set_height(height)
            else:
                b.set_height(0)
        label.set_text(
            f"t={i} · err={series_err[i]:.3%}  μ={series_mu[i]:.3f}  "
            f"σ={series_sigma[i]:.3f}  risk={series_risk[i]:.2f}  "
            f"→ {series_kind[i].upper()}"
        )
        return tel_line, conf_line, risk_line, label

    anim = FuncAnimation(fig, update, frames=n_frames, interval=140)
    out = OUT_DIR / "story_end_to_end.gif"
    anim.save(out, writer=PillowWriter(fps=8))
    plt.close(fig)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
