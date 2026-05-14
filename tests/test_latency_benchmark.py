"""Tests for the decision latency benchmark CLI."""
from __future__ import annotations

from bench import latency


def test_latency_benchmark_quick_can_enforce_budget(monkeypatch, capsys):
    calls: list[int] = []

    def fake_run(iterations: int) -> list[float]:
        calls.append(iterations)
        return [2.0, 2.0, 2.0]

    monkeypatch.setattr(latency, "_run", fake_run)

    exit_code = latency.main(["--quick", "--p99-ms", "1.0"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert calls == [200]
    assert "PERF REGRESSION" in captured.err
    assert '"p99_ms": 2.0' in captured.out


def test_latency_benchmark_quick_smoke_skips_budget_without_flag(monkeypatch, capsys):
    monkeypatch.setattr(latency, "_run", lambda _iterations: [999.0, 999.0, 999.0])

    exit_code = latency.main(["--quick"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "PERF REGRESSION" not in captured.err
    assert '"p99_ms": 999.0' in captured.out
