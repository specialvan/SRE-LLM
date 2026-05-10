"""Rollout modes for the self-iteration pipeline.

``ShadowMode`` governs how far the decision propagates out of the pipeline
process:

- ``off``        — normal operation, the decision is authoritative.
- ``shadow``     — the pipeline decides internally but **every** return value
  is rewritten to ``HOLD`` at the boundary. Traces and metrics are still
  emitted so dashboards can be compared against the live path.
- ``advisory``   — decisions are returned unchanged but are annotated with a
  ``shadow_from`` rationale so downstream automation knows not to act on
  them yet.

This mirrors the three-step maturity ramp: log → advise → enforce.
"""
from __future__ import annotations

import enum


class ShadowMode(str, enum.Enum):
    OFF = "off"
    SHADOW = "shadow"
    ADVISORY = "advisory"


def coerce(value: str | "ShadowMode" | None) -> ShadowMode:
    if value is None:
        return ShadowMode.OFF
    if isinstance(value, ShadowMode):
        return value
    try:
        return ShadowMode(value)
    except ValueError as exc:
        raise ValueError(f"invalid shadow mode: {value!r}") from exc
