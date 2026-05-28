"""§12 Replay-style SRE input evidence.

This is a synthetic replay fixture, not a production trace.  The value
of the study is contract coverage: a fixed JSONL input stream is replayed
through one continuous ``SREControlStack`` and expected event kinds must
surface without nominal background events.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from analysis._common import summary_banner
from sre_control import (
    Instance,
    PredictiveAutoscaler,
    Signal,
    SignalFusion,
    SLOGuardrail,
    SREControlStack,
    StabilityGuard,
    WeightedLoadBalancer,
    sre_error_budget_V,
)


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sre_replay.jsonl"


def _load_fixture() -> list[dict]:
    rows = []
    for line in FIXTURE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _stack() -> tuple[SREControlStack, Signal]:
    fusion = SignalFusion(
        x0=np.array([900.0, 42.0, 0.004]),
        P0=np.diag([80.0**2, 4.0**2, 0.002**2]),
        Q=np.diag([2.0, 0.2, 1e-6]),
        x_ref=np.array([950.0, 45.0, 0.005]),
        theta=0.05,
    )
    metrics = Signal(
        name="metrics",
        h=lambda x: x,
        H=lambda x: np.eye(3),
        R=np.diag([20.0**2, 2.0**2, 0.001**2]),
    )
    stack = SREControlStack(
        fusion=fusion,
        autoscaler=PredictiveAutoscaler(
            per_replica_rps=100.0,
            replicas_min=4,
            replicas_max=30,
            max_step=4,
            dt=5.0,
            horizon=6,
        ),
        guardrail=SLOGuardrail(
            nominal_direction=np.array([1.0, 0.0, 0.0]),
            theta_max_deg=20.0,
            magnitude_cap=2_500.0,
        ),
        balancer=WeightedLoadBalancer(
            instances=[
                Instance("east", np.array([1.0, 0.0]), 0.0, 900.0),
                Instance("west", np.array([0.0, 1.0]), 0.0, 900.0),
            ]
        ),
        stability=StabilityGuard(
            V_fn=sre_error_budget_V(
                latency_target_ms=60.0,
                latency_scale_ms=20.0,
                error_rate_target=0.01,
                error_rate_scale=0.01,
            ),
            tolerance=1e-6,
            k_violations=2,
            label="replay_error_budget",
        ),
    )
    return stack, metrics


def _expected_kinds(row: dict) -> list[str]:
    if "expected_kinds" in row:
        return list(row["expected_kinds"])
    expected_kind = row.get("expected_kind")
    return [] if expected_kind is None else [expected_kind]


def _row_has_expected_event(row: dict) -> bool:
    return bool(_expected_kinds(row))


def _expected_kinds_visible(entry: dict, expected_kinds: list[str]) -> bool:
    observed = {event["kind"] for event in entry["runtime"]["events"]}
    return set(expected_kinds).issubset(observed)


def _recovery_diagnostics(rows: list[dict], trace: list[dict]) -> dict[str, float | None]:
    windows: list[tuple[int, int]] = []
    start: int | None = None
    for idx, row in enumerate(rows):
        if _row_has_expected_event(row) and start is None:
            start = idx
        elif not _row_has_expected_event(row) and start is not None:
            windows.append((start, idx - 1))
            start = None
    if start is not None:
        windows.append((start, len(rows) - 1))

    recovery_ticks: list[float] = []
    for _, end in windows:
        recovered_at = None
        for idx in range(end + 1, len(rows)):
            if _row_has_expected_event(rows[idx]):
                continue
            if not trace[idx]["runtime"]["events"]:
                recovered_at = idx
                break
        if recovered_at is None:
            recovery_ticks.append(float("inf"))
        else:
            recovery_ticks.append(float(recovered_at - end))

    finite = [tick for tick in recovery_ticks if np.isfinite(tick)]
    return {
        "recovery_window_count": float(len(windows)),
        "recovered_window_fraction": (
            float(len(finite) / len(windows)) if windows else 1.0
        ),
        "max_recovery_ticks": float(max(finite)) if finite else None,
    }


def _operator_action_diagnostics(rows: list[dict]) -> dict[str, object]:
    expected_rows = [row for row in rows if _row_has_expected_event(row)]
    annotated = [
        row
        for row in expected_rows
        if isinstance(row.get("operator_action"), str)
        and row["operator_action"].strip()
    ]
    actions_by_kind: dict[str, list[str]] = {}
    for row in annotated:
        if "expected_kinds" in row:
            continue
        kind = row["expected_kind"]
        actions_by_kind.setdefault(kind, [])
        action = row["operator_action"]
        if action not in actions_by_kind[kind]:
            actions_by_kind[kind].append(action)
    return {
        "operator_action_coverage": (
            float(len(annotated) / len(expected_rows)) if expected_rows else 1.0
        ),
        "operator_actions_by_kind": {
            kind: sorted(actions) for kind, actions in sorted(actions_by_kind.items())
        },
    }


def _multi_signal_window_diagnostics(
    rows: list[dict], trace: list[dict]
) -> dict[str, object]:
    grouped: dict[str, list[int]] = {}
    for idx, row in enumerate(rows):
        incident_id = row.get("incident_id")
        if incident_id and _row_has_expected_event(row):
            grouped.setdefault(incident_id, []).append(idx)

    multi_signal_windows = []
    actions_by_window: dict[str, list[str]] = {}
    for incident_id, indices in grouped.items():
        expected = set()
        observed = set()
        actions = set()
        for idx in indices:
            expected.update(_expected_kinds(rows[idx]))
            observed.update(event["kind"] for event in trace[idx]["runtime"]["events"])
            action = rows[idx].get("window_operator_action")
            if isinstance(action, str) and action.strip():
                actions.add(action)
        if len(expected) < 2:
            continue
        end = max(indices)
        recovered_at = None
        for idx in range(end + 1, len(rows)):
            if _row_has_expected_event(rows[idx]):
                continue
            if not trace[idx]["runtime"]["events"]:
                recovered_at = idx
                break
        multi_signal_windows.append(
            {
                "incident_id": incident_id,
                "length": len(indices),
                "covered": expected.issubset(observed),
                "recovery_ticks": (
                    float("inf") if recovered_at is None else float(recovered_at - end)
                ),
            }
        )
        if actions:
            actions_by_window[incident_id] = sorted(actions)

    finite_recovery = [
        window["recovery_ticks"]
        for window in multi_signal_windows
        if np.isfinite(window["recovery_ticks"])
    ]
    return {
        "multi_signal_window_count": len(multi_signal_windows),
        "max_incident_window_ticks": (
            max((window["length"] for window in multi_signal_windows), default=0)
        ),
        "multi_signal_window_coverage": (
            float(np.mean([window["covered"] for window in multi_signal_windows]))
            if multi_signal_windows
            else 1.0
        ),
        "multi_signal_window_recovered_fraction": (
            float(len(finite_recovery) / len(multi_signal_windows))
            if multi_signal_windows
            else 1.0
        ),
        "max_multi_signal_recovery_ticks": (
            float(max(finite_recovery)) if finite_recovery else None
        ),
        "operator_actions_by_window": actions_by_window,
    }


def main() -> dict:
    rows = _load_fixture()
    stack, metrics = _stack()
    current_replicas = 10
    visible_expected = []
    background_clean = []
    visible_stability = []

    for row in rows:
        if "replicas_max" in row:
            stack.autoscaler.replicas_max = int(row["replicas_max"])
        reading = None
        if not row.get("sensor_missing", False):
            reading = np.array(
                [row["rps"], row["latency_ms"], row["error_rate"]],
                dtype=float,
            )
        entry = stack.step(
            dt=5.0,
            sensor_readings=[(metrics, reading)],
            forecast_rps=float(row["forecast_rps"]),
            current_replicas=current_replicas,
            zone_target=np.asarray(row["zone_target"], dtype=float),
            nn_proposal=np.asarray(row["nn_proposal"], dtype=float),
        )
        current_replicas = entry["replicas_next"]
        expected_kinds = _expected_kinds(row)
        if not expected_kinds:
            background_clean.append(not entry["runtime"]["events"])
        else:
            visible = _expected_kinds_visible(entry, expected_kinds)
            visible_expected.append(visible)
            if "stability_violation" in expected_kinds:
                visible_stability.append(visible)

    expected_rows = [row for row in rows if _row_has_expected_event(row)]
    observed_expected_kinds = sorted(
        {kind for row in expected_rows for kind in _expected_kinds(row)}
    )
    event_count = sum(len(entry["runtime"]["events"]) for entry in stack.trace)
    recovery = _recovery_diagnostics(rows, stack.trace)
    operator_actions = _operator_action_diagnostics(rows)
    multi_signal = _multi_signal_window_diagnostics(rows, stack.trace)
    before = {
        "expected_event_visible_fraction": 0.0,
        "background_event_fraction": 0.0,
        "event_count_total": 0.0,
        "max_recovery_ticks": 0.0,
        "multi_signal_window_coverage": 0.0,
        "max_incident_window_ticks": 0.0,
    }
    after = {
        "expected_event_visible_fraction": float(np.mean(visible_expected)),
        "background_event_fraction": float(1.0 - np.mean(background_clean)),
        "event_count_total": float(event_count),
        "max_recovery_ticks": recovery["max_recovery_ticks"],
        "multi_signal_window_coverage": multi_signal["multi_signal_window_coverage"],
        "max_incident_window_ticks": float(multi_signal["max_incident_window_ticks"]),
    }
    diagnostics = {
        "evidence_label": "synthetic_replay_fixture",
        "fixture_path": FIXTURE.relative_to(Path(__file__).resolve().parents[1]).as_posix(),
        "replay_tick_count": len(rows),
        "expected_event_count": len(expected_rows),
        "observed_expected_kinds": observed_expected_kinds,
        "stability_event_visible_fraction": float(np.mean(visible_stability)),
        **recovery,
        **operator_actions,
        **multi_signal,
        **after,
    }
    banner = summary_banner("§12 SRE replay fixture", before, after)
    print(banner)
    return {
        "before": before,
        "after": after,
        "diagnostics": diagnostics,
        "trace": stack.trace,
        "banner": banner,
    }


if __name__ == "__main__":
    main()
