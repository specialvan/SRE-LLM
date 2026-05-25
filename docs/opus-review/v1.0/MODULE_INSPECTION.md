# 重点模块逐文件笔记 · v1.0

按层级整理每个被本轮新增或重写的关键模块的实现要点、亮点与观察。
所有引用都附上文件路径 + 行号锚点，便于直接跳转。

## sre_control/

### `sre_control/__init__.py`
- 公开 11 个 adapter + 2 个 event helper + 3 个 exception 类 + `stack_data_contract`；
- `__all__` 与导出列表一致，无悬空符号。

### `sre_control/events.py`
- `REQUIRED_EVENT_FIELDS = ("stage", "kind", "detail", "safe_action")`（`sre_control/events.py:8`）；
- `EVENT_COUNTEREXAMPLES` 11 项闭包字典；
- `make_event` 拒绝未注册 kind（`sre_control/events.py:70-71`）；
- `validate_event` 对 `bounded_ls_residual` 与 `adapter_exception` 做 kind-specific 字段强校验（`sre_control/events.py:93-113`）；
- 普通 `_is_number` helper 显式排除 bool（`sre_control/events.py:116-117`），避免 JSON `true` 被当数字。

### `sre_control/exceptions.py`
- 极简 15 行；三层分类清晰：
  ```
  ControlDomainError
   └─ RecoverableControlError
       └─ AdapterInputError
  ```
- 单点扩展，没有循环 import 风险。

### `sre_control/stack.py` (355 行)
- 关键护栏：`_allocator_signature()`（`sre_control/stack.py:89-98`）把 instances 拓扑+容量打包成 tuple，用作 last-good 复用 gate；
- `_can_reuse_last_good_alloc()` 检查 shape + 边界（`sre_control/stack.py:101-112`），失败则 bootstrap zero；
- `_adapter_exception_event` 是统一的 event factory（`sre_control/stack.py:115-144`），所有 stage 走同一构造，确保 schema 一致；
- 每个 stage 的 `try/except` **只**捕获 `RecoverableControlError`，programmer error 透传（I-5 不变式）；
- StabilityMonitor 用 `was_triggered_before` 区分首次触发 vs sustained（`sre_control/stack.py:194-216`）。

### `sre_control/stack_contract.py` (91 行) — 新增
- `stack_data_contract()` 返回 dict，6 个 stage（observe/stability/plan/guard/allocate/execute）；
- `event_stage_routes` 把 runtime stage 前缀映射到 contract stage；
- `split_ready_boundaries` 给未来分布式拆分留命名锚点。

### `sre_control/catch_adapter.py` (59 行) — 新增
- `CatchLoadAdapter` 通过组合而非继承委托 `WeightedLoadBalancer`；
- 仅在 trace 中追加 `sre_catch_wrapper` 状态标识；
- source tag `sre_wrapper_for_catch_allocation` 防止反向被当成 starship 内部实现宣称。

### `sre_control/stability_guard.py` (147 行)
- `sre_error_budget_V` 是工厂函数（`sre_control/stability_guard.py:31-61`），把"延迟超出+错误率超出归一化平方和"封装成 Lyapunov 候选；
- 入参 scale 校验为正（`sre_control/stability_guard.py:48-51`）；
- `StabilityGuard.step` 用 `was_triggered_before` 抑制重复 event（`sre_control/stability_guard.py:111-128`）；
- 与底层 `starship.StabilityMonitor` 解耦，可独立测试。

### `sre_control/signal_fusion.py` (190 行)
- 每个 sensor 独立 `gate_threshold`，回落到 fusion 默认（`sre_control/signal_fusion.py:94-100`）；
- 连续 rejection 计数（`_rejections` dict），用作 detail 字符串里"该 sensor 已被拒 N 次"；
- 成功更新后重置该 sensor 的计数（`sre_control/signal_fusion.py:163-164`），避免历史污染。

### `sre_control/weighted_balancer.py` (110 行)
- `_matrix()` 构造 (rps + zone-vector) 联合系数矩阵；
- bounded LS 用 `scipy.optimize.lsq_linear`；
- event 携带 `rps_residual_fraction` 与 `demand_satisfied`，让上游不会误把"合法但低"当"完成"；
- ⚠️ 未包装 solver 异常 — 见 v1.0 DEEP_REVIEW §5.4。

## starship/

### `starship/ekf.py` (256 行)
- `EKF.update` Joseph 形式（`starship/ekf.py:91-99`）；
- `_stabilize_covariance` 对称化 + 可选特征值地板（`starship/ekf.py:102-110`）；
- Mahalanobis 距离用 `solve(S, y)`（数值稳定），`LinAlgError` 退化为 `inf`（safe-by-default gate）；
- 三个测量模型 (`RadarMeasurement`/`IMUMeasurement`/`FiducialMeasurement`) 各自带 `h` + `H` Jacobian（数值或解析），covariance R 默认值合理。

