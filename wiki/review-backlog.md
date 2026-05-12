# Review Backlog

> 当前实现顺序以 `docs/codex-review/CLAUDE_REFINED_SPEC.md` 为准。本页是跨会话知识库摘要。

## P1 execution gate

### PR-A: Refine §10 failure-trace evidence

目标：把 §10 从“事件通道可见”提升为可审查的连续场景证据。

验收要点：

- 单一连续 `SREControlStack` 实例。
- `background_event_fraction < 0.20`，除非有更严格阈值。
- `degraded_tick_fraction` 不再饱和；若保留，只作为 legacy metric。
- `s10_trace_full.jsonl` 行数等于 `event_count_total`。
- 每个 injection window 都有明确 event kind 覆盖。

### PR-B: Add stage-specific fallback taxonomy

状态：已实现，待最终提交。

目标：让 recoverable control-domain failure 可恢复，让 programmer error fail fast。

验收要点：

- 已引入 `ControlDomainError` / `RecoverableControlError` / `AdapterInputError`。
- `SREControlStack.step()` 只捕获 `RecoverableControlError`，不吞 `AttributeError` / `TypeError` 等 programmer error。
- `adapter_exception` event payload 包含 `stage`、`exception_type`、`cause_type`、`recoverable`。
- docs 已说明 exception taxonomy。

### PR-C: Lock StabilityGuard semantics

目标：把 StabilityGuard 固化为 manual-reset latch。

验收要点：

- `triggered` 一旦触发保持 true，直到显式 `reset()`。
- 文档不暗示自动恢复。
- Lyapunov 红线事件与 adapter exception 可区分，至少通过 cause 字段区分。

### PR-D: Add per-sensor innovation gate policy

目标：让不同 sensor 使用不同 gate threshold，并把实际阈值写入 trace。

验收要点：

- 同一 tick 内一个 sensor 可被拒绝，另一个可被接受。
- rejected observation 不污染 posterior。
- trace 包含 `threshold_used` 和 `innovation_mahalanobis`。

## P3 hardening

### PR-E: Prevent docs/schema drift

- `docs/RUNTIME_STATES.md` 明确 8 core adapter events 与 2 cross-cutting events。
- 添加 docs/schema sync check。
- counterexample 对每个 event kind 仍强制。

### PR-F: Strengthen import graph boundaries

- `starship/` import 白名单。
- 底层禁止 import `analysis`、`examples`、`docs`。
- `sre_control` 可依赖 `starship`，反向禁止。

## Final merge gate

```bash
python -m pytest tests -q
python -m analysis.s10_failure_trace
python -m analysis.run_all
python -m examples.demo_sre_loop
```

最终状态必须覆盖：

- 新 §10 metrics 出现在 `analysis/artifacts/SUMMARY.txt`。
- `s10_trace_full.jsonl` 行数等于 `event_count_total`。
- 测试覆盖连续 stack history。
- 测试覆盖 programmer errors are not swallowed。
- 测试覆盖 StabilityMonitor latch-until-reset。
- 测试覆盖 per-sensor gate threshold tracing。
- 文档持续声明 synthetic evidence boundary。
