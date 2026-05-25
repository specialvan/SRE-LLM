# Opus 深度评审 · v1.0 主报告

**评审范围**：`spacex-session` 分支下截至 commit `8d8e064` 的全部 codex 交付。
**评审角度**：架构一致性、模块实现质量、证据边界纪律、可维护性、可演化性。
**结论先行**：当前工程态已稳定收敛到一个可复核的研究级 SRE/控制栈，249 个测试与 12 个分析研究全绿，证据边界经多轮自审与产出，整体可作为后续研究迭代的稳态基线。无 P1 阻塞，仅有少量 P2 改进建议。

---

## 1 · 总体判断

### 1.1 工程姿态评分

| 维度 | 评分 | 关键依据 |
|---|---|---|
| **架构边界** | A | `starship/` ↔ `sre_control/` 单向依赖由 `test_import_graph.py` 守护；`CatchLoadAdapter` 通过 SRE 侧 wrapper 实现 catch 迁移而不破坏方向 |
| **事件 schema** | A | 11 个 runtime kinds 全部闭包 + counterexample + schema-doc 同步测试 |
| **异常分类** | A- | `ControlDomainError` → `RecoverableControlError` → `AdapterInputError` 三层分离；programmer error 显式不吞；`adapter_exception` 字段齐全 |
| **数值稳定** | A | EKF 用 Joseph 形式 + 协方差对称化 + 可配特征值地板；`StabilityMonitor` 用 `min_derivative_dt` 抑制调度器抖动 |
| **证据纪律** | A | 所有合成研究都打 `synthetic_*` 标签；`scripts/evidence_boundary_lint.py` 主动拦截过度宣称；live docs 通过 lint 测试 |
| **可观测性** | A | 跨研究 manifest + 字节身份记录 + 1662 行 `evidence_report` 验证 (shape/path/SHA-256/parse/schema/count/scope/route 全覆盖) |
| **测试纪律** | A | 249 个测试全绿；含契约、event schema、降级路径、release hygiene、package smoke、import graph、HTML 资产等多维护栏 |
| **文档同步** | A- | `quality_gate_counts.py` 自动同步 7 个文档的测试计数；HTML/PR/wiki/codex-review 多端不漂移 |
| **可维护性** | B+ | `analysis/evidence_report.py` 1662 行单文件偏大；`tests/test_evidence_manifest.py` 90 KB；后续应当拆分 |
| **可演化性** | A- | `sre_control.stack_data_contract()` 显式声明 split-ready boundary，给未来分布式拆分留接口；但当前实现仍是 single-process loop |

### 1.2 与 codex 自评的差异

codex 自评（`docs/codex-review/CODEX_SUMMARY.md`）在以下方面与 Opus 评审一致：

- PR-A/B/C/D 已收敛，证据边界稳态；
- Section 10/11/12 全套证据闭合；
- stack_data_contract 已是 split-ready 元数据。

差异之处（建议补强的项见 §6）：

- codex 主推"release-pipeline automation"作为下一步，Opus 评审认为 **`evidence_report.py` 拆分**优先级更高（可维护性 vs 形式工具）。
- codex 把 `compound_telemetry_policy_capacity` 复合事件作为一项独立 evidence；Opus 评审认为这是必要的但 fixture 写法略硬编码，可考虑用工厂模式生成。
- codex 未提及 `adapter_family` 与 `fault_family` 在当前 `_adapter_exception_event` 内的等价问题（详见 §5.3）。

---

## 2 · 架构层评审

### 2.1 双层架构

```
starship/  ← 物理/数学层（无 SRE 依赖）
   │
   ▼ (单向 import)
sre_control/  ← SRE 翻译/适配层
   │
   ▼
analysis/  ← 研究脚本与证据生成
```

**护栏**：`tests/test_import_graph.py` 用 AST 扫描禁止 `starship/*.py` 中出现 `from sre_control` 或 `import sre_control`。验证机制可信。

