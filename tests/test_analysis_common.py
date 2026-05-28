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
