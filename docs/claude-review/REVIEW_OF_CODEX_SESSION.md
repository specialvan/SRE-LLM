# Review of Codex's Session · Historical Session Review

> Historical review leaf from the 2026-05-12 Claude package; it is not the current handoff.
> Opus review should start from `docs/opus-review/HANDOFF.md`, then verify
> live status in `wiki/review-backlog.md`,
> `docs/codex-review/OPEN_RISKS.md`, and
> `docs/codex-review/QUALITY_GATES.md`.

> Reviewer 视角：带着 PR-REQUIREMENTS 与上一轮 HANDOFF 去评审 Codex 的 6 个提交。
> 结论先行：**P0 通过**。建议合并，附 3 条后续改进（不阻塞）。

---

## 1. 范围与节奏

Codex 在 `cf9c8dc` 之后连续推出 6 个语义聚焦的 commit，每次专门处理一件事：

| # | 提交 | 范围 |
|---|---|---|
| `4319a41` | 完善交接与契约文档 | 新增 `API_CONTRACTS.md` / `RUNTIME_STATES.md`，新增 `test_contracts.py`，修 `weighted_balancer.py` 的 `numpy.bool_` |
| `70c1d6a` | 补齐控制栈运行态追踪 | `SREControlStack.step()` 新增 `runtime.states / events / degraded` |
| `5e0a94e` | 下沉三个本地 failure trace | fusion / guardrail / balancer 各自暴露 events |
| `2c82861` | 补齐剩余三个本地事件 | canary / autoscaler / switcher 的 events |
| `1ee8ae5` | 统一 runtime event schema | 新增 `events.py`、`EVENT_SCHEMA.md`、`test_event_schema.py` |
| `d9cecb7` | 补齐静态原语的事件 | pool / topology 接入 events |

**节奏评价**：非常好的单原子提交序列，先装"管道"再装"事件源"再"收口 schema"，最后把未补的静态原语对齐。回滚任何一步都不破坏前一步。

---

## 2. 质量门全部通过

| Gate | 结果 |
|---|---|
| `pytest tests -q` | **31 passed**（11 starship + 2 contracts + 2 event_schema + 15 sre_control + 1 mpc/ekf/...） |
| `python -m analysis.run_all` | 9 studies finish in ~2.7 s，SUMMARY.txt 包含 §SRE 端到端 |
| `python -m scripts.build_kb` | 8 机制图 + 8 GIF 重建成功 |
| `python -m examples.demo_sre_loop` | 完整跑完 12 tick，trace 打印 |
| HTML well-formed | `html.parser` 验证 issue=[] leftover=[] |
| JSON serialization | stack entry 完整 json.dumps 通过，numpy.bool_ 已 fix |

---

## 3. 架构评估

### 3.1 事件 schema 抽象是干净的

`sre_control/events.py` 是个**两行接口** (`make_event`, `validate_event`) + 一张表 (`EVENT_COUNTEREXAMPLES`)。好处：

- 新增 event kind 强制要填 counter-example（`make_event` 会抛 ValueError）
- `test_event_schema.py` 把"每种 kind 必须真实被 adapter 生成 + 必须通过 validate + 必须有 counter-example"固化成三条不变量
- 每个 adapter 不用自己发明字段名

**小推荐**：`REQUIRED_EVENT_FIELDS` 是 tuple，`EVENT_COUNTEREXAMPLES.keys()` 是 dict 的 keys，建议把 `"kind in EVENT_COUNTEREXAMPLES"` 的判断抽成 `is_known_kind(kind: str) -> bool` 让语义更明显。非阻塞。

### 3.2 依赖方向正确

`starship/` **没有反向** import `sre_control/events.py`。`CatchController` 的残差留在 `info["alloc_residual"]`，避免物理层被迁移层污染。这是正确的依赖方向，文档里也有明确声明（`EVENT_SCHEMA.md §2` / `ARCHITECTURE.md §1.6`）。

### 3.3 运行态状态机体现在 trace 里，不体现在代码里

`RUNTIME_STATES.md §2` 把每个 adapter 拆成独立状态机（predict/update/skip_update 等），但代码里没有 explicit state enum；每个 adapter 用字符串 list 记状态流转。

**评价**：对"审查 trace"这个目的，字符串 list 够用；没必要早早引入 enum。但当未来要做 incident replay / state dashboard 时，建议把 `local_states` 的 allowed 值也集中在 `events.py` 里，参考 Codex 对 event kinds 的做法。

### 3.4 降级路径的语义

```
local event (adapter) → runtime.events (stack) → DEGRADED_* 状态标签 → runtime.degraded 总开关
```

这个四层映射很清晰。一个细节：`stack.py` 里 `guardrail` 触发时没有把 `DEGRADED_` 状态加进 `runtime_states`——只有事件进了 `runtime_events`。看 `stack.py L86-90`：

```python
if (audit["cone_violated_before"] or audit["magnitude_violated_before"]):
    runtime_events.extend(audit.get("events", []))
```

对比其他条件（fusion / autoscaler / canary / balancer）都加了 `runtime_states.append("DEGRADED_*")`。**这是一处不一致**，不一定是 bug，但会让 `runtime.degraded` 在 guardrail 主动投影时仍然为 False（只加 event 不加状态）。建议增加 `DEGRADED_GUARD` 让降级标识对齐。

---

## 4. 测试质量

### 4.1 `test_contracts.py`

三个测试恰好覆盖最关键的三条契约：

