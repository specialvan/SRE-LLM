"""Runtime event schema shared by SRE control adapters."""

from __future__ import annotations

from typing import Callable, Mapping


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
    "stability_violation": (
        "Do not treat Lyapunov red-lines as ordinary alert noise; a sustained "
        "stability violation means the control objective is moving in the wrong "
        "direction and needs explicit operator review."
    ),
    "adapter_exception": (
        "Do not swallow programmer bugs as recoverable adapter exceptions; only "
        "control-domain failures with validated fallbacks should use this event."
    ),
}


def _is_bool(value: object) -> bool:
    return isinstance(value, bool)


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_number_or_none(value: object) -> bool:
    return value is None or _is_number(value)


def _is_number_list(value: object) -> bool:
    return (
        isinstance(value, list)
        and all(_is_number(item) for item in value)
    )


def _is_nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value)


EVENT_FIELD_SCHEMA: dict[str, dict[str, Callable[[object], bool]]] = {
    "missing_sensor": {
        "signal": _is_nonempty_string,
    },
    "rollout_rejected": {
        "observed_error_rate": _is_number,
        "slo_error_budget": _is_number,
        "trust_region": _is_number,
    },
    "unsafe_proposal_projected": {
        "cone_violated_before": _is_bool,
        "magnitude_violated_before": _is_bool,
        "projection_distance": _is_number,
    },
    "replica_bound_active": {
        "next_replicas": _is_number,
        "replicas_min": _is_number,
        "replicas_max": _is_number,
    },
    "deadline_exceeded": {
        "minimum_time_seconds": _is_number,
        "deadline_seconds": _is_number,
    },
    "bounded_ls_residual": {
        "rps_residual": _is_number,
        "rps_residual_fraction": _is_number,
        "zone_residual": _is_number_list,
        "demand_satisfied": _is_bool,
    },
    "pool_capacity_clipped": {
        "clipped_slots": _is_number,
        "capacity_shortfall_rps": _is_number,
        "max_capacity": _is_number,
    },
    "topology_state_repaired": {
        "input_norm_valid": _is_bool,
        "quaternion_norm": _is_number_or_none,
        "repair_action": _is_nonempty_string,
    },
    "outlier_rejected": {
        "signal": _is_nonempty_string,
        "innovation_mahalanobis": _is_number,
        "threshold_used": _is_number_or_none,
        "consecutive_rejections": _is_number,
    },
    "stability_violation": {
        "label": _is_nonempty_string,
        "V": _is_number,
        "dV_dt": _is_number_or_none,
        "consecutive_violations": _is_number,
        "tolerance": _is_number,
    },
    "adapter_exception": {
        "exception_type": _is_nonempty_string,
        "cause_type": _is_nonempty_string,
        "adapter_family": _is_nonempty_string,
        "fault_family": _is_nonempty_string,
        "fallback_action": _is_nonempty_string,
        "fallback_mode": _is_nonempty_string,
        "recoverable": _is_bool,
    },
}


def make_event(
    stage: str, kind: str, detail: str, safe_action: str, **fields: object
) -> dict[str, object]:
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
        **fields,
    }


def validate_event(event: Mapping[str, object]) -> bool:
    """Return True when an event follows the shared review schema."""
    kind = event.get("kind")
    base_valid = (
        all(field in event for field in REQUIRED_EVENT_FIELDS)
        and all(
            isinstance(event[field], str) and bool(event[field])
            for field in REQUIRED_EVENT_FIELDS
        )
        and kind in EVENT_COUNTEREXAMPLES
    )
    if not base_valid:
        return False
    kind_schema = EVENT_FIELD_SCHEMA[kind]
    allowed_fields = set(REQUIRED_EVENT_FIELDS) | set(kind_schema)
    if set(event) != allowed_fields:
        return False
    return all(
        field in event and validator(event.get(field))
        for field, validator in kind_schema.items()
    )
