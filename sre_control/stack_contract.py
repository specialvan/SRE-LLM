"""Machine-readable data contract for the research SRE stack."""

from __future__ import annotations


def stack_data_contract() -> dict[str, object]:
    """Return the stage boundary contract for ``SREControlStack.step``.

    This is review metadata for splitting or auditing the research loop. It is
    not a production distributed-control-plane contract.
    """
    return {
        "evidence_scope": "research_stack_data_contract",
        "production_claim": False,
        "orchestration_model": "single_process_research_loop",
        "event_stage_routes": {
            "SignalFusion": "observe",
            "StabilityGuard": "stability",
            "PredictiveAutoscaler": "plan",
            "CanaryScheduler": "plan",
            "SLOGuardrail": "guard",
            "WeightedLoadBalancer": "allocate",
        },
        "stages": [
            {
                "stage": "observe",
                "producer": "SignalFusion.step",
                "inputs": ["dt", "sensor_readings"],
                "outputs": ["state", "observed_rps", "runtime.events"],
                "event_kinds": [
                    "missing_sensor",
                    "outlier_rejected",
                    "adapter_exception",
                ],
            },
            {
                "stage": "stability",
                "producer": "StabilityGuard.step",
                "inputs": ["state", "tick_time"],
                "outputs": ["stability", "runtime.events"],
                "event_kinds": ["stability_violation", "adapter_exception"],
            },
            {
                "stage": "plan",
                "producer": "PredictiveAutoscaler.step/CanaryScheduler",
                "inputs": ["observed_rps", "forecast_rps", "current_replicas"],
                "outputs": ["replicas_next", "canary", "runtime.events"],
                "event_kinds": [
                    "replica_bound_active",
                    "rollout_rejected",
                    "adapter_exception",
                ],
            },
            {
                "stage": "guard",
                "producer": "SLOGuardrail.audit",
                "inputs": ["nn_proposal"],
                "outputs": ["guardrail", "safe_action", "runtime.events"],
                "event_kinds": [
                    "unsafe_proposal_projected",
                    "adapter_exception",
                ],
            },
            {
                "stage": "allocate",
                "producer": "WeightedLoadBalancer.allocate",
                "inputs": ["safe_action", "zone_target"],
                "outputs": ["alloc_shares", "alloc_info", "runtime.events"],
                "event_kinds": ["bounded_ls_residual", "adapter_exception"],
            },
            {
                "stage": "execute",
                "producer": "SREControlStack.step",
                "inputs": [
                    "state",
                    "stability",
                    "replicas_next",
                    "guardrail",
                    "alloc_info",
                ],
                "outputs": ["runtime.states", "runtime.events", "runtime.degraded"],
                "event_kinds": [],
            },
        ],
        "split_ready_boundaries": [
            "observe_to_plan",
            "plan_to_guard",
            "guard_to_allocate",
            "allocate_to_execute",
        ],
    }
