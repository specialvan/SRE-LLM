"""Run the canonical benchmark and write review artifacts.

Usage:

    python scripts/run_benchmark.py --out artifacts/benchmark-metrics.json

The JSON artifact stays out of git. The markdown log is intentionally
small and reviewable.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def build_command(args: argparse.Namespace) -> list[str]:
    return [
        sys.executable,
        "-m",
        "examples.compare_e2e_vs_structural",
        "--n",
        str(args.n),
        "--seed",
        str(args.seed),
        "--horizon",
        str(args.horizon),
        "--dt",
        str(args.dt),
        "--metrics-out",
        str(args.out_path),
    ]


def format_log_entry(payload: dict, *, timestamp: datetime | None = None) -> str:
    ts = timestamp or datetime.now(timezone.utc)
    e2e = payload["summaries"]["pure_e2e"]
    structural = payload["summaries"]["structural"]
    params = payload["params"]
    return (
        f"## {ts.isoformat(timespec='seconds')}\n\n"
        f"**自动采样**：`scripts/run_benchmark.py`，"
        f"`n={params['n']}`、`seed={params['seed']}`、"
        f"`horizon={params['horizon']}`、`dt={params['dt']}`。\n\n"
        "| 指标 | Pure E2E | Structural |\n"
        "| --- | ---: | ---: |\n"
        f"| `collision_rate` | {e2e['collision_rate']:.2%} | {structural['collision_rate']:.2%} |\n"
        f"| `worst_clearance_m` | {e2e['worst_clearance_m']:+.2f} m | {structural['worst_clearance_m']:+.2f} m |\n"
        f"| `planner_emergency_rate` | — | {structural['planner_emergency_rate']:.2%} |\n"
        f"| `planner_best_effort_rate` | — | {structural.get('planner_best_effort_rate', 0.0):.2%} |\n"
        f"| `cbf_fallback_rate` | — | {structural['cbf_fallback_rate']:.2%} |\n"
        f"| `mean_step_time_ms` | {e2e['mean_step_time_ms']:.2f} ms | {structural['mean_step_time_ms']:.2f} ms |\n"
        "\n"
        f"**Planner status**：`{structural['planner_status_counts']}`\n\n"
        f"**CBF status**：`{structural['cbf_status_counts']}`\n\n"
        "---\n\n"
    )


def insert_newest_first(log_path: Path, entry: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if not log_path.exists():
        log_path.write_text("# Benchmark Log\n\n" + entry, encoding="utf-8")
        return

    text = log_path.read_text(encoding="utf-8")
    marker = "---\n\n"
    idx = text.find(marker)
    if idx == -1:
        log_path.write_text(text.rstrip() + "\n\n" + entry, encoding="utf-8")
        return
    insert_at = idx + len(marker)
    log_path.write_text(text[:insert_at] + entry + text[insert_at:], encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--horizon", type=int, default=100)
    parser.add_argument("--dt", type=float, default=0.1)
    parser.add_argument("--out", type=Path, default=Path("artifacts/benchmark-metrics.json"))
    parser.add_argument("--log", type=Path, default=Path("docs/claude-review/08-benchmark-log.md"))
    args = parser.parse_args()
    args.out_path = args.out if args.out.is_absolute() else ROOT / args.out
    log_path = args.log if args.log.is_absolute() else ROOT / args.log

    args.out_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.check_call(build_command(args), cwd=ROOT)

    payload = json.loads(args.out_path.read_text(encoding="utf-8"))
    insert_newest_first(log_path, format_log_entry(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
