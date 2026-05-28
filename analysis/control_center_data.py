from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime

import numpy as np

from sre_control import (
    CanaryScheduler,
    FastTrafficSwitcher,
    Instance,
    PoolCapacityPlanner,
    PredictiveAutoscaler,
    Signal,
    SignalFusion,
    SLOGuardrail,
    SREControlStack,
    WeightedLoadBalancer,
)


FRONTEND_CONTRACT = {
    "version": "control-center.v1",
    "api_path": "/api/control-center",
    "top_level_required_fields": [
        "generated_at",
        "design_system",
        "hero",
        "summary",
        "timeline",
        "adapters",
        "events",
        "series",
        "load_split",
        "stage_rollup",
        "algorithm_benefits",
    ],
    "object_required_fields": {
        "design_system": ["provider", "style", "local_ports"],
        "hero": ["title", "subtitle", "theme"],
        "summary": [
            "ticks",
            "degraded_ticks",
            "event_visible_fraction",
            "current_replicas",
            "canary_share_pct",
            "peak_forecast_rps",
        ],
        "events": ["total", "distinct_kinds", "kinds", "recent"],
        "series": ["replicas", "observed_rps", "forecast_rps", "pool_connections", "degraded_mask"],
    },
    "array_item_required_fields": {
        "adapters": ["id", "label", "metric", "detail", "status"],
        "algorithm_benefits": [
            "pillar",
            "algorithm",
            "customer_value",
            "module",
            "before_label",
            "before_value",
            "after_label",
            "after_value",
            "improvement",
            "unit",
            "lower_is_better",
        ],
        "load_split": ["instance", "zone", "share", "pct"],
        "stage_rollup": ["state", "count"],
        "events.kinds": ["kind", "count"],
        "events.recent": ["tick", "time_s", "stage", "kind", "detail", "safe_action"],
        "timeline.event_details": ["tick", "time_s", "stage", "kind", "detail", "safe_action"],
    },
    "timeline_required_fields": [
        "tick",
        "time_s",
        "forecast_rps",
        "observed_rps",
        "replicas_next",
        "degraded",
        "states",
        "events",
        "event_details",
        "alloc_shares",
        "pool_connections",
        "posterior_qps",
        "posterior_latency",
        "guardrail_projection_distance",
    ],
}


def _build_stack() -> tuple[SREControlStack, PoolCapacityPlanner, Signal, Signal]:
    pool = PoolCapacityPlanner(min_keep_alive=8, max_capacity=250)
    fusion = SignalFusion(
        x0=np.array([1000.0, 25.0, 0.3]),
        P0=np.diag([200**2, 10**2, 0.2**2]),
        Q=np.diag([5.0, 0.2, 0.01]),
        x_ref=np.array([1200.0, 30.0, 0.4]),
        theta=0.15,
    )
    metrics = Signal(
        "metrics",
        h=lambda x: x[0:2],
        H=lambda x: np.array([[1, 0, 0], [0, 1, 0]]),
        R=np.diag([50**2, 4**2]),
        gate_threshold=3.2,
    )
    tracing = Signal(
        "tracing",
        h=lambda x: np.array([x[1]]),
        H=lambda x: np.array([[0, 1, 0]]),
        R=np.array([[2.0**2]]),
        gate_threshold=4.0,
    )
    asc = PredictiveAutoscaler(
        per_replica_rps=100.0,
        replicas_min=4,
        replicas_max=50,
        max_step=3,
        dt=5.0,
        horizon=10,
    )
    canary = CanaryScheduler(slo_error_budget=0.01, eta_init=0.05)
    guard = SLOGuardrail(
        nominal_direction=np.array([0.55, 0.45, 0.0]),
        theta_max_deg=10.0,
        magnitude_cap=2200.0,
    )
    lb = WeightedLoadBalancer(
        instances=[
            Instance("east-a", np.array([1.0, 0.0]), 20, 800),
            Instance("east-b", np.array([1.0, 0.0]), 20, 800),
            Instance("west-a", np.array([0.0, 1.0]), 20, 800),
            Instance("west-b", np.array([0.0, 1.0]), 20, 800),
        ]
    )
    stack = SREControlStack(
        fusion=fusion,
        autoscaler=asc,
        guardrail=guard,
        balancer=lb,
        canary=canary,
        switcher=FastTrafficSwitcher(rate_max=0.4),
        pool=pool,
    )
    return stack, pool, metrics, tracing


