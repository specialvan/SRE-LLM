# Runtime States

这份文档描述的是“运行中”的控制栈，而不是静态接口。

重点是三件事：

1. 每个模块在 tick 里会经历哪些状态。
2. 哪些事件会触发降级、冻结或切换。
3. 当多个模块一起工作时，状态如何传播。

---

## 1. Stack-Level State Machine

The stack can be understood as a small finite-state machine:

| State | Meaning | Typical trigger | Safe action |
|---|---|---|---|
| `INIT` | cold start, no credible estimate yet | process boot / first tick | use conservative defaults |
| `OBSERVING` | collecting sensor streams | normal tick entry | fuse available signals |
| `PLANNING` | computing next control step | fresh estimate available | run MPC / canary planner |
| `GUARDING` | projecting actions into feasible set | unsafe proposal detected | cone / box projection |
| `ALLOCATING` | splitting resources across instances / thrusters | target wrench or demand is known | bounded LS allocation |
| `EXECUTING` | dispatching the approved action | all local checks passed | apply first action only |
| `DEGRADED_OBSERVE` | some sensors are missing or stale | missing reading / large residual | freeze confidence growth |
| `DEGRADED_PLAN` | prediction is weak | horizon mismatch / model drift | shorten horizon, raise conservatism |
| `DEGRADED_ALLOCATE` | residual cannot be driven to zero | rank loss / box saturation | keep residual trace, do not fake exactness |
| `EMERGENCY_CUTOVER` | fast switch is required | incident / rollback / deadline breach | use bang-bang switcher |

Rule of thumb:

- soft optimizers may fail closed;
- hard guardrails should never disappear;
- emergency logic overrides everything else.

---

## 2. Module-Level State Machines

### 2.1 `PoolCapacityPlanner`

States:

- `relax`
- `keep_alive_floor`
- `clip`

Transitions:

- `relax -> keep_alive_floor` when forecast demand is below the minimum live pool but health probes still require warm connections.
- `relax -> clip` when forecast demand exceeds the hard pool cap.

Failure signal:

- positive `capacity_shortfall_rps`

Recovery:

- expose the shortfall and keep the pool at `max_capacity`; do not invent capacity above the configured bound

### 2.2 `SignalFusion`

States:

- `predict`
- `update`
- `skip_update`

Transitions:

- `predict -> update` when a sensor reading is available.
- `predict -> skip_update` when the sensor is missing.
- `update -> predict` on the next tick.

Failure signal:

- rising covariance trace
- inconsistent residuals across sensors

Recovery:

- keep the last credible posterior
- downweight noisy or missing streams

### 2.3 `CanaryScheduler`

States:

- `propose`
- `observe`
- `expand`
- `shrink`
- `freeze`

Transitions:

- `observe -> expand` when improvement ratio is strong.
- `observe -> shrink` when observed error burns budget.
- `observe -> freeze` when confidence collapses.

Failure signal:

- trust region oscillates too fast

Recovery:

- pin rollout and wait for more evidence

### 2.4 `TopologyState`

States:

- `repair_unit_norm`
- `integrate`

Transitions:

- `repair_unit_norm -> integrate` when an incoming quaternion is non-finite, near-zero, or visibly off the unit sphere.
- `integrate` on every normal topology tick.

Failure signal:

- repaired input quaternion before exp-map integration

Recovery:

- reset an invalid quaternion to identity or renormalize a drifting one before integration

### 2.5 `SLOGuardrail`

States:

- `candidate`
- `projected`
- `approved`

Transitions:

- `candidate -> projected` whenever the proposal is outside the feasible cone / ball.
- `projected -> approved` when the filtered action is safe.

Failure signal:

- proposal sits deep outside the cone, indicating upstream policy mismatch

Recovery:

- keep the projection, do not trust the raw proposal

### 2.6 `PredictiveAutoscaler`

States:

- `solve`
- `clip`
- `integerize`

Transitions:

