"""§11 Catch/SRE wrapper boundary.

This study is deliberately SRE-facing.  It does not claim anything about
SpaceX internals; it checks whether a catch-allocation migration wrapper
keeps the important bounded-LS evidence visible.

Baseline:
    A residual-hiding allocator normalizes shares to exactly match demand
    and reports zero residual, even when that violates instance caps or
    placement constraints.

After:
    :class:`sre_control.CatchLoadAdapter` delegates to bounded LS, obeys
    per-instance caps, and emits ``bounded_ls_residual`` when demand
    cannot be exactly met.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from analysis._common import HAS_MPL, save_fig, summary_banner
from sre_control import CatchLoadAdapter, Instance


def _instances() -> list[Instance]:
    return [
        Instance("east-a", np.array([1.0, 0.0]), rps_min=0.0, rps_max=120.0),
        Instance("east-b", np.array([1.0, 0.0]), rps_min=0.0, rps_max=120.0),
        Instance("west-a", np.array([0.0, 1.0]), rps_min=0.0, rps_max=80.0),
    ]


def _capacity_violation(shares: np.ndarray, instances: list[Instance]) -> float:
    lb = np.array([inst.rps_min for inst in instances])
    ub = np.array([inst.rps_max for inst in instances])
    return float(
        max(
            0.0,
            np.max(
                np.concatenate(
                    [
                        shares - ub,
                        lb - shares,
                    ]
                )
            ),
        )
    )


def _cases(rng: np.random.Generator, cases_per_regime: int) -> list[tuple[str, float, np.ndarray]]:
    cases: list[tuple[str, float, np.ndarray]] = []
    for _ in range(cases_per_regime):
        demand = float(rng.uniform(120.0, 170.0))
        east_fraction = float(rng.uniform(0.58, 0.66))
        cases.append(
            (
                "feasible",
                demand,
                np.array([demand * east_fraction, demand * (1.0 - east_fraction)]),
            )
        )

    for _ in range(cases_per_regime):
        demand = float(rng.uniform(360.0, 460.0))
        east_fraction = float(rng.uniform(0.58, 0.72))
        cases.append(
            (
                "total_overload",
                demand,
                np.array([demand * east_fraction, demand * (1.0 - east_fraction)]),
            )
        )

    for _ in range(cases_per_regime):
        demand = float(rng.uniform(220.0, 300.0))
        # Total demand is feasible, but west demand exceeds west-a cap (80 RPS).
        west_target = float(rng.uniform(120.0, 170.0))
        cases.append(
            (
                "placement_infeasible",
                demand,
                np.array([demand - west_target, west_target]),
            )
        )
    return cases


def main(
    n_cases: int = 120, seed: int = 0, artifacts_dir: Path | str | None = None
) -> dict:
    artifacts = Path(artifacts_dir) if artifacts_dir is not None else None

    rng = np.random.default_rng(seed)
    instances = _instances()
    adapter = CatchLoadAdapter(instances=instances)
    cases_per_regime = max(1, n_cases // 3)
    cases = _cases(rng, cases_per_regime)

    case_counts = {"feasible": 0, "total_overload": 0, "placement_infeasible": 0}
    base_reported_residual = []
    base_capacity_violation = []
    after_reported_residual = []
    after_capacity_violation = []
    visible_events = []
    quiet_feasible = []
    total_overload_visible = []
    placement_visible = []

    for kind, demand, placement_target in cases:
        case_counts[kind] += 1
        if kind == "feasible":
            # Exact matching is possible; the baseline is not punished here.
            baseline_shares = np.array(
                [0.5 * placement_target[0], 0.5 * placement_target[0], placement_target[1]],
                dtype=float,
            )
        elif kind == "total_overload":
            # Exact-share normalization reports no residual, but overloads boxes.
            baseline_shares = np.array(
                [0.36 * demand, 0.34 * demand, 0.30 * demand],
                dtype=float,
            )
        else:
            # Exact placement pushes the single west instance past its cap.
            baseline_shares = np.array(
                [0.5 * placement_target[0], 0.5 * placement_target[0], placement_target[1]],
                dtype=float,
            )
        base_reported_residual.append(0.0)
        base_capacity_violation.append(_capacity_violation(baseline_shares, instances))

        trace = adapter.allocate(demand, placement_target)
        shares = np.asarray(trace["shares"], dtype=float)
        after_reported_residual.append(float(trace["rps_residual"]))
        after_capacity_violation.append(_capacity_violation(shares, instances))
        has_bounded_event = any(
            event["kind"] == "bounded_ls_residual" for event in trace["events"]
        )
        if kind == "feasible":
            quiet_feasible.append(
                trace["rps_residual"] < 1e-6
                and max(trace["zone_residual"]) < 1e-6
                and not trace["events"]
            )
        elif kind == "total_overload":
            is_visible = trace["rps_residual"] > 1e-6 and has_bounded_event
            total_overload_visible.append(is_visible)
            visible_events.append(is_visible)
        else:
            is_visible = max(trace["zone_residual"]) > 1e-6 and has_bounded_event
            placement_visible.append(is_visible)
            visible_events.append(is_visible)

    base_capacity_violation = np.asarray(base_capacity_violation, dtype=float)
    after_capacity_violation = np.asarray(after_capacity_violation, dtype=float)
    after_reported_residual = np.asarray(after_reported_residual, dtype=float)

    before = {
        "reported_residual_mean": 0.0,
        "capacity_violation_pct": float(np.mean(base_capacity_violation > 1e-6) * 100),
        "mean_capacity_excess": float(base_capacity_violation.mean()),
    }
    after = {
        "reported_residual_mean": float(after_reported_residual.mean()),
        "capacity_violation_pct": float(np.mean(after_capacity_violation > 1e-6) * 100),
        "mean_capacity_excess": float(after_capacity_violation.mean()),
        "event_visible_fraction": float(np.mean(visible_events)),
    }
    diagnostics = {
        "case_counts": case_counts,
        "feasible_quiet_fraction": float(np.mean(quiet_feasible)),
        "total_overload_event_visible_fraction": float(np.mean(total_overload_visible)),
        "placement_infeasible_event_visible_fraction": float(np.mean(placement_visible)),
    }

    banner = summary_banner("§11 Catch/SRE wrapper boundary", before, after)
    print(banner)

    if HAS_MPL:
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 2, figsize=(10, 4))
        axes[0].hist(base_capacity_violation, bins=24, alpha=0.6, label="hidden baseline")
        axes[0].hist(after_capacity_violation, bins=24, alpha=0.6, label="wrapper")
        axes[0].set_xlabel("capacity excess [RPS]")
        axes[0].set_ylabel("count")
        axes[0].set_title("box violation")
        axes[0].legend()
        axes[0].grid(True, alpha=0.3)

        axes[1].hist(after_reported_residual, bins=24, color="#4c78a8")
        axes[1].set_xlabel("reported residual [RPS]")
        axes[1].set_ylabel("count")
        axes[1].set_title("visible unmet demand")
        axes[1].grid(True, alpha=0.3)
        save_fig(fig, "s11_catch_sre_wrapper", artifacts_dir=artifacts)
        plt.close(fig)

    return {"before": before, "after": after, "diagnostics": diagnostics, "banner": banner}


if __name__ == "__main__":
    main()