**反例处理**：`sre_control.catch_adapter.CatchLoadAdapter` 把 catch 控制器的桥接放在 SRE 侧而不是 starship 侧 — 这是非常正确的设计，保持了边界纯净。

### 2.2 SREControlStack 流水线

```
OBSERVE → STABILITY → PLAN → GUARD → ALLOCATE → EXECUTE
```

每个 stage 的契约由 `sre_control.stack_data_contract()` 显式导出：

- 阶段 inputs/outputs
- 阶段允许的 `event_kinds`
- runtime stage 前缀 → contract stage 的路由表
- split-ready boundary 命名（`observe_to_plan` 等）

**评估**：这一份"未来要拆分时该按哪条线拆"的元数据写得非常有节制 — 既给了拆分接口，又用 `production_claim=false` 明确这是研究态，不是分布式控制平面承诺。极佳的工程纪律。

### 2.3 状态-事件双轨

`runtime.states` 列表（`OBSERVING/DEGRADED_OBSERVE/...`）与 `runtime.events`（结构化事件）双轨。`I-3` 不变式要求 `runtime.degraded=True ⇒ DEGRADED_* state + ≥1 event`，由 `test_contracts.py` 强制。这条护栏避免了状态/事件失同步的常见坑。

---

## 3 · 模块层评审

### 3.1 `sre_control/stack.py` (355 行)

**亮点**：

- `_adapter_exception_event` 静态方法统一构造 `adapter_exception`，避免散落不同 stage。
- Allocator 复用 last-good shares 时用 `_allocator_signature()` 做拓扑+容量身份比对，bootstrap 退化为 zero shares，逻辑严谨。
- 每个 stage 的 `try/except` 只捕 `RecoverableControlError`；其他异常透传 — 符合 I-5 不变式。
- StabilityMonitor 用 `was_triggered_before` 区分"首次触发"vs"持续触发"，避免重复 event。

**轻微观察**：

- `_can_reuse_last_good_alloc` 使用 `1e-6` 容差，与其他模块（如 `weighted_balancer.py`）的容差不统一，可考虑提取为模块常量。
- `_adapter_exception_event` 内 `cause_type == fault_family`（详见 §5.3）。

### 3.2 `sre_control/events.py` (117 行)

- 11 个 event kinds 闭包 + counterexample，schema 紧凑；
- `validate_event` 对 `bounded_ls_residual` 与 `adapter_exception` 做了 kind-specific 字段强校验，其他 kind 走通用路径；
- `make_event` 不接受未注册的 kind，从源头闭包；

**反例文案**质量高 — 不只是"是什么"，更是"什么时候不要触发"，这对运维落地的可读性极有帮助。

### 3.3 `sre_control/stack_contract.py` (91 行) — 新增

清晰、紧凑、自洽。`event_stage_routes` 与 `stages[].event_kinds` 互为冗余，但 `analysis.evidence_report._contract_event_errors` 会做交叉验证。**良好。**

### 3.4 `sre_control/catch_adapter.py` (59 行) — 新增

`CatchLoadAdapter` 是这次评审最让我满意的设计之一：

- 仅是一层 SRE 词汇翻译，复用 `WeightedLoadBalancer` 的 bounded LS；
- 加 `sre_wrapper_for_catch_allocation` source tag 防混淆；
- 把 `local_states` 追加 `sre_catch_wrapper` 标识，traceability 完整；
- 完全不要求 `starship.catch_controller` 改动；

**避免了**做成"在物理层加一个 SRE schema 出口"的反模式。

### 3.5 `starship/ekf.py` (256 行)

- Joseph 形式 `(I−KH) P (I−KH)^T + K R K^T` 实现正确；
- `_stabilize_covariance` 用 `eigh` + clip 实现可选特征值地板；
- Mahalanobis 距离用 `solve(S, y)` 而非 `inv(S) · y`，数值更稳；
- 当 `LinAlgError` 时 `d_mahal = inf`，等价于 "gate 直接拒绝"，安全降级；