- `solve -> clip` when the QP proposes a step beyond bounds.
- `clip -> integerize` when the step must become a whole replica count.

Failure signal:

- repeated clipping at the upper bound

Recovery:

- raise capacity cap or tune weights; do not invent fractional replicas

### 2.7 `WeightedLoadBalancer`

States:

- `solve_ls`
- `saturate`
- `report_residual`

Transitions:

- `solve_ls -> saturate` when bounds are active.
- `saturate -> report_residual` when the exact target is unattainable.

Failure signal:

- rank deficiency or persistent residual

Recovery:

- prefer bounded least squares over exact matching

### 2.8 `FastTrafficSwitcher`

States:

- `ramp_up`
- `switch_midpoint`
- `ramp_down`

Transitions:

- `ramp_up -> switch_midpoint -> ramp_down` on a minimum-time flip.

Failure signal:

- switch window exceeds incident deadline

Recovery:

- freeze the change or fall back to a simpler rollback path

---

## 3. State Propagation in the Stack

The stack is intentionally ordered so that safety is downstream of prediction:

1. observations become posterior state,
2. posterior state informs planning,
3. planning proposals are clipped by guardrails,
4. guardrails feed bounded allocation,
5. allocation is the last executable act.

This means:

- bad observations should degrade planning, not bypass safety;
- bad planning should degrade action quality, not bypass bounds;
- bad allocation should still report residuals, not fake correctness.

`SREControlStack.step()` now emits this runtime layer directly:

```python
entry["runtime"] = {
    "states": ["OBSERVING", "PLANNING", "GUARDING", "ALLOCATING", "EXECUTING"],
    "degraded": False,
    "events": [],
}
```

When a module degrades, the adapter should emit a local event first, and the stack should append the matching `DEGRADED_*` state while carrying that event upward:

```python
{
    "stage": "SignalFusion",
    "kind": "missing_sensor",
    "detail": "...",
    "safe_action": "...",
}
```

Current local event emitters:

| Adapter | Local field | Event kinds |
|---|---|---|
| `PoolCapacityPlanner.plan()` | `info["events"]` | `pool_capacity_clipped` |
| `SignalFusion.step()` | `trace["events"]` | `missing_sensor` |
| `CanaryScheduler.observe()` | `CanaryStep.events` | `rollout_rejected` |
| `TopologyState.step()` | `trace["events"]` | `topology_state_repaired` |
| `SLOGuardrail.audit()` | `audit["events"]` | `unsafe_proposal_projected` |
| `PredictiveAutoscaler.step()` | `last_trace["events"]` | `replica_bound_active` |
| `FastTrafficSwitcher.plan()` | `info["events"]` | `deadline_exceeded` |
| `WeightedLoadBalancer.allocate()` | `info["events"]` | `bounded_ls_residual` |

The exact schema and counter-examples are pinned in `docs/EVENT_SCHEMA.md`.
This is intentionally coarse. It is a review trace, not a full production incident timeline.
`starship/CatchController` stays outside this table because it is the physical layer primitive; SRE-facing residual events should be emitted by `WeightedLoadBalancer` or a future wrapper, not by importing the SRE event schema into `starship/`.

---

## 4. Degradation Matrix

| Failure source | Local symptom | Stack-level response |
|---|---|---|
| pool cap exceeded | positive `capacity_shortfall_rps` | hold `max_capacity`, surface capacity gap |
| missing sensor | `used=False` in trace | keep fused state, reduce confidence |
| invalid topology quaternion | `repair_unit_norm` | repair state before using topology distance / angle |
| model mismatch | repeated residuals | shorten horizon / freeze rollout |
| unsafe proposal | cone or magnitude violation | project before execution |
| rank loss | residual stays non-zero | keep bounded LS and report residual |
| incident deadline | switch time too long | enter emergency cutover |

---

## 5. Why this layer matters

Architecture tells you where things live.  
API contracts tell you what they are allowed to do.  
Runtime states tell you how they behave when the world is messy.

That last one is the part that makes the abstraction operational instead of decorative.
