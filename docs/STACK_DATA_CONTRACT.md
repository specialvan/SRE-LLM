# SRE Stack Data Contract

`sre_control.stack_data_contract()` exports a machine-readable boundary map for
`SREControlStack.step()`. It exists so reviewers can see the stage interfaces
that would need to become service or queue contracts if the research stack were
split later.

This is research metadata, not a production distributed-control-plane contract.

## Contract Shape

Required top-level fields:

| Field | Meaning |
|---|---|
| `evidence_scope` | Must be `research_stack_data_contract`. |
| `production_claim` | Must be `false`. |
| `orchestration_model` | Current value is `single_process_research_loop`. |
| `event_stage_routes` | String-to-string map from runtime event `stage` prefixes to declared logical contract stages. |
| `stages` | Ordered stage boundary object entries. |
| `split_ready_boundaries` | Named seams between stages for future split-out work; must be the current closed set documented below. |

Each stage entry must be an object containing:

| Field | Meaning |
|---|---|
| `stage` | Stable stage name. |
| `producer` | Current Python producer for the stage payload; must be a string. |
| `inputs` | Data the stage consumes; must be a list of strings. |
| `outputs` | Data the stage emits; must be a list of strings. |
| `event_kinds` | Runtime event kinds the stage may emit directly. Values must exist in `sre_control.events.EVENT_COUNTEREXAMPLES`. |

Current stage order:

1. `observe`
2. `stability`
3. `plan`
4. `guard`
5. `allocate`
6. `execute`

Current split-ready boundaries:

1. `observe_to_plan`
2. `plan_to_guard`
3. `guard_to_allocate`
4. `allocate_to_execute`

## Input Constraints

`SREControlStack.step(dt=...)` treats `dt` as the elapsed seconds for one
control tick. The stack rejects non-numeric, boolean, non-finite, zero, and
negative `dt` values with `AdapterInputError` before invoking any adapter, so a
bad tick interval cannot mutate EKF state, trace history, tick index, or
cumulative elapsed time.

## Action And Placement Semantics

The `guard` stage emits `safe_action` as a guarded direction vector. The
`allocate` stage interprets `np.linalg.norm(safe_action)` as the scalar
`rps_demand` magnitude and receives placement separately through `zone_target`.
The component sum of `safe_action` is not a placement or demand contract in the
current stack. Future changes to this convention must update the stack code,
contract tests, and Section 10 evidence expectations together.

Current direct event-kind bindings:

| Stage | Event kinds |
|---|---|
| `observe` | `missing_sensor`, `outlier_rejected`, `adapter_exception` |
| `stability` | `stability_violation`, `adapter_exception` |
| `plan` | `replica_bound_active`, `rollout_rejected`, `adapter_exception` |
| `guard` | `unsafe_proposal_projected`, `adapter_exception` |
| `allocate` | `bounded_ls_residual`, `adapter_exception` |
| `execute` | none; aggregates `runtime.events` emitted by earlier stages |

Runtime event `stage` labels can include suffixes such as
`StabilityGuard/replay_error_budget`. The route key is the prefix before `/`.
Current routes:

| Runtime stage prefix | Contract stage |
|---|---|
| `SignalFusion` | `observe` |
| `StabilityGuard` | `stability` |
| `PredictiveAutoscaler` | `plan` |
| `CanaryScheduler` | `plan` |
| `SLOGuardrail` | `guard` |
| `WeightedLoadBalancer` | `allocate` |

## Test Coverage

`tests/test_contracts.py::test_sre_stack_data_contract_exports_stage_boundaries`
checks that the contract is JSON-serializable, keeps the non-production scope,
exposes the current stage boundaries, and binds every stage event kind to the
runtime event registry. `analysis.evidence_report` also rejects stack-contract
artifacts that contain malformed stage entries, malformed stage interface
fields, missing or unexpected split-ready boundaries, malformed event-stage
routes, missing or unexpected event-stage route keys, unknown stage event
kinds, or disallow an event observed in generated trace artifacts.
