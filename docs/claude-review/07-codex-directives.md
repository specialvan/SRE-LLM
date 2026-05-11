# Codex 指令清单

> 这份文件是"下一轮 Codex 的必读"。执行 action items 前先过一遍。
> 规则的语气是**硬的**——不是建议，是约束。

## 开工前要做的 3 件事

1. **读 [00-executive-summary.html](./00-executive-summary.html)** — 5 分钟理解本轮所有结论。
2. **默念一次 [02-architecture-deep.html §9 Codex 心智模型](./02-architecture-deep.html#codex-mental)** — 绿黄红蓝四区。
3. **按顺序扫一遍 [01-findings.md](./01-findings.md) 的 P0 → P1 → P2** — 每条都要在 [05-action-items.md](./05-action-items.md) 里找到对应任务。

---

## ✅ DO · 必做清单

### D-01 · 先修 P0，再修 P1，最后 P2
顺序不能颠倒。P0 没解决就做 P1 只会让 CI 指标掩盖真问题。
- P0：AI-01 + AI-02；
- P1：AI-03a / AI-03b / AI-03c / AI-04；
- P2：AI-05 ~ AI-14。

### D-02 · 每个 PR 只解决一件事
- 不要同一个 PR 里"升级 nominal policy + 修 title mojibake"；
- 每个 AI-XX 独立 PR；
- commit message 带 AI 编号：`feat(AI-02): PredictiveBrakePolicy`。

### D-03 · 改 contract 必须同步文档
- 改 `trace.py` → 改 `trace-schema.md` + 同步 `04-contracts-catalog.md`；
- 改 benchmark payload → 改 `benchmark-metrics.md`；
- 改 status 枚举 → 改 [INV-G12](./03-invariants-catalog.md#inv-g12) + `04-status-enums.md` patch 已经列出所有要点。

### D-04 · 改跨层方程必须回归多模块
见 [02-architecture-deep.html §6](./02-architecture-deep.html#eq-arch) 的穿层方程表。跨层方程包括：
- E-06~E-10（动力学）
- E-23~E-25（博弈）
- E-29~E-32（barrier）
- E-35（T_inv）

改动其中任意一条，PR 描述必须包含"影响模块 + 回归测试"两节。

### D-05 · 每个 finding 关闭时引用 ID
PR 描述里明示："本 PR 关闭 F-P0-01 / AI-01。"
方便未来 archeology。

### D-06 · 每个 action item 完成后在 `.progress.json` 里标 done
详见 [05-action-items.md 末尾](./05-action-items.md#完成度追踪)。

### D-07 · 新增 invariant 走模板
见 [03-invariants-catalog.md 附录](./03-invariants-catalog.md#附新建-invariants-的模板)。
命名规则：
- 全局：`INV-G<seq>`；
- 模块：`INV-M-<MOD>-<seq>`；
- 契约：`INV-C-<名>`。

### D-08 · benchmark 结果作为对比基线
改动 nominal policy / CBF / T_inv 之后，必须跑 `python scripts/run_benchmark.py` 并把前后对比贴到 PR 描述里。

### D-09 · 保持向后兼容
- trace schema 只加字段，不删；
- VehicleParams 字段不删；
- status 值不删；
- 想改必须 bump schema_version 并在 CHANGELOG 写迁移。

### D-10 · Review 报告的 finding/AI 都要回复
若 Codex 不同意某条 finding，要在 PR 里显式写"为何不修 AI-XX"。不允许沉默跳过。

---

## ❌ DON'T · 禁令清单

### DN-01 · 不要通过放宽硬约束来"改善"指标
不允许：
- 调大 `cbf_alpha` 让 QP 找到解；
- 调小 `game.base_buffer` 让 barrier 门低；
- 调小 `BrakingDistanceBarrier.reaction` / `safety`；
- 调大 `invariant.gamma` 让 Lyapunov 容易通过；
- 调大 `invariant.tol` 让更多东西归类为 stable。

这些都是"把体温计调暖"。

### DN-02 · 不要给 Lyapunov V 塞距离项
[INV-G9](./03-invariants-catalog.md#inv-g9) 已经写死。第一版血泪史见 [equations-digest.html E-17](../equations-digest.html#e17)。

### DN-03 · 不要让 fallback 返回除刹停之外的 Control
[INV-G4](./03-invariants-catalog.md#inv-g4)。`Control(0, -jerk_max)` 是**数学上可证的终止出口**，换任何其他值都要重新证明可行性。

### DN-04 · 不要把 CBF 条件改成 loss
[INV-G8](./03-invariants-catalog.md#inv-g8)。硬约束就是硬约束，不能把 `dV/dt + γV` 加到 loss 里。

### DN-05 · 不要绕过 planner.step 调用 dynamics.step
[INV-G2](./03-invariants-catalog.md#inv-g2)。`scripts/check_invariants.py`（AI-11）会自动拦截。唯一合法例外：cbf / lyapunov 内部的 `h_dot`/`dV_dt` 求值，以及 benchmark 的 `_pure_e2e_step`（需标注）。

### DN-06 · 不要删 trace 字段
INV-G5。schema_version = "1.0" 已 freeze。加字段可以，删字段必须 bump 到 v2.0 + CHANGELOG。

### DN-07 · 不要在 auto_decide 代码里引入 ML 依赖
保持核心包只依赖 numpy + scipy。policy 升级用 numpy 能实现的 MPC 就够（AI-02 patch 01）。
想训 NN 的话新起 `auto_decide_ml/`，不要污染主包。

### DN-08 · 不要把 README/knowledge-base/architecture/handoff 的"入口"写成循环
按 [AI-10](./05-action-items.md#ai-10) 确定 primary entry。

### DN-09 · 不要在测试里调参数直到 xfail 变 pass
见 [patch 03](./06-suggested-patches/03-benchmark-assertions.md) 的 `strict=True`。测试意外通过会报错。正确做法是 AI-02 完成后显式删 xfail 标记。

### DN-10 · 不要把 summaizer/ 或类似非仓库内容提交到 git
[AI-03c](./05-action-items.md#ai-03c)。

---

## 🧭 决策树：遇到具体情况怎么办

### "我想让 benchmark 更好看"
→ 看 [01-findings F-P0-02](./01-findings.md#f-p0-02) 和 [patch 01](./06-suggested-patches/01-barrier-aware-policy.md)。
如果你想到的办法不是"升级 nominal policy"，先问自己：我在破坏哪条 INV？

### "我想加一个新的 barrier 类型"
→ 先看 [04-contracts-catalog 的 BarrierFunction protocol](./04-contracts-catalog.md)。
→ 再检查相对度分析（见 [equations-digest E-29~E-31](../equations-digest.html#e29)）。
→ 最后写两个测试：barrier h 单调性 + CBF filter 能用新 barrier 刹车。

### "我想改 VehicleParams"
→ 触发 [INV-G10](./03-invariants-catalog.md#inv-g10) 和 [INV-C-PARAM](./03-invariants-catalog.md#inv-c-param)。
→ 是整车 OTA 级变更，不是小改。
→ 要 bump 某个版本号并写 CHANGELOG。

### "我想改 schema"
→ 只加字段 → 不 bump。
→ 删字段/改语义 → bump major 版本 + CHANGELOG + 下游适配 PR。
→ 单独开 PR，不要混在其它改动里。

### "我看到一个 finding 我不同意"
→ 在 PR 描述里写明反对理由。
→ 在本文件末尾"讨论"节追加一段。
→ 不允许默默跳过。

---

## 期望的下一轮 PR 序列

```
PR-AI-03a  · chore(AI-03a): fix architecture.html title mojibake              (1 line)
PR-AI-03c  · chore(AI-03c): move summaizer/ to .local-artifacts               (2 file)
PR-AI-04   · docs(AI-04): add schema evolution policy to trace/benchmark docs (2 file)
PR-AI-03b  · feat(AI-03b): lock planner/cbf status enums + assertions         (+tests)
PR-AI-11   · ci(AI-11): static invariants scanner script                      (+tests)
PR-AI-01   · test(AI-01): SLO gate (xfail pending AI-02)                      (+tests)
PR-AI-02   · feat(AI-02): PredictiveBrakePolicy + wire into planner           (+tests)
                          removes xfail from AI-01 in same PR
PR-AI-12   · test(AI-12): forbidden status combinations                       (+tests)
PR-AI-14   · ci(AI-14): benchmark runner + log                                (script)
PR-AI-05   · docs(AI-05): architecture.html consumes metrics.json
PR-AI-07   · docs(AI-07): add failure tree + scenario matrix to architecture
PR-AI-08   · docs(AI-08): deep-dive §4.10 for trace.py
PR-AI-09   · chore(AI-09): mark _pure_e2e_step as sanctioned INV-G2 exception
PR-AI-10   · docs(AI-10): primary entry in README
PR-AI-06   · refactor(AI-06): expose trace._jsonable debug logging
PR-AI-13   · test(AI-13): graph eps cutoff regression
```

共 15 个 PR · 预估 2 ~ 3 轮工作量（每轮 3 ~ 5 个）。

---

## 讨论

（留给下一轮 Codex 写反馈 / 反对意见）

<!-- 若不同意上述某条 directive，在这里开新小节：

## Objection: D-07 要求过严
Codex: ...
-->

---

## 本文件的维护

- 下一轮 Claude review 会增补 "resolved findings" 一节；
- 本文件本身不应被 codex 无理由删改（规则层）；
- 若需要调整规则，Codex 应在讨论节提案，下一轮 review 采纳。