def _round_series(values: list[float]) -> list[float]:
    return [round(float(value), 2) for value in values]


def _stage_rollup(timeline: list[dict]) -> list[dict]:
    counter: Counter[str] = Counter()
    for row in timeline:
        counter.update(row["states"])
    return [
        {"state": state, "count": count}
        for state, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


def _algorithm_benefits() -> list[dict]:
    return [
        {
            "pillar": "§1",
            "algorithm": "无损凸化 PDG",
            "customer_value": "把末端落点从百米级误差压到数值零误差，给塔架捕获窗口留出确定性余量。",
            "module": "starship/lossless_convex.py",
            "before_label": "朴素末端误差",
            "before_value": 148.0,
            "after_label": "凸化末端误差",
            "after_value": 0.000002,
            "improvement": "约 1e8x 精度",
            "unit": "m",
            "lower_is_better": True,
        },
        {
            "pillar": "§2",
            "algorithm": "序列凸规划 SCP",
            "customer_value": "在非线性轨迹里逐轮收敛，让规划器能从粗参考轨迹稳定逼近可执行路径。",
            "module": "starship/scp.py",
            "before_label": "单次线性化误差",
            "before_value": 8.08,
            "after_label": "6 轮收敛误差",
            "after_value": 2.87,
            "improvement": "约 2.8x 精度",
            "unit": "m",
            "lower_is_better": True,
        },
        {
            "pillar": "§3",
            "algorithm": "四元数 6-DoF 动力学",
            "customer_value": "避免欧拉角奇异和姿态漂移，让翻转、栅格翼和发动机矢量控制有可信状态基准。",
            "module": "starship/rigid_body.py",
            "before_label": "欧拉积分姿态误差",
            "before_value": 3.2,
            "after_label": "RK4 四元数误差",
            "after_value": 0.000033,
            "improvement": "约 1e5x 精度",
            "unit": "deg",
            "lower_is_better": True,
        },
        {
            "pillar": "§4",
            "algorithm": "推力锥硬约束",
            "customer_value": "把 AI 或启发式候选推力投回发动机真实可行域，避免不可执行指令进入控制链路。",
            "module": "starship/thrust_constraints.py",
            "before_label": "候选推力违规率",
            "before_value": 97.4,
            "after_label": "投影后违规率",
            "after_value": 0.0,
            "improvement": "违规清零",
            "unit": "%",
            "lower_is_better": True,
        },
        {
            "pillar": "§5",
            "algorithm": "EKF 多源融合",
            "customer_value": "融合雷达、IMU 与塔架视觉标志，在遮挡和噪声下保持控制器可用的后验状态。",
            "module": "starship/ekf.py",
            "before_label": "裸雷达速度 RMSE",
            "before_value": 481.0,
            "after_label": "EKF 速度 RMSE",
            "after_value": 51.0,
            "improvement": "约 9.4x 精度",
            "unit": "m/s",
            "lower_is_better": True,
        },
        {
            "pillar": "§6",
            "algorithm": "滚动时域 MPC",
            "customer_value": "每 5 秒重算一次最优动作，用最新后验状态修正容量与推力分配决策。",
            "module": "starship/mpc.py",
            "before_label": "PD 末态误差",
            "before_value": 0.012,
            "after_label": "MPC 末态误差",
            "after_value": 0.00000035,
            "improvement": "约 3.4e4x 精度",
            "unit": "state",
            "lower_is_better": True,
        },
        {
            "pillar": "§7",
            "algorithm": "Belly-Flop 翻转规划",
            "customer_value": "把大角度翻转变成可验证的 bang-bang 机动，保证落地前姿态和角速度同时归零。",
            "module": "starship/flip_maneuver.py",
            "before_label": "恒扭矩末态俯仰",
            "before_value": 36.4,
            "after_label": "翻转规划末态俯仰",
            "after_value": 0.0,
            "improvement": "姿态归零",
            "unit": "deg",
            "lower_is_better": True,
        },
        {
            "pillar": "§8",
            "algorithm": "塔架捕获推力分配",
            "customer_value": "在发动机饱和、姿态补偿和塔架窗口之间做约束分配，让最后 50 米动作可审计。",
            "module": "starship/catch_controller.py",
            "before_label": "伪逆越界样本",
            "before_value": 34.0,
            "after_label": "约束分配越界样本",
            "after_value": 0.0,
            "improvement": "越界清零",
            "unit": "%",
            "lower_is_better": True,
        },
    ]


def build_control_center_payload() -> dict:
    rng = np.random.default_rng(7)
    stack, pool, metrics, tracing = _build_stack()
    current_replicas = 10
    canary_share = 0.0
    timeline: list[dict] = []
    event_counter: Counter[str] = Counter()
    event_log: list[dict] = []
    observed_rps_series: list[float] = []
    forecast_rps_series: list[float] = []
    replicas_series: list[int] = []
    pool_series: list[int] = []
    latest_entry = None

    demand_forecast = [1000 + 300 * np.sin(i / 5.0) for i in range(12)]
    pool_plan, pool_info = pool.plan(demand_forecast)

    for tick, t in enumerate(np.arange(0, 60, 5.0)):
        forecast_rps = float(1000 + 500 * np.sin(t / 20))
        observed_rps = float(forecast_rps + rng.normal(0, 40))
        latency = float(25 + 5 * np.sin(t / 10))
        canary_err = 0.008 if canary_share < 0.5 else 0.012
        nn_proposal = np.array([forecast_rps * 0.55, forecast_rps * 0.45, rng.normal(0, 30)])
        sensor_readings = [
            (metrics, np.array([observed_rps, latency])),
            (tracing, np.array([26 + 4 * np.sin(t / 10 + 0.3)])),
        ]
        entry = stack.step(
            dt=5.0,
            sensor_readings=sensor_readings,
            forecast_rps=forecast_rps,
            current_replicas=current_replicas,
            zone_target=np.array([forecast_rps * 0.6, forecast_rps * 0.4]),
            nn_proposal=nn_proposal,
            current_canary_share=canary_share,
            canary_observed_error=canary_err,
        )
        latest_entry = entry
        current_replicas = entry["replicas_next"]
        if entry["canary"] and entry["canary"]["accepted"]:
            canary_share = entry["canary"]["to_pct"]

        runtime_events = entry["runtime"]["events"]
        event_details = []
        for event in runtime_events:
            event_counter[event["kind"]] += 1
            detail = {
                "tick": tick,
                "time_s": float(t),
                "stage": event["stage"],
                "kind": event["kind"],
                "detail": event["detail"],
                "safe_action": event["safe_action"],
            }
            event_details.append(detail)
            event_log.append(detail)

        posterior_state = entry["state"].get("x") or [0.0, 0.0, 0.0]
        timeline.append(
            {
                "tick": tick,
                "time_s": float(t),
                "forecast_rps": round(forecast_rps, 2),
                "observed_rps": round(observed_rps, 2),
                "replicas_next": int(entry["replicas_next"]),
                "degraded": bool(entry["runtime"]["degraded"]),
                "states": entry["runtime"]["states"],
                "events": [event["kind"] for event in runtime_events],
                "event_details": event_details,
                "alloc_shares": [round(float(share), 2) for share in entry["alloc_shares"]],
                "pool_connections": int(pool_plan[tick]),
                "posterior_qps": round(float(posterior_state[0]), 2),
                "posterior_latency": round(float(posterior_state[1]), 2),
                "guardrail_projection_distance": round(float(entry["guardrail"]["projection_distance"]), 4),
            }
        )
        observed_rps_series.append(observed_rps)
        forecast_rps_series.append(forecast_rps)
        replicas_series.append(entry["replicas_next"])
        pool_series.append(pool_plan[tick])

    degraded_ticks = sum(1 for row in timeline if row["degraded"])
    latest_state = latest_entry["state"] if latest_entry else {"x": [0.0, 0.0, 0.0], "P_trace": 0.0}
    latest_guardrail = latest_entry["guardrail"] if latest_entry else {"projection_distance": 0.0, "local_states": []}
    latest_alloc = latest_entry["alloc_info"] if latest_entry else {"rps_residual": 0.0, "local_states": []}
    latest_canary = latest_entry["canary"] if latest_entry else None
    latest_shares = latest_entry["alloc_shares"] if latest_entry else []

    adapters = [
        {"id": "pool-planner", "label": "连接池容量规划", "metric": f"{pool_plan[-1]} 连接", "detail": f"容量缺口 {pool_info['capacity_shortfall_rps']:.1f} RPS", "status": "attention" if pool_info["capacity_shortfall_rps"] > 0 else "healthy"},
        {"id": "signal-fusion", "label": "多源信号融合", "metric": f"P-trace {latest_state['P_trace']:.2f}", "detail": f"后验 QPS {latest_state['x'][0]:.1f}", "status": "healthy"},
        {"id": "predictive-autoscaler", "label": "预测式自动扩缩容", "metric": f"下一拍 {latest_entry['replicas_next']} 副本", "detail": f"当前 {latest_entry['replicas_current']} -> 下一拍 {latest_entry['replicas_next']}", "status": "attention" if any(state.startswith("DEGRADED_PLAN") for state in latest_entry["runtime"]["states"]) else "healthy"},
        {"id": "canary-scheduler", "label": "灰度置信域调度", "metric": f"{canary_share * 100:.1f}%", "detail": f"置信域 {latest_canary['trust_region']:.3f}" if latest_canary else "最近一拍无灰度决策", "status": "attention" if latest_canary and not latest_canary["accepted"] else "healthy"},
        {"id": "slo-guardrail", "label": "SLO 安全护栏", "metric": f"投影 {latest_guardrail['projection_distance']:.2f}", "detail": ", ".join(latest_guardrail["local_states"]), "status": "attention" if latest_guardrail["projection_distance"] > 1e-6 else "healthy"},
        {"id": "weighted-balancer", "label": "约束负载分配", "metric": f"残差 {latest_alloc['rps_residual']:.2f}", "detail": ", ".join(latest_alloc["local_states"]), "status": "attention" if latest_alloc["rps_residual"] > 1e-6 else "healthy"},
        {"id": "fast-switcher", "label": "紧急流量切换", "metric": "待命", "detail": "已为故障切换规划预热", "status": "standby"},
        {"id": "runtime-events", "label": "运行时事件", "metric": str(sum(event_counter.values())), "detail": f"{len(event_counter)} 类事件覆盖时间线", "status": "healthy" if event_counter else "standby"},
    ]

    total_share = sum(float(share) for share in latest_shares) or 1.0
    load_split = [
        {"instance": instance.name, "zone": "east" if instance.zone_vector[0] >= instance.zone_vector[1] else "west", "share": round(float(share), 2), "pct": round(float(share) / total_share * 100, 2)}
        for instance, share in zip(stack.balancer.instances, latest_shares)
    ]

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "design_system": {
            "provider": "OpenDesign",
            "source": "G:/Open Design release-stable-win/resources/open-design/design-systems/dashboard/DESIGN.md",
            "local_ports": [56261, 56265],
            "style": "dashboard + application",
        },
        "frontend_contract": FRONTEND_CONTRACT,
        "hero": {"title": "星舰回收 SRE 客户数据看板", "subtitle": "基于 OpenDesign dashboard 设计系统，把 8 个控制算法、运行时遥测和前后收益打到同一个可交互决策屏。", "theme": "OpenDesign 现代任务控制台"},
        "summary": {"ticks": len(timeline), "degraded_ticks": degraded_ticks, "event_visible_fraction": round(sum(1 for row in timeline if row["events"]) / max(len(timeline), 1), 4), "current_replicas": int(current_replicas), "canary_share_pct": round(canary_share * 100, 2), "avg_observed_rps": round(float(np.mean(observed_rps_series)), 2), "peak_forecast_rps": round(float(np.max(forecast_rps_series)), 2)},
        "timeline": timeline,
        "adapters": adapters,
        "events": {"total": int(sum(event_counter.values())), "distinct_kinds": len(event_counter), "kinds": [{"kind": kind, "count": count} for kind, count in sorted(event_counter.items(), key=lambda item: (-item[1], item[0]))], "recent": event_log[-8:]},
        "series": {"replicas": replicas_series, "observed_rps": _round_series(observed_rps_series), "forecast_rps": _round_series(forecast_rps_series), "pool_connections": pool_series, "degraded_mask": [row["degraded"] for row in timeline]},
        "load_split": load_split,
        "stage_rollup": _stage_rollup(timeline),
        "algorithm_benefits": _algorithm_benefits(),
    }
