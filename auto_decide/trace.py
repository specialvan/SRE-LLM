"""Structured trace schema for planner outputs.

The planner writes one JSON object per control cycle. This module keeps
the trace shape stable and sanitizes values so the JSONL stream stays
strictly serializable.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any, Optional

from .types import Control, State

TRACE_SCHEMA_VERSION = "1.0"


def _jsonable(value: Any) -> Any:
    """Convert nested values into strict-JSON-friendly Python objects."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if hasattr(value, "item") and not isinstance(value, (list, tuple, dict)):
        try:
            return _jsonable(value.item())
        except Exception:
            pass
    if hasattr(value, "tolist") and not isinstance(value, (str, bytes, bytearray)):
        try:
            return _jsonable(value.tolist())
        except Exception:
            pass
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_jsonable(v) for v in value]
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


def _control_vec(u: Control) -> list[float]:
    return [float(u.steer), float(u.jerk)]


def build_trace_record(*,
                       step_index: Optional[int],
                       dt: float,
                       state: State,
                       next_state: State,
                       u_nn: Control,
                       u_safe: Control,
                       info: Mapping[str, Any],
                       min_dist: float) -> dict:
    """Build a single planner trace record.

    The record is designed for JSONL storage and automated review. The
    top-level shape is intentionally flat for the most frequently queried
    fields, while the nested ``cbf`` block preserves the full safety
    filter payload.
    """
    cbf_info = info.get("cbf", {}) if isinstance(info, Mapping) else {}
    step = None if step_index is None else int(step_index)
    t = None if step_index is None else float(step_index * dt)

    record = {
        "schema_version": TRACE_SCHEMA_VERSION,
        "step": step,
        "t": t,
        "dt": float(dt),
        "state": state.to_vec().tolist(),
        "next_state": next_state.to_vec().tolist(),
        "u_nn": _control_vec(u_nn),
        "u_safe": _control_vec(u_safe),
        "min_dist": float(min_dist),
        "V": _jsonable(info.get("V")),
        "dV_dt": _jsonable(info.get("dV_dt")),
        "status": info.get("status"),
        "cbf_status": cbf_info.get("status") if isinstance(cbf_info, Mapping) else None,
        "cbf_slack": _jsonable(
            cbf_info.get("slack") if isinstance(cbf_info, Mapping) else None
        ),
        "cbf_violations": _jsonable(
            cbf_info.get("violations", []) if isinstance(cbf_info, Mapping) else []
        ),
        "cbf": _jsonable(cbf_info),
    }
    return record
