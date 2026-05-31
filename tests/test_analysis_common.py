from __future__ import annotations

from analysis._common import summary_banner


def test_summary_banner_marks_zero_baseline_ratio_as_undefined() -> None:
    banner = summary_banner(
        "demo",
        {"event_count_total": 0.0, "bounded_error": 4.0},
        {"event_count_total": 11.0, "bounded_error": 2.0},
    )

    assert "event_count_total" in banner
    assert "ratio=undefined" in banner
    assert "inf" not in banner.lower()
    assert "(x0.5)" in banner


def test_summary_banner_omits_wall_clock_ms_metrics_for_stable_artifacts() -> None:
    banner = summary_banner(
        "demo",
        {"solve_ms": 1.25, "pos_err": 4.0},
        {"solve_ms": 9.5, "pos_err": 2.0},
    )

    assert "pos_err" in banner
    assert "solve_ms" not in banner
