"""Contract test for §10 failure-trace study.

Keeps the "event-level evidence" promise honest:

- the scenario must emit at least one event from each injected window
- the resulting metrics must be non-trivial (not all zeros)
- all events must still honour the shared schema
"""

from __future__ import annotations

import numpy as np

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

    missing = any("missing_sensor" in {e["kind"] for e in evs}
                  for t, evs in zip(t_grid, event_lists)
                  if s10.WINDOW_MISSING[0] <= t <= s10.WINDOW_MISSING[1])
    bound = any("replica_bound_active" in {e["kind"] for e in evs}
                for t, evs in zip(t_grid, event_lists)
                if s10.WINDOW_BOUND[0] <= t <= s10.WINDOW_BOUND[1])
    unsafe = any("unsafe_proposal_projected" in {e["kind"] for e in evs}
                 for t, evs in zip(t_grid, event_lists)
                 if s10.WINDOW_UNSAFE[0] <= t <= s10.WINDOW_UNSAFE[1])

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
