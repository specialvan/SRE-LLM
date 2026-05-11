"""Tests for benchmark metrics payloads."""

import json

import pytest

from examples.compare_e2e_vs_structural import (
    Scenario,
    build_metrics_payload,
    run_benchmark,
    summarise_results,
)


def test_summarise_results_counts_statuses_and_guard_rates():
    summary = summarise_results(
        "structural",
        [
            {
                "collided": False,
                "min_clear": 2.0,
                "jerk_rms": 1.0,
                "elapsed_ms": 0.5,
                "steps": 10,
                "cbf_status_counts": {"nom_ok": 8, "fallback_brake": 2},
                "planner_status_counts": {"stable": 7, "emergency_brake": 1},
            },
            {
                "collided": True,
                "min_clear": -0.4,
                "jerk_rms": 3.0,
                "elapsed_ms": 0.7,
                "steps": 10,
                "cbf_status_counts": {"qp_ok": 10},
                "planner_status_counts": {"relaxed": 10},
            },
        ],
    )

    assert summary["collision_count"] == 1
    assert summary["collision_rate"] == 0.5
    assert summary["worst_clearance_m"] == -0.4
    assert summary["cbf_status_counts"]["fallback_brake"] == 2
    assert summary["planner_status_counts"]["emergency_brake"] == 1
    assert summary["guard_intervention_rate"] == 12 / 20
    assert summary["cbf_fallback_rate"] == 2 / 20
    assert summary["planner_emergency_rate"] == 1 / 20


def test_build_metrics_payload_is_json_safe():
    scenarios = [Scenario(mu=0.7, obstacle_x=30.0, obstacle_y=0.0)]
    e2e = [{
        "collided": True,
        "min_clear": -0.5,
        "jerk_rms": 4.0,
        "elapsed_ms": 0.1,
        "steps": 5,
        "cbf_status_counts": {},
        "planner_status_counts": {},
    }]
    structural = [{
        "collided": False,
        "min_clear": 1.5,
        "jerk_rms": 2.0,
        "elapsed_ms": 1.0,
        "steps": 5,
        "cbf_status_counts": {"qp_ok": 5},
        "planner_status_counts": {"stable": 5},
    }]

    payload = build_metrics_payload(
        scenarios=scenarios,
        e2e_results=e2e,
        structural_results=structural,
        seed=42,
        horizon=5,
        dt=0.1,
    )

    assert payload["schema_version"] == "benchmark.metrics.v1"
    assert payload["deltas"]["collision_rate_reduction"] == 1.0
    assert payload["deltas"]["avg_clearance_gain_m"] == 2.0
    json.dumps(payload, allow_nan=False)


@pytest.mark.xfail(
    strict=True,
    reason=(
        "AI-01 + AI-02: current GradientPolicy is not barrier-aware yet. "
        "Remove this xfail when PredictiveBrakePolicy makes the SLO pass."
    ),
)
def test_structural_pipeline_respects_availability_budget():
    """Demo SLO gate for structural benchmark availability.

    This is intentionally xfail until AI-02 upgrades the nominal policy.
    Do not make it pass by loosening CBF/game/Lyapunov hard constraints.
    """
    payload = run_benchmark(n=20, seed=0, horizon=100, dt=0.1)
    structural = payload["summaries"]["structural"]

    assert structural["collision_rate"] == 0.0, (
        f"collision_rate must be 0, got {structural['collision_rate']}"
    )
    assert structural["planner_emergency_rate"] <= 0.10, (
        "planner_emergency_rate must be <= 10% in demo benchmark, "
        f"got {structural['planner_emergency_rate']:.2%}. "
        "Fix by AI-02 nominal-policy upgrade, not by loosening CBF."
    )
    assert structural["cbf_fallback_rate"] <= 0.10, (
        "cbf_fallback_rate must be <= 10% in demo benchmark, "
        f"got {structural['cbf_fallback_rate']:.2%}."
    )
