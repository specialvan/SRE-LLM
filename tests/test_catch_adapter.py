from __future__ import annotations

import json

import numpy as np

from sre_control import CatchLoadAdapter, Instance


def _adapter() -> CatchLoadAdapter:
    return CatchLoadAdapter(
        instances=[
            Instance("east-a", np.array([1.0, 0.0]), rps_min=0.0, rps_max=120.0),
            Instance("east-b", np.array([1.0, 0.0]), rps_min=0.0, rps_max=120.0),
            Instance("west-a", np.array([0.0, 1.0]), rps_min=0.0, rps_max=80.0),
        ]
    )


def test_catch_load_adapter_reports_bounded_residual_without_hiding_it():
    adapter = _adapter()

    trace = adapter.allocate(
        request_demand=400.0,
        placement_target=np.array([260.0, 140.0]),
    )

    assert trace["source"] == "sre_wrapper_for_catch_allocation"
    assert trace["request_demand"] == 400.0
    assert sum(trace["shares"]) <= 320.0 + 1e-6
    assert trace["rps_residual"] >= 80.0 - 1e-6
    assert trace["demand_satisfied"] is False
    assert trace["rps_residual_fraction"] >= (80.0 / 400.0) - 1e-6
    assert "report_residual" in trace["local_states"]
    assert any(trace["saturation"])
    event = next(event for event in trace["events"] if event["kind"] == "bounded_ls_residual")
    assert event["demand_satisfied"] is False
    assert event["rps_residual_fraction"] == trace["rps_residual_fraction"]
    json.dumps(trace)


def test_catch_load_adapter_keeps_exact_solution_quiet_when_feasible():
    adapter = _adapter()

    trace = adapter.allocate(
        request_demand=180.0,
        placement_target=np.array([120.0, 60.0]),
    )

    assert trace["rps_residual"] < 1e-6
    assert max(trace["zone_residual"]) < 1e-6
    assert trace["events"] == []
    assert trace["local_states"] == ["solve_ls", "sre_catch_wrapper"]
