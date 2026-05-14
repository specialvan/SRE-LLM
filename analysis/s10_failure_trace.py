"""§10 · Failure-trace before vs after — event-level evidence.

Scenario
--------
Same 300 s synthetic service traffic as §9, with *explicit* fault injection
windows so the SREControlStack actually emits runtime events to measure:

    t ∈ [40, 60]    — `missing_sensor` burst: drop the primary sensor reading
    t ∈ [120, 140]  — `replica_bound_active`: clamp replicas_max so MPC hits ceiling
    t ∈ [220, 230]  — `unsafe_proposal_projected`: emit off-axis NN proposal

Baseline (no stack observability)
---------------------------------
Run the stack but discard ``runtime.events`` — equivalent to today's SRE
dashboards that only see the outcome (latency / replica count).

After (stack observability on)
------------------------------
Keep ``runtime.events`` and derive four evidence artefacts:

1.  event density vs time          → docs/assets/s10_event_density.png
2.  kind co-occurrence (Jaccard)   → docs/assets/s10_cooccurrence.png
3.  full JSONL trace               → analysis/artifacts/s10_trace_full.jsonl
4.  reviewer sample (first events) → analysis/artifacts/s10_trace_sample.jsonl

Metrics rolled into SUMMARY.txt
-------------------------------
- ``event_count_total``              — how many runtime events fired
- ``distinct_kinds``                 — how many unique kinds observed
- ``event_visible_fraction``         — fraction of injected-window ticks with any
                                       emitted event
- ``true_degraded_fraction``         — fraction of ticks that belong to configured
                                       injection windows
- ``background_event_fraction``      — fraction of non-injection ticks with any
                                       event (should stay low)
- ``injected_window_coverage``       — per-window visibility and expected-kind
                                       coverage
- ``degraded_tick_fraction``         — legacy coarse metric: fraction of ticks
                                       with any event, kept only for backwards
                                       compatibility
- ``mttr_seconds``                   — mean time-to-recover based on event-kind
                                       span in seconds

Counter-example
---------------
We do NOT change the baseline traffic / noise to "help" the after run.
The only difference is whether the stack's ``runtime.events`` channel is
read or ignored. All other variables (seed, latency model, SLO budget,
autoscaler tuning) are identical.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np

from sre_control import (
    Instance,
    PredictiveAutoscaler,
    Signal,
    SignalFusion,
    SLOGuardrail,
    SREControlStack,
    WeightedLoadBalancer,
)

from analysis._common import ARTIFACTS, HAS_MPL, save_fig, summary_banner


# ---------------------------------------------------------------------------
# Scenario
# ---------------------------------------------------------------------------

DT = 5.0
T_FINAL = 300.0
SLO_BUDGET_MS = 60.0

# Fault-injection windows (seconds)
WINDOW_MISSING = (40, 60)
WINDOW_BOUND = (120, 140)
WINDOW_UNSAFE = (220, 230)


@dataclass(frozen=True)
class InjectionWindow:
    name: str
    bounds: tuple[float, float]
    expected_kind: str


INJECTION_WINDOWS = (
    InjectionWindow("missing_sensor", WINDOW_MISSING, "missing_sensor"),
    InjectionWindow("replica_bound_active", WINDOW_BOUND, "replica_bound_active"),
    InjectionWindow(
        "unsafe_proposal_projected", WINDOW_UNSAFE, "unsafe_proposal_projected"
    ),
)


def _true_rps(t: float) -> float:
    return 1200 + 400 * np.sin(t / 40)


def _true_latency(t: float, replicas: int, rps: float) -> float:
    capacity = 110.0
    rho = min(0.98, rps / max(replicas, 1) / capacity)
    return 18.0 + 12.0 * rho / max(1e-3, 1.0 - rho)


def _build_stack() -> tuple[SREControlStack, Signal]:
    fusion = SignalFusion(
        x0=np.array([1200.0, 25.0, 0.3]),
        P0=np.diag([200**2, 10**2, 0.2**2]),
        Q=np.diag([5.0, 0.2, 0.01]),
        x_ref=np.array([1200.0, 25.0, 0.3]),
        theta=0.1,
    )
    metrics = Signal(
        name="metrics",
        h=lambda x: x[0:2],
        H=lambda x: np.array([[1, 0, 0], [0, 1, 0]]),
        R=np.diag([50**2, 4**2]),
    )
    asc = PredictiveAutoscaler(
        per_replica_rps=100.0,
        replicas_min=4,
        replicas_max=50,
        max_step=5,
        dt=DT,
        horizon=10,
        q_slo=150.0,
        r_cost=0.5,
    )
    guard = SLOGuardrail(
        nominal_direction=np.array([0.6, 0.4, 0]),
        theta_max_deg=15.0,
        magnitude_cap=5_000.0,
    )
    lb = WeightedLoadBalancer(
        instances=[
            Instance("east", np.array([1, 0.0]), rps_min=20, rps_max=1500),
            Instance("west", np.array([0, 1.0]), rps_min=20, rps_max=1500),
        ]
    )
    return (
        SREControlStack(fusion=fusion, autoscaler=asc, guardrail=guard, balancer=lb),
        metrics,
    )


# ---------------------------------------------------------------------------
# Run one scenario and collect events
# ---------------------------------------------------------------------------


def _run_scenario() -> tuple[list[list[dict]], np.ndarray, np.ndarray]:
    """Return (per-tick event lists, replicas_trace, latency_trace).

    The same scenario will be run once.  The "before" analysis is just
    ignoring ``runtime.events`` in the trace we collect.
    """
    rng = np.random.default_rng(0)
    t_grid = np.arange(0, T_FINAL, DT)
    replicas = 10
    event_lists: list[list[dict]] = []
    replicas_trace, latency_trace = [], []

    stack, metrics = _build_stack()

    for t in t_grid:
        rps = _true_rps(t) + rng.normal(0, 30)
        lat = _true_latency(t, replicas, rps)

        # ---- inject fault windows ----
        reading: np.ndarray | None = np.array([rps, lat])
        if WINDOW_MISSING[0] <= t <= WINDOW_MISSING[1]:
            reading = None  # triggers missing_sensor

        zone_target = np.array([rps * 0.6, rps * 0.4])
        nominal = np.array([0.6, 0.4, 0.0])
        nn_proposal = nominal / np.linalg.norm(nominal) * rps
        if WINDOW_UNSAFE[0] <= t <= WINDOW_UNSAFE[1]:
            # Push the proposal well outside the 15° cone (nominal is
            # [0.6, 0.4, 0]). [1, -1, 0] is ~78° off the nominal, guaranteed
            # to violate `unsafe_proposal_projected`.
            nn_proposal = np.array([rps * 1.0, -rps * 1.0, 0.0])

        original_replicas_max = stack.autoscaler.replicas_max
        if WINDOW_BOUND[0] <= t <= WINDOW_BOUND[1]:
            stack.autoscaler.replicas_max = 18

        try:
            entry = stack.step(
                dt=DT,
                sensor_readings=[(metrics, reading)],
                forecast_rps=_true_rps(t + 20),
                current_replicas=replicas,
                zone_target=zone_target,
                nn_proposal=nn_proposal,
            )
        finally:
            stack.autoscaler.replicas_max = original_replicas_max

        replicas = max(entry["replicas_next"], 10)
        replicas_trace.append(replicas)
        latency_trace.append(lat)
        event_lists.append(entry["runtime"].get("events", []))

    return event_lists, np.array(replicas_trace), np.array(latency_trace)


# ---------------------------------------------------------------------------
# Derived metrics
# ---------------------------------------------------------------------------


def _ticks_in_window(t_grid: np.ndarray, bounds: tuple[float, float]) -> list[int]:
    start, end = bounds
    return [i for i, t in enumerate(t_grid) if start <= t <= end]


def _derive_metrics(event_lists: list[list[dict]]) -> dict:
    counts = [len(evs) for evs in event_lists]
    kinds_per_tick = [{e["kind"] for e in evs} for evs in event_lists]
    all_kinds = set().union(*kinds_per_tick) if kinds_per_tick else set()
    degraded_ticks = sum(1 for c in counts if c > 0)
    t_grid = np.arange(0, len(event_lists) * DT, DT)

    injected_tick_sets = [
        set(_ticks_in_window(t_grid, window.bounds)) for window in INJECTION_WINDOWS
    ]
    injected_ticks = set().union(*injected_tick_sets) if injected_tick_sets else set()
    background_ticks = set(range(len(event_lists))) - injected_ticks
    visible_injected_ticks = [i for i in injected_ticks if counts[i] > 0]
    visible_background_ticks = [i for i in background_ticks if counts[i] > 0]

    injected_window_coverage = {}
    for window in INJECTION_WINDOWS:
        tick_idxs = _ticks_in_window(t_grid, window.bounds)
        expected_kind_ticks = [
            i for i in tick_idxs if window.expected_kind in kinds_per_tick[i]
        ]
        visible_ticks = [i for i in tick_idxs if counts[i] > 0]
        denominator = max(1, len(tick_idxs))
        injected_window_coverage[window.name] = {
            "expected_kind": window.expected_kind,
            "event_visible_fraction": len(visible_ticks) / denominator,
            "expected_kind_fraction": len(expected_kind_ticks) / denominator,
        }

    # mean time-to-recover: ticks between first and last event of each kind
    mttr_per_kind = {}
    for kind in all_kinds:
        idxs = [i for i, ks in enumerate(kinds_per_tick) if kind in ks]
        if idxs:
            mttr_per_kind[kind] = (idxs[-1] - idxs[0]) * DT
    mttr = float(np.mean(list(mttr_per_kind.values()))) if mttr_per_kind else 0.0

    return {
        "event_count_total": int(sum(counts)),
        "distinct_kinds": int(len(all_kinds)),
        "degraded_tick_fraction": 100.0 * degraded_ticks / max(1, len(counts)),
        "true_degraded_fraction": len(injected_ticks) / max(1, len(event_lists)),
        "event_visible_fraction": (
            len(visible_injected_ticks) / max(1, len(injected_ticks))
        ),
        "background_event_fraction": (
            len(visible_background_ticks) / max(1, len(background_ticks))
        ),
        "injected_window_coverage": injected_window_coverage,
        "mttr_seconds": mttr,
        "_counts": counts,
        "_kinds_per_tick": kinds_per_tick,
        "_all_kinds": sorted(all_kinds),
    }


def _jaccard_matrix(kinds_per_tick: list[set], all_kinds: list[str]) -> np.ndarray:
    """Pairwise tick-level Jaccard over event kinds."""
    n = len(all_kinds)
    mat = np.eye(n)
    for i, ki in enumerate(all_kinds):
        for j, kj in enumerate(all_kinds):
            if i >= j:
                continue
            both = sum(1 for s in kinds_per_tick if ki in s and kj in s)
            either = sum(1 for s in kinds_per_tick if ki in s or kj in s)
            j_val = both / either if either else 0.0
            mat[i, j] = mat[j, i] = j_val
    return mat


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> dict:
    event_lists, replicas, latency = _run_scenario()
    after = _derive_metrics(event_lists)
    # "Before" = pretend the stack has no runtime.events channel, so
    # everything except replicas/latency is invisible.
    before = {
        "event_count_total": 0,
        "distinct_kinds": 0,
        "degraded_tick_fraction": 0.0,
        "mttr_seconds": 0.0,
    }

    # Guard against false claims about before/after
    assert (
        after["event_count_total"] > 0
    ), "no events fired; fault injection windows may be misconfigured"
    assert (
        after["distinct_kinds"] >= 2
    ), "need at least 2 distinct event kinds for co-occurrence to be meaningful"

    # Banner
    before_for_banner = {k: v for k, v in before.items() if not k.startswith("_")}
    after_for_banner = {k: v for k, v in after.items() if not k.startswith("_")}
    banner = summary_banner(
        "§10 · Failure trace (event-level evidence)",
        before_for_banner,
        after_for_banner,
    )
    print(banner)

    # JSONL artifacts: full trace for verification, sample for reviewers.
    trace_rows = [
        {"tick": tick_idx, "t_seconds": tick_idx * DT, **ev}
        for tick_idx, evs in enumerate(event_lists)
        for ev in evs
    ]
    full_path = ARTIFACTS / "s10_trace_full.jsonl"
    with open(full_path, "w", encoding="utf-8") as fh:
        for row in trace_rows:
            fh.write(json.dumps(row) + "\n")

    sample_path = ARTIFACTS / "s10_trace_sample.jsonl"
    with open(sample_path, "w", encoding="utf-8") as fh:
        for row in trace_rows[:10]:
            fh.write(json.dumps(row) + "\n")

    if HAS_MPL:
        import matplotlib.pyplot as plt
        from pathlib import Path as _P

        docs_assets = _P(__file__).resolve().parent.parent / "docs" / "assets"
        docs_assets.mkdir(parents=True, exist_ok=True)

        t_axis = np.arange(len(event_lists)) * DT

        # ---- (1) event density vs time ----
        fig, ax = plt.subplots(figsize=(11, 3.2))
        ax.plot(
            t_axis,
            after["_counts"],
            color="#1f5fa3",
            lw=1.8,
            label="runtime.events / tick",
        )
        # shade injected windows
        for (w0, w1), label, color in [
            (WINDOW_MISSING, "missing_sensor", "#fbf1ed"),
            (WINDOW_BOUND, "replica_bound", "#fef7e7"),
            (WINDOW_UNSAFE, "unsafe_proposal", "#eaf2e6"),
        ]:
            ax.axvspan(w0, w1, color=color, alpha=0.8)
            ax.text(
                (w0 + w1) / 2,
                max(after["_counts"]) + 0.5,
                label,
                ha="center",
                fontsize=9,
                color="#6a7889",
            )
        ax.set_xlabel("t [s]")
        ax.set_ylabel("events/tick")
        ax.set_title(
            "§10 Event density over time (stack observability ON)",
            fontsize=11,
            color="#1b2430",
        )
        ax.grid(True, alpha=0.3)
        ax.legend(loc="upper right")
        fig.tight_layout()
        fig.savefig(docs_assets / "s10_event_density.png", dpi=130, bbox_inches="tight")
        save_fig(fig, "s10_event_density")
        plt.close(fig)

        # ---- (2) co-occurrence heat map ----
        if len(after["_all_kinds"]) >= 2:
            mat = _jaccard_matrix(after["_kinds_per_tick"], after["_all_kinds"])
            fig, ax = plt.subplots(figsize=(6, 5))
            im = ax.imshow(mat, cmap="YlGnBu", vmin=0, vmax=1)
            ax.set_xticks(range(len(after["_all_kinds"])))
            ax.set_yticks(range(len(after["_all_kinds"])))
            ax.set_xticklabels(after["_all_kinds"], rotation=30, ha="right", fontsize=9)
            ax.set_yticklabels(after["_all_kinds"], fontsize=9)
            for i in range(mat.shape[0]):
                for j in range(mat.shape[1]):
                    ax.text(
                        j,
                        i,
                        f"{mat[i, j]:.2f}",
                        ha="center",
                        va="center",
                        fontsize=8,
                        color="#1b2430" if mat[i, j] < 0.5 else "white",
                    )
            ax.set_title(
                "§10 Event kind co-occurrence (Jaccard)", fontsize=11, color="#1b2430"
            )
            fig.colorbar(im, ax=ax, shrink=0.75)
            fig.tight_layout()
            fig.savefig(
                docs_assets / "s10_cooccurrence.png", dpi=130, bbox_inches="tight"
            )
            save_fig(fig, "s10_cooccurrence")
            plt.close(fig)

    # Clean the banner-metrics dict to what summary_banner expects
    return {"before": before_for_banner, "after": after_for_banner, "banner": banner}


if __name__ == "__main__":
    main()
