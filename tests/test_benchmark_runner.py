"""Tests for benchmark artifact helpers."""

from datetime import datetime, timezone

from scripts.run_benchmark import format_log_entry, insert_newest_first


def _payload(n: int, emergency: float) -> dict:
    return {
        "params": {"n": n, "seed": 0, "horizon": 10, "dt": 0.1},
        "summaries": {
            "pure_e2e": {
                "collision_rate": 0.5,
                "worst_clearance_m": -0.2,
                "mean_step_time_ms": 0.1,
            },
            "structural": {
                "collision_rate": 0.0,
                "worst_clearance_m": 2.0,
                "planner_emergency_rate": emergency,
                "planner_best_effort_rate": 0.2,
                "cbf_fallback_rate": 0.05,
                "mean_step_time_ms": 1.0,
                "planner_status_counts": {"best_effort": 2},
                "cbf_status_counts": {"nom_ok": 8, "fallback_brake": 1},
            },
        },
    }


def test_format_log_entry_includes_recovery_metrics():
    entry = format_log_entry(
        _payload(n=2, emergency=0.1),
        timestamp=datetime(2026, 5, 12, tzinfo=timezone.utc),
    )

    assert "planner_emergency_rate" in entry
    assert "planner_best_effort_rate" in entry
    assert "cbf_fallback_rate" in entry
    assert "n=2" in entry


def test_insert_newest_first_preserves_benchmark_log_header(tmp_path):
    log = tmp_path / "benchmark-log.md"
    log.write_text("# Benchmark Log\n\n## 配置说明\n\n---\n\n## old\n", encoding="utf-8")

    insert_newest_first(log, "## new\n\n---\n\n")

    text = log.read_text(encoding="utf-8")
    assert text.index("## new") < text.index("## old")
    assert text.startswith("# Benchmark Log")
