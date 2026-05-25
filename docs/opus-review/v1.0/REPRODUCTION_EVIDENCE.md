# Opus 深度评审 · v1.0 · 隐患复现实证

本文档把 `LINE_LEVEL_FINDINGS.md` 中 7 项最关键的发现用**可粘贴运行**的 Python 片段复现，把"理论分析"坐实为"实测证据"。每条都附完整命令、实测输出、期望分析。

环境：`python` 在 `D:\workspace\SRE-LLM\spacex`、HEAD=`8d8e064`。

---

## F01 实证 · FastTrafficSwitcher 在 `safety_margin=1.2` 时终点超调 44%

```bash
python -c "
from sre_control import FastTrafficSwitcher
sw = FastTrafficSwitcher(rate_max=0.4, safety_margin=1.2)
t, share, info = sw.plan(share_from=0.0, share_to=0.5, dt=0.05)
print(f'target=0.5 final_share={share[-1]:.4f} info.final_share={info[\"final_share\"]:.4f}')
"
```

**实测输出**：
```
target=0.5 final_share=0.7200 info.final_share=0.7200
```

**分析**：理论预测 `safety_margin² × dx = 1.44 × 0.5 = 0.72`，实测精确等于 0.72。
**结论**：H 级 bug 坐实。fix 前不要把 `safety_margin` 暴露成可调参数，或在 `__post_init__` 拒绝 `!= 1.0`。

---

## F02 实证 · WeightedLoadBalancer 在不可行 bounds 直接抛 ValueError

```bash
python -c "
from sre_control import WeightedLoadBalancer, Instance
import numpy as np
balancer = WeightedLoadBalancer(instances=[
    Instance('a', np.array([1.0]), rps_min=100.0, rps_max=50.0),
])
try:
    shares, info = balancer.allocate(rps_demand=10.0, zone_target=[10.0])
    print(f'returned: shares={shares}')
except Exception as e:
    print(f'caught {type(e).__name__}: {e}')
"
```

**实测输出**：
```
caught ValueError: Each lower bound must be strictly less than each upper bound.
```

**分析**：`scipy.optimize.lsq_linear` 在 `lb > ub` 时直接抛 `ValueError`。这条异常**不是 `RecoverableControlError` 子类**，所以 `SREControlStack.step()` 的 `except RecoverableControlError` **接不住**，会冒泡到调用方，整个 tick 崩溃 — **违反 I-5 不变式**。
**结论**：H 级，破坏不变式。必修。

---

## F03 实证 · EKF.update 在 `S` 奇异且无 gate 时崩溃

```bash
python -c "
import numpy as np
from starship.ekf import EKF
ekf = EKF(
    x=np.array([0.0, 0.0]),
    P=np.eye(2),
    process_noise=np.zeros((2,2)),
    f=lambda x,u,dt: x,
    F_jac=lambda x,u,dt: np.eye(2),
)
ekf.predict(None, 1.0)
try:
    ekf.update(
        z=np.array([1.0]),
        h=lambda x: np.array([0.0]),
        H=lambda x: np.zeros((1, 2)),
        R=np.zeros((1, 1)),
    )
    print('update returned without raising')
except Exception as e:
    print(f'caught {type(e).__name__}: {e}')
"
```

**实测输出**：
```
caught LinAlgError: Singular matrix
```

**分析**：第一次 `solve(S, y)`（L84）被 try/except 接住，`d_mahal=inf`；但因为 `gate_threshold=None`（默认值），代码继续往下，**第二次 `solve(S.T, ...)`（L93）再次抛同样异常但无保护**。
**结论**：H 级，调用方崩溃。必修。

---

## F04 实证 · `adapter_family` 与 `event_stage_routes` 给 StabilityGuard 不同分类

```bash
python -c "
from sre_control import (RecoverableControlError, SignalFusion, StabilityGuard, SREControlStack,
                          PredictiveAutoscaler, SLOGuardrail, WeightedLoadBalancer, Instance, Signal,
                          stack_data_contract)
import numpy as np

contract = stack_data_contract()
print('event_stage_routes:')
print(f'  StabilityGuard -> {contract[\"event_stage_routes\"][\"StabilityGuard\"]}')
print(f'  CanaryScheduler -> {contract[\"event_stage_routes\"][\"CanaryScheduler\"]}')

class _RecoverableStability(StabilityGuard):
    def step(self, x, t):
        raise RecoverableControlError('test')

fusion = SignalFusion(x0=np.array([100.0,10.0,0.01]), P0=np.eye(3),
                      Q=np.eye(3)*0.1, x_ref=np.array([100.0,10.0,0.01]), theta=0.1)
metrics = Signal(name='m', h=lambda x: x[:2],
                 H=lambda x: np.array([[1,0,0],[0,1,0]]), R=np.eye(2))
stack = SREControlStack(
    fusion=fusion,
    autoscaler=PredictiveAutoscaler(per_replica_rps=100, replicas_min=2, replicas_max=10, max_step=2, dt=1.0, horizon=4),
    guardrail=SLOGuardrail(nominal_direction=np.array([1.0,0,0]), theta_max_deg=20.0, magnitude_cap=1000.0),
    balancer=WeightedLoadBalancer(instances=[Instance('a', np.array([1.0]), rps_min=0, rps_max=100)]),
    stability=_RecoverableStability(V_fn=lambda x: float(x[0]), tolerance=1e-3, k_violations=1),
)
entry = stack.step(dt=1.0, sensor_readings=[(metrics, np.array([100.0, 10.0]))],
                    forecast_rps=100.0, current_replicas=4,
                    zone_target=np.array([100.0]), nn_proposal=np.array([100.0, 0, 0]))
ev = next(e for e in entry['runtime']['events'] if e['stage'] == 'StabilityGuard')
print(f'adapter_family in emitted event:')
print(f'  StabilityGuard -> {ev[\"adapter_family\"]}')
print(f'DISCREPANCY: contract says \"stability\", event says \"{ev[\"adapter_family\"]}\"')
"
```