- **trace 完整性**：所有必需字段齐全、可 JSON 序列化
- **降级传播**：sensor 缺失 → `DEGRADED_OBSERVE` + event upward
- **canary 事件传播**：rollout 拒绝 → `DEGRADED_PLAN` + event upward

**不足**：没有覆盖 `guardrail` 单独触发的事件传播（因为上面提到的栈侧状态缺失）；没有覆盖 `allocator` 饱和触发事件。建议补 2 个测试：

```python
def test_guardrail_events_propagate_upward(): ...
def test_allocator_saturation_propagates_upward(): ...
```

### 4.2 `test_event_schema.py`

`test_all_runtime_events_follow_shared_schema` 最关键：它真实调用每个 adapter 的极端路径触发事件，而不是伪造事件字典验证 schema——这保证了"字典定义的 kind"和"代码路径实际产生的 kind"严格一致。

`test_every_event_kind_has_a_specific_counterexample` 用了 `len >= 60` 和 `"Do not" in counterexample` 两个微弱签名。够用，但有点脆——如果未来 counter-example 改成 "Avoid ..." 就会挂。非阻塞。

### 4.3 `test_sre_control.py`

`test_topology_state_repairs_invalid_quaternion_event` 直接给了零四元数 `[0,0,0,0]`，验证 repair 路径——好测试，因为 `np.linalg.norm([0,0,0,0]) = 0 < 1e-12` 走 non-finite 分支。

---

## 5. 文档评估

- `API_CONTRACTS.md`：每个模块有 Public surface / Contract / State / Failure modes / Counter-example 五件套。结构非常工整；作为"新人入职第一份读物"是合格的。
- `RUNTIME_STATES.md`：先给栈级 FSM，再给模块级 FSM，再给传播矩阵。层次清晰。
- `EVENT_SCHEMA.md`：该历史评审时覆盖 8 个 kind × 5 列表格；当前 registry 已扩展到 11 个 kind。
- `ARCHITECTURE.md`：mermaid 图 + Refine Backlog 很有条理。
- `CODEX_HANDOFF.md` / `CODEX_REVIEW_REPORT.md`：作为 session 级交接页合格；前者偏 "下一步"，后者偏 "证据表"。

**小瑕疵**：
- `ARCHITECTURE.md §4.5 Refine Backlog` 第 5 条和 `CODEX_HANDOFF.md §下一步` 第 3 条都提到"未来如果做 CatchController 的 SRE wrapper"——同一条建议写了两次，可以收敛到 handoff 即可。
- `API_CONTRACTS.md §2.9 CatchController` 其实是 starship 物理层，放在 SRE API Contracts 文档里会让读者误以为它有 SRE event 映射。建议显式加"**不属于 sre_control，但保留契约给未来 wrapper 参考**"。

---

## 6. 发现的实际缺陷与建议

| 严重度 | 位置 | 描述 | 建议 |
|---|---|---|---|
| **中** | `stack.py :: step()` L86-90 | guardrail 触发事件时没加 `DEGRADED_GUARD` 状态 | 与其他分支对齐，加 `runtime_states.append("DEGRADED_GUARD")` |
| **小** | `run_all.py` L41 | hardcoded `"All 8 studies"` 但现在是 9 | 已修：改成 `f"All {len(STUDIES)}"` |
| **小** | `test_event_schema.py` | `"Do not" in counterexample` 文案签名脆 | 改成 `counterexample.startswith(("Do not", "Avoid"))` 或去掉该断言，靠 `len >= 60` 足矣 |
| **小** | `API_CONTRACTS.md §2.9` | CatchController 被放在 SRE contracts 里容易误导 | 加一句"属 starship 物理层，不反向依赖 sre_control" |
| **小** | `ARCHITECTURE.md + CODEX_HANDOFF.md` | CatchController wrapper 建议重复 | 收敛到 handoff |

---

## 7. 数字证据（本轮未动）

```
§1 pos_err                148.3    →  2.125e-6     ×1.43e-8
§3 angle_rmse             0.0558   →  5.7e-7       ×1.02e-5
§4 cone_violations        97.4%    →  0%
§5 vel_rmse               481.1    →  51.07        ×0.106
§6 final_err              0.0119   →  3.46e-7      ×2.9e-5
§8 saturation             33.75%   →  0%
§SRE slo_violation_pct    25       →  10           ×0.4  (mean_replicas +44%)
```

Codex 没有触碰这些数字（数据层未动），只是在外围加了可观测性和契约层。这种"稳证据、加仪表盘"的节奏符合工程复利的好习惯。

---

## 8. 评审结论

**通过**。合并建议：

1. 立即可合：当前 31 passed，三条质量门绿灯，证据链完整。
2. 合并前建议改一条：`stack.py` 的 `DEGRADED_GUARD` 对齐（中等严重度的一致性问题）。
3. 可放到下轮：测试补两例（guardrail / allocator 的栈级事件传播）、文档收敛"CatchController wrapper"提法。

**工程复利判断**：这一轮是典型的"外围加层次"，没有改动任何 starship 数学支柱或 before/after 证据，把前面证据的可观测性和契约固化下来。这正是把一套"跑通的方案"变成"可交接工件"的必经一步。下一轮可以考虑把 failure-state 的 before/after 也做成独立分析 (`analysis/s10_failure_trace.py`)，让 events 本身可视化。

---

评审者签字：人类 Reviewer，2026-05-12。
