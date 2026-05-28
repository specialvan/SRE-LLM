"""Contract test for §10 failure-trace study.

Keeps the "event-level evidence" promise honest:

- the scenario must emit at least one event from each injected window
- the resulting metrics must be non-trivial (not all zeros)
- all events must still honour the shared schema
"""

from __future__ import annotations

import json

import numpy as np
import pytest

import analysis.s10_failure_trace as s10
from sre_control.events import validate_event


def test_s10_fires_at_least_three_distinct_event_kinds():
    event_lists, _, _ = s10._run_scenario()
    all_kinds = {ev["kind"] for evs in event_lists for ev in evs}
    # Expect at least missing_sensor + replica_bound_active +
    # unsafe_proposal_projected (plus whatever ambient kinds may fire).
    assert len(all_kinds) >= 3, f"only saw kinds: {all_kinds}"


def test_s10_events_match_injected_windows():
    event_lists, _, _ = s10._run_scenario()
    t_grid = np.arange(0, s10.T_FINAL, s10.DT)

    missing = any(
        "missing_sensor" in {e["kind"] for e in evs}
        for t, evs in zip(t_grid, event_lists)
        if s10.WINDOW_MISSING[0] <= t <= s10.WINDOW_MISSING[1]
    )
    bound = any(
        "replica_bound_active" in {e["kind"] for e in evs}
        for t, evs in zip(t_grid, event_lists)
        if s10.WINDOW_BOUND[0] <= t <= s10.WINDOW_BOUND[1]
    )
    unsafe = any(
        "unsafe_proposal_projected" in {e["kind"] for e in evs}
        for t, evs in zip(t_grid, event_lists)
        if s10.WINDOW_UNSAFE[0] <= t <= s10.WINDOW_UNSAFE[1]
    )

    assert missing, "missing_sensor did not fire during its injection window"
    assert bound, "replica_bound_active did not fire during its injection window"
    assert unsafe, "unsafe_proposal_projected did not fire during its injection window"


def test_s10_every_event_follows_shared_schema():
    event_lists, _, _ = s10._run_scenario()
    for evs in event_lists:
        for ev in evs:
            assert validate_event(ev), f"invalid event payload: {ev}"


def test_s10_metrics_are_nontrivial():
    event_lists, _, _ = s10._run_scenario()
    metrics = s10._derive_metrics(event_lists)
    assert metrics["event_count_total"] > 0
    assert metrics["distinct_kinds"] >= 3
    assert metrics["degraded_tick_fraction"] > 0.0


def test_s10_empty_injection_set_uses_vacuous_visibility(monkeypatch):
    monkeypatch.setattr(s10, "INJECTION_WINDOWS", ())

    metrics = s10._derive_metrics([[], []])

    assert metrics["true_degraded_fraction"] == 0.0
    assert metrics["event_visible_fraction"] == 1.0
    assert metrics["background_event_fraction"] == 0.0
    assert metrics["injected_window_coverage"] == {}


def test_s10_uses_one_continuous_stack_instance(monkeypatch):
    calls = 0
    real_build_stack = s10._build_stack

    def wrapped_build_stack(*args, **kwargs):
        nonlocal calls
        calls += 1
        return real_build_stack(*args, **kwargs)

    monkeypatch.setattr(s10, "_build_stack", wrapped_build_stack)

    s10._run_scenario()

    assert calls == 1


def test_s10_replicas_trace_uses_stack_output_without_hidden_floor(monkeypatch):
    class FakeAutoscaler:
        replicas_max = 100

    class FakeStack:
        def __init__(self):
            self.autoscaler = FakeAutoscaler()

        def step(self, **kwargs):
            return {"replicas_next": 6, "runtime": {"events": []}}

    monkeypatch.setattr(s10, "T_FINAL", s10.DT)
    monkeypatch.setattr(s10, "_build_stack", lambda: (FakeStack(), object()))

    _event_lists, replicas, _latency = s10._run_scenario()

    assert replicas.tolist() == [6]