**观察**：`covariance_eigenvalue_floor` 默认是 `0.0`（关闭）；用户必须显式开启。对研究脚本可以接受，但若未来作为生产 EKF，建议 1e-12 或 1e-10 作为常态地板，避免协方差崩塌的"沉默失败"。

### 3.6 `starship/stability_monitor.py` (207 行)

- Manual-reset latch 语义清楚；
- `_history`/`_t_history` 同步窗口，平滑后向差分；
- `min_derivative_dt` 默认 `1e-9`，能挡掉调度器抖动；
- `triggered` 与 `consecutive` 分别有 `@property`，外部只读，封装良好。

### 3.7 `sre_control/weighted_balancer.py` (110 行)

- 使用 `scipy.optimize.lsq_linear`，bounded least squares；
- `bounded_ls_residual` event 携带 `rps_residual_fraction` 与 `demand_satisfied` 布尔，给上游提供"合法但不够"的语义；

**潜在风险**：`lsq_linear` 在极端病态输入下可能抛 `ValueError` 等，目前未被 `RecoverableControlError` 包装，会直接冒泡到 `stack.step()` 的 `except` 之外。建议补一层 `try/except` 包装为 `RecoverableControlError`，保持降级路径完整。

### 3.8 `analysis/evidence_manifest.py` (191 行) — 新增

- 把 S10/S11/S12 + stack_contract 写入 `event_evidence_manifest.json`；
- 每个 artifact 附 `sha256` + `size_bytes`，字节身份记录；
- 路径全部用 `_artifact_ref` 转 repo-relative，跨机器可复现；

**评估**：设计正确，输出形式标准化。

### 3.9 `analysis/evidence_report.py` (1662 行) — 新增

逻辑覆盖：

- top-level shape；
- 研究/合约 ID 闭包集合；
- 必需字段、字段类型、固定值；
- 数值范围（fraction ∈ [0,1]、计数 ≥0）；
- artifact key parity、扩展名；
- 路径可移植性、repo 内包含；
- JSON/JSONL/PNG 可解析；
- runtime event payload 合法；
- stack contract scope、stage event-kind registry、observed trace event 路由；
- count 一致性；
- artifact 字节身份（SHA-256 + size 重算比对）。

**评估**：**功能上无可挑剔**，是这次提交最大的工程产出之一。

**可维护性问题**：1662 行单文件偏大，建议在下一轮拆分为：

```
analysis/evidence_report/
  __init__.py        # main, _cli, public entry
  shape.py           # _manifest_shape_errors 系列
  consistency.py     # _consistency_errors / _contract_consistency_errors
  s10_checks.py
  s11_checks.py
  s12_checks.py
  io_helpers.py      # _resolve_artifact / _is_number / _is_sha256 / ...
```

详见 §6。

### 3.10 `analysis/s11_catch_sre_wrapper.py` & `s12_sre_replay.py`

两个研究均严格沿用"baseline → after → diagnostics → banner"四段式，可读性好。

- S11 设计三个 case 类（feasible / total_overload / placement_infeasible），每类 40 个随机样本，覆盖到位；
- S12 用固定的 19-tick fixture（`analysis/fixtures/sre_replay.jsonl`），3-tick 复合事件窗口测试多信号联动，确实是 replay 级证据。

---

## 4 · 证据边界纪律

这是本项目最值得称道的部分。三道防线：

1. **命名**：所有合成研究输出带 `synthetic_*` 标签；
2. **代码**：`stack_data_contract.production_claim=False`；`evidence_report` 拒绝 contract 中出现 production 关键字；
3. **文档 lint**：`scripts/evidence_boundary_lint.py` 用正则匹配过度宣称短语（如 `proves production readiness`、`official SpaceX implementation`），并支持否定上下文 8 行回看；`tests/test_synthetic_evidence_boundaries.py` 把 7 份 live review 文档加入 lint 集合。

**评估**：这种"显式拒绝表演性宣称"的纪律在研究项目里极为难得。值得作为模板沉淀。

