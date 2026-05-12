# V2_Knowledge CHANGELOG

> 本文件记录 knowledge hub 的版本演进。每个版本都是快照，**不删除旧版本**。

---

## V2 · 2026-05-12 · 当前版本

**生成 agent**：Claude Opus 4.7（Review & Knowledge Pack round）
**触发事件**：Codex round-1 完成 trace / benchmark 契约后，Claude 做第一轮深度 review，同时建立统一入口层。

### 2026-05-12（Codex 补丁 · AI-11/AI-12/AI-13/AI-14 守门收口）

Codex 在 P0/P1 收口后继续完成 CI 与回归守门：

| AI | 类型 | 改动 |
| --- | --- | --- |
| AI-11 | CI 守门 | 新增 `scripts/check_invariants.py`，通过 `tests/test_invariants.py` 接入 pytest，覆盖 INV-G2 / INV-G9 / INV-G10 |
| AI-12 | 状态组合 | 新增 forbidden T_inv/CBF status 测试，并修复 `(non_increasing, fallback_brake)` 语义漂移 |
| AI-13 | 图回归 | 新增 `test_edges_respect_eps_cutoff`，锁定 `_edges` 不保留 `w < EPS` |
| AI-14 | benchmark artifact | 新增 `scripts/run_benchmark.py`，支持 JSON artifact + benchmark log newest-first 摘要 |

canonical benchmark（n=50 seed=0）在 AI-12 语义修正后更新：

- `collision_rate = 0.00%`；
- `planner_emergency_rate = 4.82%`（与 `cbf_fallback_rate` 对齐，demo SLO 仍通过）；
- `cbf_fallback_rate = 4.82%`；
- `planner_best_effort_rate = 63.76%`；
- 32 / 32 tests 绿。

### 2026-05-12（Codex 补丁 · AI-01/AI-02/AI-03b 收口）

Codex 接手 Claude review pack 后关闭 P0 与剩余 P1：

| AI | 类型 | 改动 |
| --- | --- | --- |
| AI-01 | 测试守门 | `tests/test_benchmark_metrics.py` 的 availability SLO 断言已启用，移除 `xfail(strict=True)` |
| AI-02 | 策略升级 | 新增 `auto_decide/policies/PredictiveBrakePolicy`，`StructuralPlanner` 默认包裹 `GradientPolicy` |
| AI-03b | 契约封闭 | `PLANNER_STATUS_VALUES` / `CBF_STATUS_VALUES` 常量 + strict trace 校验；新增 `best_effort` 恢复态 |

canonical benchmark（n=50 seed=0）更新：

- `collision_rate = 0.00%`；
- `planner_emergency_rate = 4.18%`（demo SLO 通过，生产 SLO 仍未达）；
- `cbf_fallback_rate = 4.82%`（demo 与生产告警线通过）；
- `planner_best_effort_rate = 63.76%`（新观测项，说明恢复态仍偏高）；
- `mean_step_time_ms = 1.86 ms`；
- `TRACE_SCHEMA_VERSION = "1.1"`（status enum 扩展，字段集合不变）；
- 27 / 27 tests 绿。

本补丁不放宽 `cbf_alpha` / `game.base_buffer`，也不把硬约束改成 loss；风险从“硬刹停泛滥”转移为“Lyapunov 恢复态仍多”，下一轮应进入 AI-11 / AI-12 / AI-14。

### 2026-05-12（12:00 补丁 · 亲手清理 P1 易改项）

Claude 在 V2 发布后同日清理了 4 项与策略无关的 action items，减轻 Codex 下一轮负担：

| AI | 类型 | 改动 |
| --- | --- | --- |
| AI-03a | 文档 | `docs/architecture.html` title mojibake `路` → `·` |
| AI-03c | 项目卫生 | `summaizer/` → `.local-artifacts/` + `.gitignore` 更新 |
| AI-04 | 契约文档 | `trace-schema.md` / `benchmark-metrics.md` 各加"Schema Evolution"节 |
| AI-09 | 代码注释 | `examples/compare_e2e_vs_structural.py` 标注 INV-G2 合法例外 |

同时产出：

- `docs/claude-review/08-benchmark-log.md` 建立 **canonical baseline**（n=50 seed=0）；
- `state.json` 字段 `action_items.done_by_claude_post_review` 记录已完成；
- `state.json` `benchmark` 指标用 n=50 的更稳定结果（原 n=20）。

**当时未触动**：所有 P0 / 剩余 P1 / P2 仍由 Codex 推进。不改算法、不改契约语义。（见上方 Codex 补丁：AI-01/02/03b 已完成。）

### 新增（V2 初版）

