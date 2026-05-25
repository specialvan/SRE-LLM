# 执行摘要 — Opus v2.0 深度评审

**评审对象**：spacex 仓库中 codex 工程包当前快照
**评审入口**：`docs/opus-review/OPUS_REVIEW_PACKET.md`
**评审日期**：2026-05-26
**评审分支**：`spacex-session`（against `attention-residuals-session`）
**前序基线**：Opus v1.0 评审（F01–F42）

---

## 一、Quality Gate 实测

| 命令 | 期望 | 实测 | 状态 |
|---|---|---|---|
| `python -m pytest tests -q` | 276 passed | `276 passed in 152.50s` | ✅ |
| `python -m analysis.run_all` | All 12 studies finished | `All 12 studies finished in 4.02s` | ✅ |
| `python -m analysis.evidence_manifest` | wrote manifest | `wrote ...event_evidence_manifest.json` | ✅ |
| `python -m analysis.evidence_report` | `artifact_check ok studies=3 files=8` | 同上 | ✅ |
| `python -u -m scripts.quality_gate_counts` | `quality gate pytest count: 276` | 同上 | ✅ |

**结论**：当前快照在本机环境下所有声明的门禁全部通过。

---

## 二、v1.0 Resolved 项 line-level 复核结果

**P0/P1 高优 5 项**：

| ID | 验收点 | 结论 |
|---|---|---|
| F01 | 终端 share 在 safety_margin 下不漂移 | HOLDS（几何上恒等） |
| F02 | balancer solver 失败包装为 RecoverableControlError | **PARTIAL**：`_matrix()` 调用位于 try 外，post-construction mutate 可能漏掉 |
| F03 | EKF 奇异 innovation 协方差走 gated no-op | HOLDS（提前 return 不污染状态） |
| F04/F25 | adapter_family 单一真源来自 `stack_data_contract().event_stage_routes` | HOLDS（6 处 call site 都走同一 helper） |
| F05 | `safe_action` L2 范数 = RPS 标量；`zone_target` = 分布 | HOLDS（contract 已贯穿 docstring/consumer） |

**P2/P3 评审者 / 数值类 14 项**：F07、F10、F14、F16、F18、F19、F21、F23、F32、
F33、F37、F39、F42、F11/F12 全部 **HOLDS**。F39 的实现是 `lower()` 而非 regex，
描述用词需要修正，但行为正确。

详见 `02-resolved-findings-spot-check.md`。

---

## 三、本轮新发现（F50–F60）

| ID | 严重度 | 区域 | 一句话描述 |
|---|---|---|---|
| F50 | **P1** | predictive_autoscaler | MPC 内部 plant ZOH 后 `Bd = B*dt` 让"u=1"等于 5 个 replicas，但 executor 只加 1 个；MPC 系统性欠下达 5× |
| F51 | **P1** | stability_monitor | 反向差分使用窗口最旧样本，单个尖峰污染后续 `window-1` 个 tick，恢复期仍报 violating |
| F52 | P2 | canary_scheduler | `_last_share=0.0` 默认值在首次 warm-start 时引入"幻影斜率"，污染 trust-region |
| F53 | **P1** | stack（与 stability_guard 协作） | `stability_violation` 触发后仅追加 `DEGRADED_PLAN` 状态，autoscaler / canary 仍按常规参数执行，红线只是装饰 |
| F54 | **P1** | slo_guardrail | NaN proposal 透传，无事件 / 无 raise，下游 RPS 标量、bounded-LS 静默感染 |
| F55 | P2 | stack | autoscaler `last_trace` 在 recoverable fallback 路径上停留在上一 tick，遥测与实际执行不一致 |
| F56 | P2 | signal_fusion | `_rejections` 按 `Signal.name` 做 key；同名重复 Signal 会互相覆盖计数 |
| F57 | P3 | stack | `_can_reuse_last_good_alloc` 对 NaN 不敏感，万一缓存里有 NaN 会被复用 |
| F58 | P3 | pool_planner | 精确饱和（`sigma == max_capacity` 且 `shortfall == 0`）跳过 `pool_capacity_clipped` 事件，"悬崖边没报警" |
| F59 | P3 | topology_state | `ring_angle_rad` 实际返回区间 `[-2π, 2π]`，与 docstring `[-π, π]` 不一致 |
| F60 | P3 | tests | OU 数值 sanity 测试用相同的解析公式回算 expected，是同义反复式自验证 |

详见 `03-new-findings.md`。

---

## 四、合并门禁判断

**当前快照可作为研究阶段（synthetic / scenario）PR 合入**，前提是以下任一：

- **方案 A（推荐）**：在 spacex-session 上追加 1 个修复 commit，至少修复
  F50 + F51 + F53 + F54 中的两项；其余条目移入 `docs/codex-review/OPEN_RISKS.md`。
- **方案 B**：维持现状合并，但必须把 F50-F54 全部以 P1 形式登记到
  `OPEN_RISKS.md`，且明确"在 production-readiness 论证前必须解决"。

**不应跳过的合并前动作**：

1. 修复 `s11_catch_sre_wrapper.png` 与 manifest SHA 漂移问题（执行
   `python -m analysis.evidence_manifest` 后再提交）。
2. 修正 `OPEN_RISKS.md` 中"No active numerical risk is currently recorded"
   表述 —— F50/F51/F54 显然是数值类风险。
3. 在 `wiki/review-backlog.md` 增加 v2.0 复核条目（链接本目录），让评审历史
   可追溯。

详见 `05-merge-gate-checklist.md`。

---

## 五、与 v1.0 评审的关系

- v1.0 找出的 P0/P1 类 bug（switcher overshoot、bounded-LS crash、EKF singular
  innovation、event taxonomy ambiguity、action vector ambiguity）**已经在
  代码层面真实修复**。v2.0 复核的负面结论集中在"次层"问题：plant-executor
  契约一致性、状态滞后、装饰性事件、NaN 透传。
- v1.0 的修复工程质量较高，但工程包文案中存在两处与实现机制不一致的描述（F39
  实现机制、F02 try 边界），应在下轮文档轮里更正。
- 本评审保留 v1.0 全部产出在 `docs/opus-review/v1.0/`，并将本轮 11 项新
  findings 编号自 F50 起，避免与 v1.0 编号冲突。
