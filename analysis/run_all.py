"""Run every before/after analysis study in sequence.

Each module returns a ``{before, after, banner}`` dict. We concatenate
all banners into a single report and stash them in ``artifacts/``.
"""

from __future__ import annotations

import importlib
import time
from pathlib import Path

STUDIES = [
    "analysis.s01_lossless_convex",
    "analysis.s02_scp",
    "analysis.s03_rigid_body",
    "analysis.s04_thrust_cone",
    "analysis.s05_ekf",
    "analysis.s06_mpc",
    "analysis.s07_flip_maneuver",
    "analysis.s08_catch_allocation",
    "analysis.s09_sre_stack",
]


def main() -> None:
    banners = []
    total_start = time.time()
    for name in STUDIES:
        print(f"\n---- running {name} ----")
        t0 = time.time()
        mod = importlib.import_module(name)
        result = mod.main()
        took = time.time() - t0
        banners.append(f"{result['banner']}\n    (elapsed {took:.2f}s)")
    total = time.time() - total_start
    print("\n\n========= FULL REPORT =========")
    for b in banners:
        print(b)
        print()
    print(f"All {len(STUDIES)} studies finished in {total:.2f}s. Artifacts in analysis/artifacts/.")

    out = Path(__file__).parent / "artifacts" / "SUMMARY.txt"
    out.write_text("\n\n".join(banners), encoding="utf-8")


if __name__ == "__main__":
    main()
