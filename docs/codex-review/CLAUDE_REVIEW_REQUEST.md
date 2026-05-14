# Claude Review Request

> 目标：请 Claude 对 Codex 在 `spacex-session` 上的最新推进做一次工程审查。
> 审查范围只基于公开文章抽象、当前仓库实现和本地合成证据，不假设任何 SpaceX 官方内部实现。

## 预期输出

请优先返回问题，而不是复述功能。建议按下面格式输出：

| Priority | File / Area | Finding | Why it matters | Suggested fix |
|---|---|---|---|---|
| P0/P1/P2 | path or module | 具体问题 | 对控制栈或 SRE 迁移的影响 | 可执行修复建议 |

如果没有 P0，请明确写“未发现 P0 阻断”。如果某项只是口径建议，也请标成 P2，避免和行为缺陷混在一起。

## P0 审查项

| 主题 | 请重点审什么 | 相关文件 |
|---|---|---|
| 依赖边界 | `starship/` 是否仍是纯数学/物理抽象层，不反向 import `sre_control/`；`StabilityMonitor` 是否没有把 SRE 语义塞回基础层 | `starship/stability_monitor.py`, `tests/test_import_graph.py`, `sre_control/stability_guard.py` |
| 事件 schema 闭环 | 11 个 `event kind` 是否都有真实触发路径、counter-example、测试覆盖；`adapter_exception` 的 cause 字段是否足够可审 | `sre_control/events.py`, `tests/test_event_schema.py`, `tests/test_sre_control.py`, `docs/EVENT_SCHEMA.md` |
| 异常兜底 | `SREControlStack.step()` 只抓 `RecoverableControlError` 后，allocator fallback 语义是否仍合理；`adapter_exception` 是否保留足够 root cause | `sre_control/stack.py`, `tests/test_contracts.py`, `docs/RUNTIME_STATES.md` |
| failure trace 证据 | `analysis/s10_failure_trace.py` 的单 stack history、`event_visible_fraction`、`background_event_fraction` 与 `replica_bound_active` 覆盖率是否足以证明 lifecycle observability | `analysis/s10_failure_trace.py`, `tests/test_failure_trace.py`, `analysis/artifacts/SUMMARY.txt` |

## P1 审查项

| 主题 | 请重点审什么 | 相关文件 |
|---|---|---|
| Innovation gating | `SignalFusion` 的 Mahalanobis gate 是否数值稳定；全局阈值是否会误杀正常传感器；被拒观测是否污染 posterior | `sre_control/signal_fusion.py`, `starship/ekf.py`, `tests/test_sre_control.py` |
| Lyapunov guard | `dV/dt` 有限差分、`k_violations`、tolerance 默认值是否合理；是否需要物理能量函数样例，而不是只有 generic scalar | `starship/stability_monitor.py`, `sre_control/stability_guard.py`, `tests/test_stability_monitor.py` |
| before/after 证据 | 各研究是否只在合成场景内成立；是否有指标被过度解释成通用结论 | `analysis/`, `analysis/artifacts/SUMMARY.txt`, `docs/codex-review/QUALITY_GATES.md` |
| 文档口径漂移 | `64 passed`、`10 studies`、`11 event kinds` 是否在主文档、V2 知识库、review 包里保持一致 | `docs/`, `PR-REQUIREMENTS.md` |
| SRE 能力复利 | 8 个数学支柱是否已经抽象成可复用 SRE 控制原语，而不是一次性 demo 适配 | `sre_control/`, `docs/ARCHITECTURE.md`, `docs/codex-review/CODEX_SUMMARY.md` |

## P2 审查项

| 主题 | 请重点审什么 | 相关文件 |
|---|---|---|
| 命名与 UX | `degraded_tick_fraction`、`stability_violation`、`outlier_rejected` 是否表达准确 | `analysis/s10_failure_trace.py`, `sre_control/events.py` |
| 可视化入口 | 主知识库和 V2 知识库是否仍有重复或漂移；图像/GIF/HTML 是否能让评审快速定位证据 | `docs/knowledge-base.html`, `docs/V2_Knowledge/knowledge-base.html`, `docs/assets/` |
| 性能与规模 | 当前 tests 和 analysis 都是小规模合成数据；是否需要压测或更大 trace | `tests/`, `analysis/` |
| backlog 精简 | 下一步列表是否混入了非阻断优化，是否应该拆成 PR 粒度 | `docs/CODEX_HANDOFF.md`, `docs/codex-review/OPEN_RISKS.md` |

## 建议复现路径

```bash
python -m pytest tests -q
python -m analysis.run_all
python -m analysis.s10_failure_trace
python -m examples.demo_sre_loop
```

可选检查：

```bash
python -m pytest tests --collect-only -q
python -m examples.demo_powered_descent
python -m examples.demo_catch_phase
```

## 特别想请 Claude 挑刺的点

1. `SignalFusion` 的 outlier gate 是否缺少 sensor-class-specific 策略。
2. allocator recoverable fallback 是否应该保持 last known good，而不是回到全零 shares。
3. §10 的 `replica_bound_active` 只覆盖 60% 窗口，这个证据强度是否足够。
4. `StabilityGuard` 的 manual-reset latch 是否已经足够清晰，还是仍需要更具体的服务能量函数样例。
5. 文档是否仍存在“已经证明生产可用”的误读风险。