### `starship/stability_monitor.py` (207 行)
- Manual-reset latch：`triggered` 一旦为 True，必须显式 `reset()`（`starship/stability_monitor.py:107-141`）；
- `min_derivative_dt` 默认 1e-9，挡掉重复 timestamp 与抖动；
- `summary()` 提供 JSONL-friendly dict；
- 顶层 helpers `kinetic_plus_potential_V` / `quadratic_V` 让物理与 SRE 场景共用同一 monitor。

## analysis/

### `analysis/evidence_manifest.py` (191 行) — 新增
- 把 `s10_failure_trace.main()` / `s11_catch_sre_wrapper.main()` / `s12_sre_replay.main()` 串联；
- 每个 artifact 用 `_artifact_metadata` 计算 SHA-256 与字节数；
- `_artifact_ref` 强制 repo-relative 路径，防绝对路径漂移。

### `analysis/evidence_report.py` (1662 行) — 新增
13 类函数职责分组（可拆分依据见 v1.0 DEEP_REVIEW §6.1）：

1. `_resolve_artifact` / `_is_*` 工具；
2. `_artifact_paths` / `_nonportable_artifact_paths`；
3. `_artifact_metadata` / `_artifact_identity_errors`；
4. `_manifest_shape_errors`（顶层 shape + 字段类型/范围/固定值/closed sets）；
5. `_invalid_artifact_errors` 入口；
6. `_s10_trace_shape_errors`；
7. `_s11_diagnostics_shape_errors`；
8. `_s12_diagnostics_shape_errors` / `_s12_trace_shape_errors` / `_s12_fixture_shape_errors`；
9. `_invalid_png_errors` / `_invalid_jsonl_errors`；
10. `_consistency_errors` / `_contract_consistency_errors`；
11. `_schema_invalid_event_errors`；
12. `_contract_event_errors`；
13. `main` / `_cli`。

### `analysis/s11_catch_sre_wrapper.py` (201 行) — 新增
- 三类合成 case 平均分（feasible / total_overload / placement_infeasible），每类 40 个；
- `feasible` 案例 baseline 走精确 share normalization 不被惩罚；
- `total_overload` baseline 隐藏 residual（教育反例）；
- after 用 `CatchLoadAdapter`，看 event 是否暴露。

### `analysis/s12_sre_replay.py` (324 行) — 新增
- 固定 19-tick fixture `analysis/fixtures/sre_replay.jsonl`；
- 包含 5 类 expected_kind 与一个 3-tick 复合事件 `compound_telemetry_policy_capacity`；
- 计算多维 diagnostics：recovery / operator-action / multi-signal window 三组；
- 每条 expected event 行带 `operator_action`，复合窗口带 `window_operator_action`；
- `before` 全 0 baseline 是教学性的对比起点。

## scripts/

### `scripts/evidence_boundary_lint.py` (71 行) — 新增
- 7 条 overclaim 正则（`scripts/evidence_boundary_lint.py:17-24`）；
- 16 条否定提示（中英混合）（`scripts/evidence_boundary_lint.py:26-43`）；
- 8 行上下文回看 + 200 字符窗口，足以覆盖 markdown 段落级否定语境。

### `scripts/quality_gate_counts.py` (235 行)
- `replace_once` 在 7 个文档里同步测试计数；
- `require_quality_gate_commands` 守护 4 条 gate 命令必须仍列在 PR + HTML；
- 单点失败模式：任一 regex 不匹配即 `RuntimeError`，可能因文档措辞变化而误触发。

## tests/

### `tests/test_synthetic_evidence_boundaries.py` (212 行)
- 同时是 study 行为测试 + live docs lint 测试；
- 7 份 live review 文档列入 `test_live_review_docs_do_not_make_unqualified_production_claims`。

### `tests/test_evidence_manifest.py` (90 KB)
- 覆盖 manifest 生成 + report 校验的负向用例；
- 测试矩阵非常完整，但单文件偏大，建议拆分（见 v1.0 DEEP_REVIEW §6.2）。

## docs/

### `docs/STACK_DATA_CONTRACT.md` (新增)
- 与 `sre_control/stack_contract.py` 一一对应；
- 显式声明研究 metadata，非生产承诺。

### `docs/EVENT_EVIDENCE_MANIFEST.md` (新增)
- 与 `analysis/evidence_manifest.py` + `analysis/evidence_report.py` 互为契约；
- 写得较密集（167 行单页），新增字段需同步该 doc + `tests/test_evidence_manifest.py`。

---

**Opus 4.7 / 2026-05-25**
