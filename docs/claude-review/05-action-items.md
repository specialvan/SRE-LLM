# Action Items

> 本轮 Review 产出的全部任务，按优先级排序。每条有：ID / Title / Priority / Owner / Depends / 验收标准 / 建议实现路径。
> Codex 下一轮可直接把这份文件当 sprint log 用。

## 进度快照（2026-05-12 · Codex AI-01/02/03b 收口后）

| 状态 | 计数 | 项目 |
| --- | --- | --- |
| ✅ done | 11 | AI-01 · AI-02 · AI-03a · AI-03b · AI-03c · AI-04 · AI-09 · AI-11 · AI-12 · AI-13 · AI-14 |
| 🔄 unassigned | 5 | AI-05 · AI-06 · AI-07 · AI-08 · AI-10 |
| **P0 剩余** | **0** | — |
| **P1 剩余** | **0** | — |

详见 [V2_Knowledge/01-current-state.html](../V2_Knowledge/01-current-state.html) 的 action items 进度表（需同步更新）。

## 索引

| ID | 标题 | Priority | Depends | Patch |
| --- | --- | --- | --- | --- |
| [AI-01](#ai-01) | benchmark metrics 红线断言 | P0 | — | [patch 03](./06-suggested-patches/03-benchmark-assertions.md) ✅ **done 2026-05-12** |
| [AI-02](#ai-02) | 升级 nominal policy 到 barrier-aware | P0 | — | [patch 01](./06-suggested-patches/01-barrier-aware-policy.md) ✅ **done 2026-05-12** |
| [AI-03a](#ai-03a) | 修 architecture.html title mojibake | P1 | — | — ✅ **done 2026-05-12** |
| [AI-03b](#ai-03b) | 锁 T_inv / CBF status 枚举并加 assert | P1 | — | [patch 04](./06-suggested-patches/04-status-enums.md) ✅ **done 2026-05-12** |
| [AI-03c](#ai-03c) | 处置 summaizer/ 目录 | P1 | — | — ✅ **done 2026-05-12** |
| [AI-04](#ai-04) | trace & benchmark schema 演进策略 | P1 | — | — ✅ **done 2026-05-12** |
| [AI-05](#ai-05) | benchmark metrics JSON 注入 architecture.html | P2 | AI-01 | — |
| [AI-06](#ai-06) | trace._jsonable 调试可见性 | P2 | — | — |
| [AI-07](#ai-07) | architecture.html 补失败决策树与场景矩阵 | P2 | — | [02-architecture-deep.html](./02-architecture-deep.html) 参考 |
| [AI-08](#ai-08) | deep-dive.html 给 trace.py 独立一节 | P2 | — | — |
| [AI-09](#ai-09) | 标注 _pure_e2e_step 为 INV-G2 合法例外 | P2 | — | — ✅ **done 2026-05-12** |
| [AI-10](#ai-10) | hub 文档明示 primary entry | P2 | — | — |
| [AI-11](#ai-11) | CI 脚本：grep-based invariant 扫描 | P2 | AI-03b | [patch 05](./06-suggested-patches/05-ci-invariants.md) ✅ **done 2026-05-12** |
| [AI-12](#ai-12) | T_inv / CBF 非法组合的单元测试 | P2 | AI-03b | — ✅ **done 2026-05-12** |
| [AI-13](#ai-13) | 图剪枝一致性回归 | P3 | — | — ✅ **done 2026-05-12** |
| [AI-14](#ai-14) | benchmark JSON 固化为 CI artifact | P3 | AI-01 | [patch 02](./06-suggested-patches/02-benchmark-ci.md) ✅ **done 2026-05-12** |

---

## AI-01 · benchmark metrics 红线断言

- **Priority**：P0
- **Status**：✅ done 2026-05-12。`tests/test_benchmark_metrics.py::test_structural_pipeline_respects_availability_budget` 已移除 `xfail(strict=True)`，作为 demo SLO 守门。
- **Finding**：[F-P0-01](./01-findings.md#f-p0-01)
- **Why**：当前 benchmark 的 `planner_emergency_rate = 42.5%` 与 `cbf_fallback_rate = 23.1%` 都远超 SLO。没有 CI 断言的话，下一轮 Codex 可能把它调回"好看"。
- **What**：
  1. 在 `tests/test_benchmark_metrics.py` 新增 `test_structural_pipeline_respects_availability_budget`；
  2. 断言 `structural.planner_emergency_rate ≤ 0.10`；
  3. 断言 `structural.cbf_fallback_rate ≤ 0.10`；
  4. 断言 `structural.collision_rate == 0`；
  5. 测试**初次运行会失败**（这是预期），将其标记为 `pytest.mark.xfail(strict=True, reason="AI-02 完成前预期失败")`；
  6. AI-02 完成后去掉 xfail。
- **验收**：
  - `pytest tests/test_benchmark_metrics.py -v` 输出 xfail 或 pass（不能 xpass 也不能 fail）；
  - `docs/benchmark-metrics.md` 末尾加 "SLO 阈值参考" 表。
- **非目标**：
  - 不通过调宽 CBF/game 参数让测试通过（那就违背了 AI-02）。

---

## AI-02 · 升级 nominal policy 到 barrier-aware

- **Priority**：P0
- **Status**：✅ done 2026-05-12。已新增 `auto_decide/policies/PredictiveBrakePolicy` 并在 `StructuralPlanner.__post_init__` 自动包裹默认 `GradientPolicy`；canonical benchmark 达到 demo SLO：`collision_rate=0%`、`planner_emergency_rate=4.82%`、`cbf_fallback_rate=4.82%`。
- **Finding**：[F-P0-02](./01-findings.md#f-p0-02)
- **Why**：当前 `GradientPolicy` 与 CBF 结构性不匹配，benchmark 里 42.5% 的命令都触发 emergency。
- **What**：实现 `auto_decide/policies/barrier_aware.py` 中的 `BarrierAwareMPC` 或 `PredictiveBrakePolicy`（详见 [patch 01](./06-suggested-patches/01-barrier-aware-policy.md)）。
- **最小可行版本**（推荐先做）：
  ```python
  class PredictiveBrakePolicy(GradientPolicy):
      """在 GradientPolicy 基础上，若前瞻 T_look 秒后 h_min < 0 则主动减速。"""
      def __init__(self, *args, barrier_fns, t_lookahead=0.5, **kw):
          super().__init__(*args, **kw)
          self.barrier_fns = barrier_fns
          self.t_lookahead = t_lookahead

      def __call__(self, state, graph=None):
          u = super().__call__(state, graph)
          # 前瞻：若保持当前 u 的路径在 t_lookahead 后违反任何 barrier，改为减速
          future = predict_future(state, u, self.t_lookahead)
          if any(b.h(future) < 0 for b in self.barrier_fns):
              u = Control(u.steer, min(u.jerk, -2.0))
          return u
  ```
- **验收**：
  - benchmark 指标：`planner_emergency_rate ≤ 10%` 且 `collision_rate == 0`（在默认场景 n=50 seed=0 下）；
  - 新测试 `tests/test_policies.py::test_predictive_brake_avoids_emergency`；
  - AI-01 的 xfail 去掉后仍通过。
- **非目标**：
  - 不要追求 `emergency_rate == 0`（那需要完美预测器）；
  - 不要引入外部 ML 依赖（sklearn/torch），最小 numpy 即可。

---

## AI-03a · 修 architecture.html title mojibake

- **Priority**：P1
- **Finding**：[F-P1-01](./01-findings.md#f-p1-01)
- **What**：一行改动。
  ```diff
  -<title>auto-decide 路 Detailed Architecture</title>
  +<title>auto-decide · Detailed Architecture</title>
  ```
- **验收**：浏览器 tab 无乱码。

---

## AI-03b · 锁 T_inv / CBF status 枚举并加 assert

- **Priority**：P1
- **Status**：✅ done 2026-05-12。`auto_decide.trace` 已定义 `PLANNER_STATUS_VALUES` / `CBF_STATUS_VALUES`，`build_trace_record(..., strict=True)` 会拒绝未知枚举；新增 `best_effort` 用于区分 CBF 非 fallback 的 Lyapunov 恢复帧，并按 schema 规则 bump 到 trace v1.1。
- **Finding**：[F-P1-02](./01-findings.md#f-p1-02)
- **What**：
  1. 在 `auto_decide/trace.py` 顶部加：
     ```python
     PLANNER_STATUS_VALUES = frozenset({
         "stable", "relaxed_exp", "relaxed", "non_increasing",
         "best_effort", "emergency_brake",
     })
     CBF_STATUS_VALUES = frozenset({"nom_ok", "qp_ok", "fallback_brake"})
     ```
  2. 在 `build_trace_record` 末尾加（可选，基于 `strict` 参数）：
     ```python
     if record["status"] is not None:
         assert record["status"] in PLANNER_STATUS_VALUES, ...
     if record["cbf_status"] is not None:
         assert record["cbf_status"] in CBF_STATUS_VALUES, ...
     ```
  3. `docs/trace-schema.md` 改枚举为 bullet list（见 F-P1-02 的 diff）；
  4. `docs/codex-handoff.md` 把自己维护的 status 列表改为"见 trace-schema.md"。
- **验收**：
  - 新增测试 `test_trace.py::test_status_values_are_from_enum`；
  - 移除 `codex-handoff.md` 里自维护的 status 枚举（避免漂移）。

---

## AI-03c · 处置 summaizer/ 目录

- **Priority**：P1
- **Finding**：[F-P1-03](./01-findings.md#f-p1-03)
- **What**（推荐选项 B）：
  1. `git mv summaizer .local-artifacts`（或随便一个明确"非仓库内容"的名）；
  2. `.gitignore` 加 `.local-artifacts/`；
  3. `git status` 干净。
- **验收**：`git status` 无 untracked。

---

## AI-04 · trace & benchmark schema 演进策略

- **Priority**：P1
- **Finding**：[F-P2-02](./01-findings.md#f-p2-02)
- **What**：在 `docs/trace-schema.md` 与 `docs/benchmark-metrics.md` 末尾都加 "Schema Evolution" 小节，规则如下：
  ```markdown
  ## Schema Evolution
  - 新增字段：保持 `schema_version` 不变（同 v1.x）；
  - 删字段或改字段语义：必须 bump 到 v2.0 并在 CHANGELOG 注明迁移；
  - `schema_version` 字段本身永不删；
  - 下游读 JSON 必须先 check `schema_version`，再用字段。
  ```
  同时在 [04-contracts-catalog.md](./04-contracts-catalog.md) 的 "契约变更规则" 引用这一节。
- **验收**：两份文档都有 Schema Evolution 段落。

---

## AI-05 · benchmark metrics JSON 注入 architecture.html

- **Priority**：P2
- **Finding**：[F-P2-04](./01-findings.md#f-p2-04)
- **Depends**：AI-01 完成（metrics.json 稳定生产）
- **What**：在 `architecture.html` §4.1 Symptom → refine target 表下方加一个 placeholder，JS 里 `fetch("../artifacts/benchmark-metrics.json")` 然后高亮当前症状。
- **验收**：本地有 `artifacts/benchmark-metrics.json` 时，`architecture.html` 会显示 "当前 emergency_rate = XX% · 指向 AI-02"；无 metrics 时显示"请先跑 benchmark"。

---

## AI-06 · trace._jsonable 调试可见性

- **Priority**：P2
- **Finding**：[F-P2-01](./01-findings.md#f-p2-01)
- **What**：把 `except Exception: pass` 改为带 logging：
  ```python
  import logging
  _LOG = logging.getLogger(__name__)
  ...
  try:
      return _jsonable(value.item())
  except Exception as e:
      _LOG.debug("trace _jsonable item() failed for %r: %s", type(value), e)
  ```
- **验收**：`logging.getLogger("auto_decide.trace").setLevel(logging.DEBUG)` 时能看到失败原因。

---

## AI-07 · architecture.html 补失败决策树与场景矩阵

- **Priority**：P2
- **Finding**：[F-P2-03](./01-findings.md#f-p2-03)
- **What**：把 [02-architecture-deep.html §3](./02-architecture-deep.html#scenario-matrix) 的场景矩阵与 [§4](./02-architecture-deep.html#failure-tree) 的失败决策树搬到 `architecture.html` 作为新章节。
- **验收**：`architecture.html` 的 TOC 增加 "Failure tree" / "Scenario matrix" 两条。

---

## AI-08 · deep-dive.html 给 trace.py 独立一节

- **Priority**：P2
- **Finding**：[F-P2-05](./01-findings.md#f-p2-05)
- **What**：
  - 选项 A：在 `deep-dive.html` 加一个 §4.10 "Cross-cutting · trace"；
  - 选项 B：把 `docs/trace-schema.md` 的内容 inline 进 deep-dive.html。
- **推荐**：A。
- **验收**：deep-dive.html 有 10 个章节而不是 9 个。

---

## AI-09 · 标注 _pure_e2e_step 为 INV-G2 合法例外

- **Priority**：P2
- **Finding**：[F-P2-06](./01-findings.md#f-p2-06)
- **What**：在 `examples/compare_e2e_vs_structural.py` 顶部加注释：
  ```python
  """...
  .. note::
     This file intentionally calls ``dyn.step`` directly in
     ``_pure_e2e_step`` to establish a baseline without CBF/T_inv.
     This is the only sanctioned INV-G2 exception outside of
     ``cbf.py``/``lyapunov.py``/``planner.py``.
  """
  ```
- **验收**：AI-11 的 grep 脚本能跳过这个文件。

---

## AI-10 · hub 文档明示 primary entry

- **Priority**：P2
- **Finding**：[F-P2-07](./01-findings.md#f-p2-07)
- **What**：`README.md` 顶部写清楚：
  ```markdown
  ## Primary Entry

  - 技术评审起点：[docs/knowledge-base.html](./docs/knowledge-base.html)
  - 开工起点：[docs/architecture.html](./docs/architecture.html)
  - 下一轮接手起点：[docs/codex-handoff.md](./docs/codex-handoff.md)
  ```
- **验收**：三份 hub 文档互相链接时明确"你从哪来"。

---

## AI-11 · CI 脚本：grep-based invariant 扫描

- **Priority**：P2
- **Status**：✅ done 2026-05-12。已新增 `scripts/check_invariants.py`，并通过 `tests/test_invariants.py` 接入 pytest，当前覆盖 INV-G2 / INV-G9 / INV-G10。
- **Depends**：AI-03b、AI-09
- **What**：`scripts/check_invariants.py`，见 [patch 05](./06-suggested-patches/05-ci-invariants.md)：
  ```bash
  # 检查 INV-G2：除了 cbf/lyapunov/planner/benchmark，不应有 dynamics.step 调用
  python scripts/check_invariants.py
  ```
- **验收**：
  - 脚本返回 0 退出码；
  - pyproject.toml 或 CI config 增加 `pytest` 前运行此脚本。

---

## AI-12 · T_inv / CBF 非法组合的单元测试

- **Priority**：P2
- **Status**：✅ done 2026-05-12。`tests/test_planner.py::test_no_forbidden_tinv_cbf_status_combinations` 已落地；该测试发现并修复了 `(non_increasing, fallback_brake)` 语义漂移，当前 fallback 帧统一归入 `emergency_brake`。
- **Depends**：AI-03b
- **What**：`tests/test_planner.py` 加：
  ```python
  def test_no_forbidden_status_combinations():
      """INV-G13: stable/relaxed_* 绝不与 cbf_status=fallback_brake 同时出现。"""
      traces = run_demo_trace()  # helper
      forbidden = {
          ("stable", "fallback_brake"),
          ("relaxed_exp", "fallback_brake"),
          ("relaxed", "fallback_brake"),
          ("non_increasing", "fallback_brake"),
          ("best_effort", "fallback_brake"),
      }
      for t in traces:
          assert (t["status"], t["cbf_status"]) not in forbidden
  ```
- **验收**：当前 benchmark trace 能通过此测试（做健康检查）。

---

## AI-13 · 图剪枝一致性回归

- **Priority**：P3
- **Status**：✅ done 2026-05-12。`tests/test_graph.py::test_edges_respect_eps_cutoff` 验证 `_edges` 不保留 `w < EPS` 的边。
- **Finding**：[INV-M-GRAPH-2](./03-invariants-catalog.md#inv-m-graph-2)
- **What**：`test_graph.py` 加一个测试，验证 `_edges` 中不包含 `w < EPS` 的边：
  ```python
  def test_edges_respect_eps_cutoff():
      g = InteractionIntentGraph()
      ... # 构造几个边界情况
      g.update()
      for edge in g.edges:
          assert edge.weight >= g.EPS
  ```
- **验收**：新测试通过。

---

## AI-14 · benchmark JSON 固化为 CI artifact

- **Priority**：P3
- **Status**：✅ done 2026-05-12。已新增 `scripts/run_benchmark.py`，支持写出 `artifacts/benchmark-metrics.json` 并把摘要 newest-first 插入 `docs/claude-review/08-benchmark-log.md`；helper 由 `tests/test_benchmark_runner.py` 覆盖。
- **Depends**：AI-01
- **What**：见 [patch 02](./06-suggested-patches/02-benchmark-ci.md)。在 CI 里跑 benchmark，产出的 JSON 保存为 artifact + 附加到 `docs/claude-review/08-benchmark-log.md` 形成历史基线。
- **验收**：
  - `docs/claude-review/08-benchmark-log.md` 每次 CI 后追加一段 diff。

---

## 完成度追踪

建议 Codex 维护一个 `docs/claude-review/.progress.json`：
```json
{
  "AI-01": "done",
  "AI-02": "done",
  "AI-03b": "done",
  "AI-03a": "done",
  "AI-11": "done",
  "AI-12": "done",
  "AI-13": "done",
  "AI-14": "done",
  ...
}
```
下轮 review 用来对比本轮。
