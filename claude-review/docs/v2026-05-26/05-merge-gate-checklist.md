# 合并门禁清单 — Opus v2.0

> Historical subreport from a prior Opus review packet; it is not the current handoff.
> Opus review should start from `docs/opus-review/HANDOFF.md`, then verify
> live status in `wiki/review-backlog.md`,
> `docs/codex-review/OPEN_RISKS.md`, and
> `docs/codex-review/QUALITY_GATES.md`.

> 基于本轮评审结论，对 `spacex-session` 是否可以并入主线给出门禁判断与建议
> 路径。

---

## 合入判定

| 维度 | 当前快照 | 判定 |
|---|---|---|
| 测试套件 | 276 passed | ✅ |
| analysis 套件 | 12 studies 全过 | ✅ |
| Quality gate 命令链 | 全过 | ✅ |
| Opus v1.0 P0/P1 修复闭环 | F01/F03/F04/F25/F05 全 HOLDS；F02 PARTIAL | ⚠️（窄缝隙） |
| Opus v1.0 P2/P3 修复闭环 | 14/14 全 HOLDS | ✅ |
| 本轮新发现 | 11 项 finding；其中 4 项 P1 | ⚠️ |
| 证据 / manifest 一致性 | 8 文件 byte identity OK；G1 process-trap 存在 | ⚠️ |
| 文档边界声明 | 已被 evidence_boundary_lint 拦截 | ✅ |

**判定**：当前快照**可作为研究阶段 PR 合入**，但建议按下列路径之一执行
合入前动作。

---

## 推荐合入路径

### 路径 A（推荐，"修后合"）

1. 在 `spacex-session` 上增 1 个 commit 修复 F50 + F53（或 F51 + F54）任一
   组合。两组都覆盖了"控制语义"与"数值健康"两类风险。
2. 把剩余 P1 / P2 / P3 finding 全部登记到 `docs/codex-review/OPEN_RISKS.md`
   的"Numerical Risks" / "Modeling Risks"两节中，并在表中追加 ID（F50…F60）。
3. 在 `docs/codex-review/OPEN_RISKS.md` 修正"No active numerical risk is
   currently recorded"表述 —— F50 / F51 / F54 显然是数值类。
4. 修复 `docs/opus-review/v1.0/...` 中关于 F39 的"regex"描述（机制误述）。
5. 在 `wiki/review-backlog.md` 末尾追加 v2.0 评审记录入口，链接本目录。
6. 执行 `python -m analysis.evidence_manifest && python -m analysis.evidence_report`
   保证 manifest 与 PNG 字节一致后再 commit。

### 路径 B（"先合后修"）

1. 不改代码，但必须把 F50 + F51 + F53 + F54 全部以 P1 形式登记到
   `OPEN_RISKS.md`，并明确"在 production-readiness 论证前必须解决"。
2. 同步 1) F39 描述更正；2) `OPEN_RISKS.md` 表述更正；3) `wiki/review-backlog`
   入口追加。
3. 在 PR 描述中显式声明"此次合入不涉及 closed-loop 控制语义增强；F50–F54
   作为已知风险随合入入主线"。

### 不推荐

- 直接合入但不登记新 findings：评审历史会断层，下游 reviewer 会重复发现。
- 全部修复后再合：F58 / F59 / F60 不影响研究阶段使用，没必要拖延合入。

---

## 必须的合入前操作（不可省）

```bash
# 1) 重新生成 manifest 并与制品对齐
python -m analysis.run_all
python -m analysis.evidence_manifest
python -m analysis.evidence_report

# 2) 重跑 gate counts
python -u -m scripts.quality_gate_counts

# 3) 重跑全套测试确认无回归
python -m pytest tests -q
```

期望输出：

```text
quality gate pytest count: 276
artifact_check ok studies=3 files=8
276 passed in <time>
```

---

## 合入后立刻要做（不阻塞合入但要落计划）

| 任务 | 责任目录 | 优先级 |
|---|---|---|
| 修复 F50 autoscaler 单位错配 + 加 plant/executor 一致性测试 | `sre_control/predictive_autoscaler.py`、`tests/test_sre_control.py` | P1 |
| 修复 F51 stability_monitor 反向差分 + 恢复期回归测试 | `starship/stability_monitor.py`、`tests/test_stability_monitor.py` | P1 |
| 修复 F53 `stability_violation` 接入 closed-loop 或显式声明 observe-only | `sre_control/stack.py`、`sre_control/stability_guard.py` 文档 | P1 |
| 修复 F54 NaN proposal 拒绝路径 | `sre_control/slo_guardrail.py`、新增 schema 路径 | P1 |
| 修复 F52 canary warm-start 幻影斜率 | `sre_control/canary_scheduler.py` | P2 |
| 修复 F55 / F56 telemetry / signal name 唯一性 | `sre_control/stack.py` × `signal_fusion.py` | P2 |
| F57 / F58 / F59 / F60 进 OPEN_RISKS 即可 | 文档 | P3 |
| G1 PNG 确定化或 quality gate 自愈合 | `scripts/quality_gate_counts.py` 或 `analysis/` 写入 | P2 |
| G3 浮点 `!=` 改 ε 比较 | `analysis/evidence_report.py` | P3 |

---

## 触发回滚 / 紧急止血的条件

只要出现以下任一情形，应立即在主线发紧急 PR：

- 任一现有 276 测试在主线 CI 上 red。
- `analysis.evidence_report` 在主线 CI 上 red 但 worktree 本地 green
  → 命中 G1 process-trap，按 G1 处置。
- `OPEN_RISKS.md` 中存在 P1 风险却未登记本轮 F50–F54 任一项 → 缺评审一致性。

---

## 与 v1.0 的连续性

本评审结果与 v1.0 评审一脉相承：

- v1.0 找到的所有 P0 / P1 bug 都已实质性修复。
- v2.0 找到的 P1 是 v1.0 评审未触及的"次层"问题（控制语义、单位契约、状态
  滞后、NaN propagation），不属于 v1.0 修复回归。
- 评审节奏：v1.0 = "深读已存在代码"；v2.0 = "在 v1.0 修好的代码上做对抗
  路径推演"。建议未来 v3.0 评审重点放在"closed-loop 行为验证 + 集成测试 +
  线上 telemetry 假设核实"。