**轻微观察**：`OVERCLAIM_PATTERNS` 是固定 7 条正则，扩充时建议补单元测试避免遗漏。

---

## 5 · 风险与潜在改进

### 5.1 [P2] `evidence_report.py` 单文件过大

- **现状**：1662 行，13 类函数职责。
- **风险**：未来新增研究（S13、S14）时单文件不可控；新人 onboarding 成本高。
- **建议**：见 §6.1 拆分方案。

### 5.2 [P2] `tests/test_evidence_manifest.py` 90 KB

- **风险**：单测试文件过大；同 5.1。
- **建议**：按 study/contract 拆分为 4 个文件（s10 / s11 / s12 / contract）。

### 5.3 [P3] `adapter_exception` 中 `cause_type` 与 `fault_family` 冗余

- **代码**：`sre_control/stack.py:140-141` 中 `fault_family=cause_type`，二者在当前实现下永远相等。
- **风险**：未来加更多 fault 分类时，二者语义会混淆。
- **建议**：要么删除一个；要么明确 `adapter_family`（来源 stage 家族）、`fault_family`（故障类别）、`cause_type`（recoverable vs adapter_input 二分）三者分工。

### 5.4 [P3] `WeightedLoadBalancer.allocate` 未包装 `lsq_linear` 失败

- **现状**：`scipy.optimize.lsq_linear` 在病态输入下可能抛 `ValueError`/`RuntimeError`。
- **风险**：未被 `stack.py` 的 `except RecoverableControlError` 捕获，会以未分类异常冒出。
- **建议**：在 `weighted_balancer.allocate` 内 try/except 把求解失败包装为 `RecoverableControlError`，并在 `stack.py` 给一个 zero-allocation fallback。

### 5.5 [P3] EKF `covariance_eigenvalue_floor` 默认为 0

- **现状**：`starship/ekf.py:43` 默认 `0.0`，等价于关闭地板。
- **风险**：研究使用者忘记开启时，重复低噪声更新可能让 P 缓慢塌缩，导致后续更新失去权重 — 沉默失败。
- **建议**：要么默认设为 1e-12；要么在 `test_ekf.py` 增加一个"长跑低噪声更新"的正则化测试，强制下游使用者意识到该开关。

### 5.6 [P2] 同步质量门计数依赖正则替换

- **现状**：`scripts/quality_gate_counts.py` 用 `replace_once` 在 7 个文档里做正则替换。
- **风险**：任何文档措辞变化或表格结构调整会让正则不匹配 → `RuntimeError: missing <label>`。
- **建议**：长期看可引入模板渲染（如 jinja2）或单一 source of truth + 自动注入；短期看，应当在 `RuntimeError` 信息里包含 file path 便于排查。

### 5.7 [P3] 复合事件 fixture 硬编码

- **现状**：`sre_replay.jsonl` 19 tick 是硬编码 JSONL，复合 incident `compound_telemetry_policy_capacity` 写在固定 3 行；测试用断言精确比对 5 类 expected_kind。
- **风险**：未来新增 incident 类时，fixture 与测试要并行修改；表达力 vs 维护成本失衡。
- **建议**：保留 fixture 文件作为冻结 baseline，但同时提供一个 Python builder（`build_replay_fixture(incidents=[...])`），让新增 case 走代码生成路径。

### 5.8 [P3] 未提供发布管线

- **codex 自评**已识别"if this repository starts publishing versioned artifacts, add release-pipeline automation"。
- **Opus 评审**同意这是 P3 — 当前没有版本制品需要分发，所以无急迫性。但 `test_release_hygiene.py` 已经在守护 `__version__` 与 spec 版本分离，做好了准备。

### 5.9 [P3] `LLM-WIKI/` 目录未跟踪

- `git status` 显示 `LLM-WIKI/` 为 untracked。
- 不确定是否打算纳入版本，还是临时本地素材。
- 建议确认归属：若是项目知识库，加入 git 并写 README；若是工作区，加入 `.gitignore`。

---

## 6 · 建议下一轮 codex 处理

