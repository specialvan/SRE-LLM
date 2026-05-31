# 评审范围与基线

> Historical subreport from a prior Opus review packet; it is not the current handoff.
> Opus review should start from `docs/opus-review/HANDOFF.md`, then verify
> live status in `wiki/review-backlog.md`,
> `docs/codex-review/OPEN_RISKS.md`, and
> `docs/codex-review/QUALITY_GATES.md`.

## 1. 评审范围（in scope）

本轮 Opus 评审覆盖 codex 工程包当前主线 + 当前 worktree 已修改文件，
逐项验证 `docs/opus-review/OPUS_REVIEW_PACKET.md` 中宣称的状态。

### 1.1 代码层

| 层 | 范围 | 关注点 |
|---|---|---|
| `starship/` | `ekf.py`、`stability_monitor.py` | 数值稳定性、Joseph form、协方差地板、奇异 innovation gating |
| `sre_control/` | `stack.py`、`events.py`、`stack_contract.py`、`signal_fusion.py`、`predictive_autoscaler.py`、`canary_scheduler.py`、`slo_guardrail.py`、`weighted_balancer.py`、`catch_adapter.py`、`pool_planner.py`、`fast_switcher.py`、`stability_guard.py`、`topology_state.py` | 控制环契约、状态机、事件 schema、单位一致性、fallback 路径正确性 |
| `analysis/` | `evidence_manifest.py`、`evidence_report.py`、`run_all.py`、`s10/s11/s12_*` 等 | 证据制品 byte identity、JSON / JSONL / PNG 可解析性、scope 边界 |
| `tests/` | 全部 276 项 | 是否真实断言行为而非同义反复；是否覆盖对抗路径 |
| `scripts/` | `quality_gate_counts.py`、`evidence_boundary_lint.py` | gate 漂移防护、文案 lint |

### 1.2 文档层

| 类别 | 关键入口 |
|---|---|
| 评审入口 | `docs/opus-review/OPUS_REVIEW_PACKET.md`、`docs/opus-review/v1.0/*` |
| 工程移交 | `docs/codex-review/ENGINEERING_PACKET.md`、`docs/codex-review/OPEN_RISKS.md`、`docs/codex-review/QUALITY_GATES.md` |
| 知识库 | `docs/V2_Knowledge/knowledge-base.html`、`docs/EVENT_SCHEMA.md`、`docs/RUNTIME_STATES.md`、`docs/EVENT_EVIDENCE_MANIFEST.md`、`docs/STACK_DATA_CONTRACT.md` |
| 跨会话 wiki | `wiki/review-backlog.md`、`wiki/runtime-lifecycle.md`、`wiki/pillar-mapping.md` |

### 1.3 不在评审范围

- 性能基准（packet 已声明此仓库不做 production 性能宣称）
- 不覆盖 SpaceX 专有细节（packet 已声明这是公开材料复现）
- 制品在第三方 CI/CD 中的可移植性（packet 已自带 byte identity / SHA-256 校验）

---

## 2. 评审基线

| 维度 | 当前值 |
|---|---|
| 分支 | `spacex-session` |
| 比较对象（主分支） | `attention-residuals-session` |
| pytest 数量 | 276 |
| analysis studies | 12 |
| 跨研究证据制品数量 | 8 |
| Opus v1.0 findings 总数 | 42 |
| v1.0 已宣称 resolved 项 | 全部高优 + 14 项 P2/P3（详见 v1.0 LINE_LEVEL_FINDINGS.md） |
| v1.0 仍 open 项 | F06/F08/F09/F13/F15/F17/F20/F22/F24/F28/F31/F36/F38/F40/F41/B1/B2 |

---

## 3. 文档边界声明（评审者必读）

本仓库与本评审反复声明：

- 本仓库是公开资料下的研究与工程复现，**不代表 SpaceX 官方实现**。
- `analysis/` 产生的所有 before/after 数据是 **scenario / synthetic 证据**，
  不是生产证据。
- `starship/` 保持物理 / 数学层；`sre_control/` 是 SRE 迁移层，二者通过
  `tests/test_import_graph.py` 校验依赖方向。
- 单进程 `SREControlStack` 是研究 stack，不等同于生产分布式 control plane；
  `sre_control.stack_data_contract()` 已显式 `production_claim=false`。

任何把这些证据扩大解读为"可上线证明"或"等同官方实现"的下游表述，都应被
`scripts/evidence_boundary_lint.py` 拦截。

---

## 4. 评审方法

1. **入口阅读**：从 packet → engineering_packet → open_risks → quality_gates
   → review-backlog 依次拉直。
2. **门禁实测**：本机重跑 packet 列出的全部命令，比对输出与文档声明。
3. **resolved 项 spot-check**：把每一项 v1.0 findings 的"声明 resolved 证据
   文件 / 测试名"逐一打开读源码，验证不是"看起来过了"。
4. **独立审计**：在不被 v1.0 编号束缚的前提下，重新审 sre_control / starship
   核心 12 个模块，关注数值、契约、事件、fallback 路径四类问题。
5. **证据 / manifest 审计**：交叉验证 JSON 内容 vs 生成器 vs reviewer CLI vs
   markdown 契约 vs 测试断言。
6. **报告产出**：按 v1.0 评审目录格式落到 `claude-review/docs/v2026-05-26/`，
   编号从 F50 起避免冲突。

---

## 5. 与全局指令的对齐

| 指令来源 | 本轮如何对齐 |
|---|---|
| `~/.claude/CLAUDE.md`①  | 评审知识沉淀进 `claude-review/docs/v2026-05-26/`，按版本区分 |
| `~/.claude/CLAUDE.md`②  | codex 工程包评审报告汇总在本目录 |
| `~/.claude/CLAUDE.md`③  | 评审完成后将变动以详细中文 commit 提交 |
| `rules/common/agents.md` | 使用了 4 个并行 subagent 做 resolved 复核 / 新隐患 / manifest 审计，主线汇总 |
| `rules/common/coding-style.md` | 评审中标注了 immutability 违例（F56 / weighted_balancer mutation 旁注） |
