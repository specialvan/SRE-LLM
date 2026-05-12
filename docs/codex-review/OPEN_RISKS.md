# Open Risks

> 本页是 Codex 自己交给 Claude 的风险登记。这里列出的不是已确认 bug，而是最值得继续审查的数值、建模、边界条件和文档口径风险。

## 风险总览

| ID | Priority | Area | 风险 | 建议下一步 |
|---|---|---|---|---|
| R1 | P1 | §10 failure trace | `degraded_tick_fraction = 100%` 容易被误读成系统全程降级，而不是“事件可见性通道全开” | 拆成 `event_visible_fraction` 和 `true_degraded_fraction` |
| R2 | P1 | Stack fallback | `SREControlStack.step()` 统一异常兜底可能隐藏编程错误 | 区分 control-domain exception 与 programmer error；增加 stage-specific fallback |
| R3 | P1 | Stability | 当前 Lyapunov monitor 是 generic scalar 版本，缺少更贴近服务系统的能量函数 | 增加队列长度、误差预算、恢复趋势组合的 SRE energy 示例 |
| R4 | P1 | Signal fusion | Innovation gate 使用全局阈值，缺少按信号源差异配置 | 增加 per-sensor threshold、cooldown、re-admission 策略 |
| R5 | P2 | Event schema drift | 文档、测试、registry 已同步到 10 kinds，但未来新增 kind 容易漏同步 | 增加 docs/schema 自动核对脚本或 snapshot check |
| R6 | P2 | Knowledge base drift | 主知识库与 V2 知识库仍是两个入口，长期会产生解释差异 | 选一个主入口，另一个降级为归档或构建产物 |
| R7 | P2 | Synthetic evidence | before/after 都是合成场景证据，容易被过度泛化 | 在报告中持续标注“场景内证据”，不要写成生产定理 |
| R8 | P2 | Catch/SRE wrapper | CatchController 仍主要是物理层 trace，SRE 迁移需要 adapter 包装而不是反向依赖 | 如果推进 catch-to-SRE，新增 wrapper 层并加 import graph 测试 |

## 数值风险

| 风险 | 具体表现 | 影响 |
|---|---|---|
| 零分母和极小分母 | `SUMMARY.txt` 里 timing 或 before metric 为 0 时会出现 `×inf` | 容易让 reviewer 误把计时波动当成能力提升 |
| Covariance 退化 | EKF / innovation gating 如果 covariance 过小，Mahalanobis distance 会被放大 | 正常观测可能被误拒 |
| 有限差分噪声 | Lyapunov `dV/dt` 用离散差分估计，tick 间隔和噪声会影响 violation 判断 | 稳定性红线可能抖动 |
| 边界投影残差 | guardrail / bounded LS 虽能投影到可行域，但 residual 可能意味着业务需求未满足 | “安全”不等于“足够好” |

## 建模风险

| 风险 | 具体表现 | 影响 |
|---|---|---|
| SRE 原语过度类比火箭控制 | 凸化、MPC、EKF 都是迁移抽象，不是把 Starship 控制器搬到生产系统 | 需要持续避免“官方 SpaceX 实现”误读 |
| 单一 stack 编排过强 | `SREControlStack` 把多个 adapter 串在一起，研究友好但生产系统通常是分布式控制面 | 未来要拆控制面职责和数据契约 |
| Stability function 太抽象 | 只要用户传入 scalar function 就能跑，但函数质量决定监控意义 | 需要给 SRE 域推荐默认函数族 |
| Event kind 粒度仍粗 | `stability_violation` 同时承载异常兜底和稳定性红线，语义压力大 | 后续可拆 `adapter_exception` / `lyapunov_violation` |

## 边界条件风险

| 模块 | 风险 |
|---|---|
| `PoolCapacityPlanner` | 容量上下界、整数副本、冷启动延迟未完全模拟 |
| `CanaryScheduler` | trust region 拒绝后如何恢复推进仍偏简单 |
| `TopologyState` | repair 会让状态合法，但可能掩盖上游拓扑输入异常 |
| `SLOGuardrail` | 投影后动作可行，但可能牺牲用户意图或业务收益 |
| `SignalFusion` | 缺失传感器和异常传感器的恢复策略仍粗 |
| `PredictiveAutoscaler` | replica bound active 能保安全，但不代表容量规划最优 |
| `FastTrafficSwitcher` | deadline exceeded 只说明切换策略超时，不说明根因 |
| `WeightedLoadBalancer` | bounded residual 需要进入业务告警，否则会被当成正常误差 |
| `StabilityGuard` | 连续 violation 的窗口长度和阈值目前需要场景化调参 |

## Codex 建议的下一批 PR

1. `s10` 指标拆名 + 全量 JSONL 导出 + dashboard query 示例。
2. `SREControlStack` stage-specific fallback，并把 programmer error 从控制域异常中分离。
3. `SignalFusion` per-sensor gate policy。
4. `StabilityMonitor` 增加 SRE energy function 示例。
5. 文档入口收敛：主知识库与 V2 知识库只保留一个 canonical 入口。