### 6.1 [Priority 1] 拆分 `analysis/evidence_report.py`

**目标**：把 1662 行单文件按职责切到 5-7 个文件，每个 200-400 行，可独立单测。

**建议结构**：

```
analysis/evidence_report/
  __init__.py                  # 暴露 main, REPO_ROOT
  __main__.py                  # CLI 入口
  errors.py                    # 错误打印格式与 _is_* helper
  manifest_shape.py            # _manifest_shape_errors + _matches_manifest_type
  artifact_paths.py            # _resolve_artifact / _artifact_paths / _nonportable_*
  byte_identity.py             # _artifact_identity_errors
  s10_consistency.py           # s10-specific shape & consistency
  s11_consistency.py           # s11-specific shape & consistency
  s12_consistency.py           # s12-specific shape & consistency
  contract_consistency.py      # _contract_consistency_errors + _contract_event_errors
```

**配套**：保留 `analysis.evidence_report` 顶层 import，对外 API 不变。

**风险控制**：拆分应是纯 refactor，测试套件全绿即视为成功。建议先写一个"main() smoke" 测试，再做拆分。

### 6.2 [Priority 1] 拆分 `tests/test_evidence_manifest.py`

```
tests/test_evidence_manifest/
  __init__.py
  test_manifest_shape.py
  test_s10_consistency.py
  test_s11_consistency.py
  test_s12_consistency.py
  test_contract.py
  test_artifact_identity.py
```

### 6.3 [Priority 2] 整理 `adapter_exception` 字段语义

明确：

- `adapter_family`: stage 家族（observe/plan/...），与拓扑映射；
- `fault_family`: 故障类别（input/control/numerical/...），与处置映射；
- `cause_type`: 异常根因二分（adapter_input vs control_domain）。

更新 `events.py` 的 docstring + `EVENT_SCHEMA.md` 字段说明。

### 6.4 [Priority 2] 给 `WeightedLoadBalancer` 加 solver 异常包装

```python
try:
    res = lsq_linear(A, b, bounds=(lb, ub))
except (ValueError, RuntimeError) as exc:
    raise RecoverableControlError(...) from exc
```

stack.py 的 except 已经能处理 `RecoverableControlError`，所以这一步只是补完降级路径。

### 6.5 [Priority 3] EKF 默认协方差地板

把 `covariance_eigenvalue_floor` 默认值改为 `1e-12` 或在 `__post_init__` 里添加 deprecation-style warning。

### 6.6 [Priority 3] `quality_gate_counts.py` 模板化

把硬编码 replace_once 调用挪到一份 `quality_gate_targets.json` 配置里（path + regex + replacement template），运行时遍历执行。让"新增需同步的文档"成为配置而非代码改动。

---

## 7 · 验证证据

| 命令 | 结果 |
|---|---|
| `python -m pytest tests` | **249 passed in 133.15s** |
| `python -m analysis.run_all` | **All 12 studies finished in 3.45s** |
| `python -m analysis.evidence_manifest` | `wrote event_evidence_manifest.json` |
| `python -m analysis.evidence_report` | `artifact_check ok studies=3 files=8` |

详细日志见 [`QUALITY_GATE_VERIFICATION.md`](./QUALITY_GATE_VERIFICATION.md)。

---

## 8 · 结论

当前 codex 在 `spacex-session` 分支上的工程态满足以下条件：

- ✅ 全部质量门绿；
- ✅ 全部证据边界文档化、可程序化校验；
- ✅ I-1 ~ I-5 不变式由代码与测试守护；
- ✅ 跨研究证据 manifest + 字节身份 + schema 校验闭合；
- ✅ live docs lint 拦截过度宣称；
- ✅ 历史评审材料已显式标注为 historical context。

**建议**接受当前研究态作为下一轮迭代的稳态基线，并在下一轮 PR 内优先处理 §6.1 / §6.2 的拆分，让工程结构跟得上证据广度的成长。

---

**Opus 4.7 / 2026-05-25 / spacex-session @ 8d8e064**