def test_s10_background_event_fraction_is_bounded():
    event_lists, _, _ = s10._run_scenario()
    metrics = s10._derive_metrics(event_lists)

    assert metrics["background_event_fraction"] < 0.20


def test_s10_degraded_tick_fraction_not_saturated():
    event_lists, _, _ = s10._run_scenario()
    metrics = s10._derive_metrics(event_lists)

    assert 0.0 < metrics["degraded_tick_fraction"] < 100.0


def test_s10_each_injected_window_has_kind_coverage():
    event_lists, _, _ = s10._run_scenario()
    metrics = s10._derive_metrics(event_lists)
    coverage = metrics["injected_window_coverage"]
    expected = {
        "missing_sensor": "missing_sensor",
        "replica_bound_active": "replica_bound_active",
        "unsafe_proposal_projected": "unsafe_proposal_projected",
    }

    assert set(expected).issubset(coverage)
    for window_name, expected_kind in expected.items():
        window = coverage[window_name]
        assert window["expected_kind"] == expected_kind
        assert window["event_visible_fraction"] > 0.0
        assert window["expected_kind_fraction"] > 0.0


def test_s10_replica_bound_window_has_full_expected_kind_coverage():
    event_lists, _, _ = s10._run_scenario()
    metrics = s10._derive_metrics(event_lists)

    bound_coverage = metrics["injected_window_coverage"]["replica_bound_active"]

    assert bound_coverage["expected_kind_fraction"] == 1.0


def test_s10_bound_events_stay_inside_injection_window():
    event_lists, _, _ = s10._run_scenario()
    t_grid = np.arange(0, s10.T_FINAL, s10.DT)
    outside_bound_ticks = [
        i
        for i, t in enumerate(t_grid)
        if not (s10.WINDOW_BOUND[0] <= t <= s10.WINDOW_BOUND[1])
    ]

    assert not any(
        "replica_bound_active" in {e["kind"] for e in event_lists[i]}
        for i in outside_bound_ticks
    )


def test_s10_full_trace_jsonl_contains_all_events(tmp_path, monkeypatch):
    monkeypatch.setattr(s10, "ARTIFACTS", tmp_path)

    result = s10.main()
    full_path = tmp_path / "s10_trace_full.jsonl"

    assert full_path.exists()
    lines = full_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == result["after"]["event_count_total"]
    assert all(json.loads(line)["kind"] for line in lines)


def test_s10_jsonl_artifacts_use_sorted_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(s10, "ARTIFACTS", tmp_path)

    s10.main()

    for artifact_name in ("s10_trace_full.jsonl", "s10_trace_sample.jsonl"):
        path = tmp_path / artifact_name
        first_line = path.read_text(encoding="utf-8").splitlines()[0]
        pairs = json.loads(first_line, object_pairs_hook=list)
        keys = [key for key, _value in pairs]

        assert keys == sorted(keys), artifact_name


def test_s10_jsonl_artifacts_reject_non_standard_float_events(tmp_path, monkeypatch):
    monkeypatch.setattr(
        s10,
        "_run_scenario",
        lambda: ([[{"kind": "missing_sensor", "value": float("nan")}]], np.array([1]), np.array([1.0])),
    )
    monkeypatch.setattr(
        s10,
        "_derive_metrics",
        lambda _events: {
            "event_count_total": 1,
            "distinct_kinds": 3,
            "degraded_tick_fraction": 100.0,
            "true_degraded_fraction": 1.0,
            "event_visible_fraction": 1.0,
            "background_event_fraction": 0.0,
            "injected_window_coverage": {},
            "mttr_seconds": 0.0,
            "_counts": [1],
            "_kinds_per_tick": [{"missing_sensor"}],
            "_all_kinds": ["missing_sensor"],
        },
    )

    with pytest.raises(ValueError, match="Out of range float"):
        s10.main(artifacts_dir=tmp_path)
