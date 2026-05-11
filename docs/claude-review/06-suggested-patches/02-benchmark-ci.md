# Patch 02 · Benchmark 作为 CI Artifact

- **Action item**：[AI-14](../05-action-items.md#ai-14)
- **Target**：每次 CI 都跑一次 benchmark，产物 `artifacts/benchmark-metrics.json` 保存，同时追加到 `docs/claude-review/08-benchmark-log.md`。

## 背景

单次 benchmark 无法反映趋势。没有历史基线的话，Codex 下一轮看不见"上一轮的结果"。这个 patch 把 benchmark 结果**版本化**。

## 实现步骤

### 1 · 新建 `scripts/run_benchmark.py`

```python
"""Run the benchmark and write artifacts.

Usage (also used by CI):

    python scripts/run_benchmark.py --out artifacts/benchmark-metrics.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path,
                        default=Path("artifacts/benchmark-metrics.json"))
    parser.add_argument("--log", type=Path,
                        default=Path("docs/claude-review/08-benchmark-log.md"))
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, "-m", "examples.compare_e2e_vs_structural",
        "--n", str(args.n), "--seed", str(args.seed),
        "--metrics-out", str(args.out),
    ]
    subprocess.check_call(cmd)

    payload = json.loads(args.out.read_text(encoding="utf-8"))
    append_log(args.log, payload)
    return 0


def append_log(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = f"\n## {datetime.utcnow().isoformat(timespec='seconds')}Z\n"
    e2e = payload["summaries"]["pure_e2e"]
    st = payload["summaries"]["structural"]
    line = (
        f"- scenarios: {payload['params']['n']} seed: {payload['params']['seed']}\n"
        f"- e2e collision_rate: {e2e['collision_rate']:.2%}\n"
        f"- structural collision_rate: {st['collision_rate']:.2%}\n"
        f"- structural emergency_rate: {st['planner_emergency_rate']:.2%}\n"
        f"- structural cbf_fallback_rate: {st['cbf_fallback_rate']:.2%}\n"
        f"- structural mean_step_time_ms: {st['mean_step_time_ms']:.2f}\n"
    )
    with path.open("a", encoding="utf-8") as f:
        f.write(header)
        f.write(line)


if __name__ == "__main__":
    raise SystemExit(main())
```

### 2 · 初始化 benchmark log

新建 `docs/claude-review/08-benchmark-log.md`：

```markdown
# Benchmark Log

> 每次 `scripts/run_benchmark.py` 运行会追加一段。
> 阅读顺序：自底向上看最新。

<!-- scripts/run_benchmark.py 会在此追加 -->
```

### 3 · 在 `.gitignore` 加 `artifacts/` 或决定入仓

推荐：`artifacts/` 加到 `.gitignore`（不入仓 JSON），benchmark-log.md 入仓。这样"趋势可追溯"但"每次 JSON 不污染 git history"。

```gitignore
artifacts/
```

### 4 · 如果用 GitHub Actions（可选）

`.github/workflows/benchmark.yml`：

```yaml
name: Benchmark
on:
  pull_request:
    paths:
      - 'auto_decide/**'
      - 'examples/**'
      - 'tests/**'
jobs:
  bench:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r requirements.txt
      - run: python scripts/run_benchmark.py --n 50 --seed 0
      - uses: actions/upload-artifact@v4
        with:
          name: benchmark-metrics
          path: artifacts/benchmark-metrics.json
```

## 验收

- `python scripts/run_benchmark.py` 本地能跑；
- 产出 `artifacts/benchmark-metrics.json`；
- `docs/claude-review/08-benchmark-log.md` 新增一段带时间戳的摘要；
- CI artifact 可下载（若启用 CI）。
