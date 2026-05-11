"""Runtime event schema shared by SRE control adapters."""

from __future__ import annotations

from typing import Mapping


REQUIRED_EVENT_FIELDS = ("stage", "kind", "detail", "safe_action")


EVENT_COUNTEREXAMPLES: dict[str, str] = {
    "missing_sensor": (
        "Do not interpret one missing low-value stream as a full incident; "
        "degrade confidence only when the missing stream matters for the control action."
    ),
    "rollout_rejected": (
        "Do not use canary rejection for one-shot migrations with no traffic-share ramp; "
        "there is no trust region to shrink."
    ),
    "unsafe_proposal_projected": (
        "Do not treat every projection as proof the upstream policy is bad; "
        "small projection distance can be ordinary numerical clipping."
    ),
    "replica_bound_active": (
        "Do not assume hitting replicas_max means the autoscaler failed; "
        "the real bottleneck may be quota, dependency capacity, or a non-CPU resource."
    ),
    "deadline_exceeded": (
        "Do not force a bang-bang switch through a missing health-check gate; "
        "a slower manual rollback can be safer than meeting the deadline."
    ),
    "bounded_ls_residual": (
        "Do not hide allocation residual by renormalising shares after the solve; "
        "that can violate per-instance capacity boxes."
    ),
    "pool_capacity_clipped": (
        "Do not treat max pool clipping as proof the planner is wrong; "
        "the real bottleneck may be quota, dependency capacity, or upstream demand shaping."
    ),
    "topology_state_repaired": (
        "Do not normalize arbitrary scalar metrics as if they lived on a manifold; "
        "repair only states that are explicitly quaternion topology states."
    ),
    "outlier_rejected": (
        "Do not raise the innovation-gate threshold just to silence this event; "
        "a persistent outlier usually means the measurement model h(x) or noise R "
        "is mis-specified, not that the sample is actually noise."
    ),
}


def make_event(stage: str, kind: str, detail: str,
               safe_action: str) -> dict[str, str]:
    """Create one JSON-serializable runtime event.

    The counter-example is kept in ``EVENT_COUNTEREXAMPLES`` rather than
    repeated in every event payload, so traces stay small while review
    docs still have a precise caveat for each event kind.
    """
    if kind not in EVENT_COUNTEREXAMPLES:
        raise ValueError(f"unknown runtime event kind: {kind}")
    return {
        "stage": stage,
        "kind": kind,
        "detail": detail,
        "safe_action": safe_action,
    }


def validate_event(event: Mapping[str, object]) -> bool:
    """Return True when an event follows the shared review schema."""
    return (
        all(field in event for field in REQUIRED_EVENT_FIELDS)
        and all(isinstance(event[field], str)
                and bool(event[field])
                for field in REQUIRED_EVENT_FIELDS)
        and event["kind"] in EVENT_COUNTEREXAMPLES
    )
