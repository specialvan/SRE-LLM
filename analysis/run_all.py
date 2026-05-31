"""Run every before/after analysis study in sequence.

Each module returns a ``{before, after, banner}`` dict. We concatenate
all banners into a single report and stash them in ``artifacts/``.
"""

from __future__ import annotations

import importlib
import inspect
import sys
import time
from pathlib import Path
from collections.abc import Sequence

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
    "analysis.s10_failure_trace",
    "analysis.s11_catch_sre_wrapper",
    "analysis.s12_sre_replay",
]


def main(
    studies: Sequence[str] | None = None,
    artifacts_dir: Path | None = None,
) -> None:
    banners = []
    summary_banners = []
    failures = []
    total_start = time.time()
    selected_studies = list(STUDIES if studies is None else studies)
    for name in selected_studies:
        print(f"\n---- running {name} ----")
        t0 = time.time()
        try:
            mod = importlib.import_module(name)
            main_func = mod.main
            signature = inspect.signature(main_func)
            if artifacts_dir is not None and "artifacts_dir" in signature.parameters:
                result = main_func(artifacts_dir=artifacts_dir)
            else:
                result = main_func()
        except Exception as exc:
            took = time.time() - t0
            failure = f"FAILED {name}: {type(exc).__name__}: {exc}"
            print(failure, file=sys.stderr)
            banners.append(f"{failure}\n    (elapsed {took:.2f}s)")
            summary_banners.append(failure)
            failures.append(failure)
            continue
        took = time.time() - t0
        banners.append(f"{result['banner']}\n    (elapsed {took:.2f}s)")
        summary_banners.append(result["banner"])
    total = time.time() - total_start
    print("\n\n========= FULL REPORT =========")
    for b in banners:
        print(b)
        print()
    if failures:
        print(
            f"{len(failures)} of {len(selected_studies)} studies failed in "
            f"{total:.2f}s. Artifacts in analysis/artifacts/.",
            file=sys.stderr,
        )
    else:
        print(
            f"All {len(selected_studies)} studies finished in {total:.2f}s. "
            "Artifacts in analysis/artifacts/."
        )

    out_dir = Path(__file__).parent / "artifacts" if artifacts_dir is None else artifacts_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "SUMMARY.txt"
    out.write_text("\n\n".join(summary_banners), encoding="utf-8")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