**实测输出**：
```
event_stage_routes:
  StabilityGuard -> stability
  CanaryScheduler -> plan
adapter_family in emitted event:
  StabilityGuard -> plan
DISCREPANCY: contract says "stability", event says "plan"
```

**分析**：同一个 adapter (StabilityGuard) 在 trace 里 `adapter_family="plan"`，在 contract 路由表里被分到 `"stability"` stage。下游 dashboard 按任一一种分类都会**漏掉**另一种语义下的事件。
**结论**：H 级，metadata cross-consistency 失守。修法：用 `event_stage_routes` 作为单一信息源生成 `_adapter_family`。

---

## F05 实证 · L2 范数与逐分量绝对值之和的差距

```bash
python -c "
import numpy as np
safe_action = np.array([600.0, 800.0])
L2 = float(np.linalg.norm(safe_action))
total = float(np.sum(np.abs(safe_action)))
print(f'safe_action={safe_action} L2={L2} sum(|x|)={total}')
print(f'delta={total - L2:.2f} ({(total - L2)/total*100:.1f}%)')
"
```

**实测输出**：
```
safe_action=[600. 800.] L2=1000.0 sum(|x|)=1400.0
delta=400.00 (28.6%)
```

**分析**：在 east/west 分配场景下，L2 范数 (1000) 与实际 RPS 总量 (1400) 差 28.6%。当前 `stack.py:300` 用 L2 范数把"动作向量"折成 `rps_demand` 喂给 bounded LS，意味着 **下游容量预算被低估**。
**结论**：H 级建模约定不明。需要明确文档约定，或改用 sum。

---

## F08 实证 · Canary 在连续拒绝时模型永远不学习

```bash
python -c "
from sre_control import CanaryScheduler
sched = CanaryScheduler(slo_error_budget=0.01)
for share in [0.05, 0.10, 0.15]:
    step = sched.observe(current_share=share - 0.05, proposed_share=share, observed_error_rate=0.03)
    print(f'share={share:.2f} accepted={step.accepted} _b_est={sched._b_est:.4f} trust={sched._eta:.4f}')
"
```

**实测输出**：
```
share=0.05 accepted=False _b_est=0.0000 trust=0.0250
share=0.10 accepted=False _b_est=0.0000 trust=0.0125
share=0.15 accepted=False _b_est=0.0000 trust=0.0063
```

**分析**：三步全部 rejected，`_b_est` 始终为 0（初始值），仅 trust region 几何收缩。即使**新数据点本可以拟合斜率**，模型也不学习。
**结论**：M 级 — SCP 理论上每次观察都该更新模型，无论 accept/reject。

---

## F10 实证 · PoolCapacityPlanner 在整数 demand 上 +1

```bash
python -c "
from sre_control import PoolCapacityPlanner
planner = PoolCapacityPlanner(min_keep_alive=1, max_capacity=1000)
plan, info = planner.plan(demand_rps_forecast=[500.0, 550.0, 600.0])
print(f'demand 500/550/600 RPS -> conn = {plan}')
print(f'true ceil(5.0)=5, ceil(5.5)=6, ceil(6.0)=6')
"
```

**实测输出**：
```
demand 500/550/600 RPS -> conn = [6, 6, 7]
true ceil(5.0)=5, ceil(5.5)=6, ceil(6.0)=6
```

**分析**：500 RPS（5.0 conn）→ 6（多 1）；600 RPS（6.0 conn）→ 7（多 1）；550 RPS（5.5 conn）→ 6（正确）。只有非整数 demand 才"碰巧"正确。原因是 `int(demanded) + 1` 不是 `ceil(demanded)`。
**结论**：M 级成本被系统高估 ~10%。修法用 `math.ceil`。

---

## 综合复现结论

| Finding | 严重度 | 复现成功 | 复现脚本可粘贴 |
|---|---|---|---|
| F01 终点溢出 | H | ✅ 精确 1.44× | ✅ |
| F02 lsq_linear ValueError 不被 except 接 | H | ✅ ValueError 直接冒出 | ✅ |
| F03 EKF 第二个 solve 无保护 | H | ✅ LinAlgError 抛出 | ✅ |
| F04 adapter_family vs route 冲突 | H | ✅ StabilityGuard 双重身份 | ✅ |
| F05 L2 vs sum RPS demand | H 建模约定 | ✅ 28.6% 偏差 | ✅ |
| F08 Canary 不更新模型 | M | ✅ `_b_est` 永远 0 | ✅ |
| F10 PoolPlanner +1 ceiling | M | ✅ 整数 demand 多 1 | ✅ |

7/7 复现，无一例外。这些都不是"理论上可能"，而是"在 HEAD=8d8e064 上现在跑就能看到"。

---

## 复现脚本约定

- 所有命令在 `D:\workspace\SRE-LLM\spacex` 目录下执行；
- Python 解释器是工作区默认环境（与 codex 一致）；
- 任何一条粘到 PowerShell/Git Bash 都能直接跑，无需额外 sys.path 配置；
- 复现脚本是**只读**的，不会写入任何 artifact 或修改源代码。

---

**Opus 4.7 / 2026-05-25 / spacex-session @ 8d8e064**
