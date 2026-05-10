"""Shared helpers for the before/after analysis studies."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

import numpy as np

try:
    import matplotlib
    matplotlib.use("Agg")                # safe for CI / headless runs
    import matplotlib.pyplot as plt
    HAS_MPL = True
except Exception:                        # pragma: no cover
    HAS_MPL = False


ARTIFACTS = Path(__file__).resolve().parent / "artifacts"
ARTIFACTS.mkdir(exist_ok=True)


def save_fig(fig, name: str) -> Path:
    path = ARTIFACTS / f"{name}.png"
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    return path


def save_csv(rows: Iterable[Dict[str, Any]], name: str) -> Path:
    """Save a list of dict rows to CSV without pulling pandas as a dep."""
    rows = list(rows)
    if not rows:
        return ARTIFACTS / f"{name}.csv"
    keys = list(rows[0].keys())
    path = ARTIFACTS / f"{name}.csv"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(",".join(keys) + "\n")
        for r in rows:
            fh.write(",".join(str(r[k]) for k in keys) + "\n")
    return path


def summary_banner(title: str, before: Dict[str, Any],
                   after: Dict[str, Any]) -> str:
    keys = set(before.keys()) | set(after.keys())
    lines = [f"=== {title} ==="]
    for k in sorted(keys):
        b = before.get(k, "-")
        a = after.get(k, "-")
        if isinstance(b, float) and isinstance(a, float):
            try:
                ratio = a / b if abs(b) > 1e-12 else float("inf")
                lines.append(f"  {k:24s}  before={b:.4g}  after={a:.4g}  (×{ratio:.3g})")
                continue
            except Exception:
                pass
        lines.append(f"  {k:24s}  before={b}  after={a}")
    return "\n".join(lines)