- `docs/V2_Knowledge/index.html` — 统一入口（5 角色分流 + 快速动作 + 快速统计）
- `docs/V2_Knowledge/01-current-state.html` — 当前状态一页概览（代码健康度 / SLO / action items 进度）
- `docs/V2_Knowledge/02-agent-triage.html` — 5 角色独立 SOP（Codex / Reviewer / SRE / Researcher / Observability）
- `docs/V2_Knowledge/03-doc-graph.html` — 33 文档 + 代码的全景关系图
- `docs/V2_Knowledge/state.json` — 机器可读状态快照（含 benchmark 最新实测数据、action items 列表、契约清单）
- `docs/V2_Knowledge/CHANGELOG.md` — 本文件
- `docs/V2_Knowledge/_style.css` — 共享样式

### 同时交付（见 V2 前置 commit）

- `docs/claude-review/` — 14 文件的完整 review pack（在 V2 hub 里作为"本轮 review"引用）
  - findings / action-items / invariants / contracts / patches / directives
- `docs/codex-handoff.md` — 更新为 V2，指向 V2_Knowledge 与 claude-review
- `README.md` — 新增 "Primary Entry" 段

### 关键决策

1. **V2_Knowledge 作为独立目录**，不覆盖已有 docs/。下一轮若需要 V3 会建 `V3_Knowledge/` 并把本目录改名为 `V2_Knowledge_archived/`。
2. **state.json** 作为机器可读入口，所有动态状态（benchmark 数字 / action items 列表）都可由此读出。
3. **agent 分流**：5 个角色 × 独立 SOP，避免通读整个文档栈。
4. **文档不删**：`knowledge-base.html`（v1 总览）保留，由 V2 index 主动引用；不追求"V2 完全替代 v1"。

### 对应代码状态（V2 初版基线，已被上方 Codex 补丁刷新）

- 19 / 19 tests 绿；
- `planner_emergency_rate = 42.5%`（SLO 违约，已生成 AI-02 任务）；
- `cbf_fallback_rate = 23.1%`（SLO 违约）；
- trace v1.0 / benchmark.metrics.v1 契约稳定。

### 对下一轮的承诺

- `state.json` 的字段在 `v2_knowledge.state.v1` 内向后兼容；
- `trace.jsonl` / `benchmark-metrics.json` 的字段集合不删；
- V2_Knowledge 目录内文件不重命名（如改名需 bump 到 V3）。

---

## V1 · 2026-05-11 · 已归档（逻辑上）

**物理位置**：`docs/knowledge-base.html` 作为 v1 总览
**触发事件**：auto-decide 论文 → 工程包落地后的首次知识库建立

### V1 核心产出

- `docs/knowledge-base.html` — SRE 评审报告 + Codex checklist
- `docs/deep-dive.html` — 9 模块算法级拆解
- `docs/equations-digest.html` — 35 方程手册
- `docs/sre-adaptation.html` — 9 P-模式
- `docs/FORMULA_MAP.md` · `docs/DESIGN.md` · `docs/codex-handoff.md`（v1）

### V1 → V2 演进动机

- Codex 在 v1 基础上扩展了 `trace.py` / `benchmark.metrics.v1` / `architecture.html` 等新契约，但没有给下一轮 agent 一个"统一入口"；
- v1 的 `knowledge-base.html` 仍然是 10k 行文档，新接手者消化成本高；
- v2 把"给新 agent 的推荐路径"从"隐含在文档交叉引用里"升级为"显式 landing page + 角色分流"。

### 兼容性

- v1 文档全部保留；
- v2 不引入破坏性变更，只提供更友好的入口。

---

## V3 · 预计 · 下一轮 Claude review 之后

**触发条件**：Codex 完成 AI-01 + AI-02 + 大部分 P1 任务后。

### 预计变更

- 新建 `docs/V3_Knowledge/`；
- 当前 `V2_Knowledge/` 改名为 `V2_Knowledge_archived/`；
- `state.json` 的 benchmark 数据反映新的（降低后的）emergency_rate；
- `agent-triage` 里 Codex 角色的"已知陷阱"加入 "V2 → V3 吸取的经验"；
- 旧 finding 标记为 resolved。

### 维护节奏

- **频繁更新**（每次 PR）：`01-current-state` 的 action items 进度；`state.json` 的测试数 / benchmark 数。
- **中频更新**（每周）：`agent-triage` 的"开工前准备"路径；`doc-graph` 的新增文档。
- **低频更新**（每轮 review）：`CHANGELOG`；新建 `V<N>_Knowledge/`。

---

## 维护契约

### 任何 agent 若要修改本目录，必须：

1. 在 CHANGELOG 顶部加一条版本记录；
2. 不重命名已有文件（除非建 V3）；
3. `state.json` 的 schema_version 遵循 [schema 演进策略](../benchmark-metrics.md)；
4. 保留 v1 所有文档的链接不断。

### CI 可以自动做的事（AI-14 runner 已具备后）：

- 扫描本目录所有相对链接是否断链；
- 比较 `state.json` 中 `benchmark.structural.*` 与最新实测差距，触发 `01-current-state` 更新提醒；
- 扫描 `progress` 字段，提醒长期未完成的 action items。
