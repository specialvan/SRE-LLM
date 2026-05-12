# Codex Handoff - GAN Matchmaking / SRE Self-Iteration

## 当前状态
- 当前分支：`gan-session`
- 当前方向：把 matchmaking / rating / decision 方案稳定成可审计、可训练、可回放的 SRE 决策流水线
- 现状：九个机制的语义映射、架构拆解、模块契约、状态生命周期、实施路线图、ADR 已经成体系
- 最新进展：runtime artifact 版本化已经接入在线决策链路，`Decision.artifact_version`、SQLite 决策审计表、训练产物元数据、runtime hydrate 都已打通；golden replay corpus 已覆盖 fallback / fitted artifact / freeze / rollback / escalation，并新增 critical-tier canary downgrade、risk-WARN canary、shadow strategy hold 三个事故叙事样本；artifact manifest 已校验 feature_names / shape / Cox baseline，不合格会降级为 bootstrap 并写入 trace；新决策 trace 已记录 `trace.input.context/config`；SQLite replay export 现在支持 fitted artifact promotion：导出前校验 artifact bundle、可归档 artifact 文件、写 `replay_artifact_manifest.json`，并在 fixture 中记录 `requires_artifact_version` / `artifact_bundle`；服务入口已支持 `GAN_LEASE_FILE` 本地 writer lease，Kubernetes 文档和 ADR 已明确单写者边界；新增 `sre/primitives.py` 与 `docs/sre-control-primitives.md`，把九机制抽象为可迁移的 SRE 控制原语

## 机制地图
| 数学机制 | SRE 映射 | 代码位置 |
|---|---|---|
| TrueSkill | 服务可靠性评分，维护 `mu / sigma` | `gan_matchmaking/trueskill.py`，`sre/self_iteration.py` |
| EOMM | 发布策略选择，偏向保留/稳定 | `gan_matchmaking/eomm.py`，`training/retention.py`，`sre/artifacts.py` |
| Dynamic K | 连续成功后的调参衰减 | `gan_matchmaking/dynamic_k.py` |
| PCA | 观测压缩，提取异常模式 | `gan_matchmaking/pca_hidden.py`，`sre/self_iteration.py` |
| GNN | 依赖关系与 blast radius 分析 | `gan_matchmaking/gnn_synergy.py`，`sre/self_iteration.py` |
| Handicap | 风险折损后的胜率估计 | `gan_matchmaking/handicap.py` |
| Entropy | 过滤“过于确定”的候选 | `gan_matchmaking/entropy_match.py`，`sre/self_iteration.py` |
| Cox Survival | 故障/流失风险预警 | `gan_matchmaking/survival.py`，`training/cox.py`，`sre/artifacts.py` |
| Minimax / BP | SLO 与稳定性之间的策略张力 | `gan_matchmaking/minimax_bp.py`，当前仍偏研究态 |

## Replay Corpus
- 入口 + 命名约定 + catalog：[`tests/fixtures/replay/README.md`](../tests/fixtures/replay/README.md)
- 测试：`tests/test_replay_corpus.py`（含 `test_fixture_naming_matches_convention`）
- 导出：`python -m gan_matchmaking.cli export-replay --state-db state.sqlite --correlation-id <id> --output tests/fixtures/replay/<scenario>_<kind>.json`
- fitted promotion：追加 `--allow-fitted-artifacts --artifact-dir <runtime-artifacts> --artifact-output-dir tests/fixtures/replay/<name>-artifacts`
- 边界：bootstrap 决策可直接导出成 standalone fixture；fitted artifact 决策必须显式允许并提供匹配 artifact bundle，导出器会校验版本和 manifest 后再归档

## 生产化模块
> Phase/PR 编号详见 [`docs/implementation-roadmap.md`](implementation-roadmap.md)；
> 本节只列"哪些文件已到生产形态、哪些仍偏研究态"，不重复 phase 定义。

### 已经接近生产形态
- `core/`：配置 / 错误 / 指标 / 日志 / seed
- `persistence/`：SQLite + memory 双实现，决策审计表带 `artifact_version`，migration 通过 idempotent guard 兼容遗留列（F-008 已修）
- `service/`：HTTP boundary 完整，含 `/healthz`、`/readyz`（含 lease-healthy 翻转）、`/metrics`、`/v1/observe`、`/v1/decide`；`handle_decide` 走 `ReleaseContext.from_dict` 公共 API（F-007 已修）
- `sre/self_iteration.py`：主决策链路 + artifact hydrate + decision persist + trace 输入快照；shadow/advisory 在边界后才发 metric / log（F-002 已修）
- `sre/artifacts/`：拆分为 metadata / retention / cox / bundle 四个子模块（F-006 已修），rating scaling 常数带 version 合同（F-005 已修），runtime manifest + feature contract 校验失败会写 `trace["artifacts"]["validation_errors"]`
- `sre/leases.py`：本地 writer lease + TTL + 后台续租 + on-failure 回调（F-001 已修）
- `sre/replay.py`：从 SQLite 审计行导出 replay fixture，含 fitted artifact promotion
- `training/`：Cox / Retention 训练 + 权重 + 元数据（含 rating_scaling_version）
- `tests/fixtures/replay/`：8 个 golden fixture + README 命名约定 + naming-convention 测试（F-010 已修）

### 仍偏研究态
- `minimax_bp.py`：解释性辅助层，不是主生产路径
- `gnn_synergy.py`：轻量图推理，不是完整图服务
- EOMM / Cox 特征空间已共享 feature builders，但还需要更多真实观测校准

## 风险与边界
1. **训练/运行特征不完全同构**
   - Cox 训练已经切到 runtime 同构的 6 维语义
   - EOMM 训练已复用 runtime match config / history vector
   - 后续重点是用真实观测校准，而不是再改接口形状

2. **artifact 与 fallback 的切换要可见**
   - 线上必须能看出当前是 artifact 路径还是 bootstrap 路径
   - `trace["artifacts"]` 是主入口
   - 当前 loader 已对 feature contract 做硬校验；坏 artifact 会显式降级

3. **决策审计和幂等性**
   - `correlation_id` 不能乱复用
   - 熔断短路场景要避免重复主键
   - 只有记录了 `trace.input.context` 的新审计行能自动导出 replay fixture
   - fitted artifact 决策需要匹配 artifact bundle，否则导出器会拒绝 promotion

4. **SQLite 仍是单进程友好，不是跨进程协调方案**
   - 服务入口已有本地 `FileLease` 护栏
   - 真要多实例并发，需要外部分布式 lease / lock + 外部数据库
   - 不能把本地 lease 当成跨节点一致性方案

5. **shadow / advisory 模式不能丢 trace**
   - 这两种模式是可观察性工具，不是“悄悄改结果”

## 可迁移抽象
这套方案可以抽象成一条通用的 SRE 控制回路：

1. **信号采集**
   - 业务 / 依赖 / 观测 / 历史
2. **压缩与评分**
   - PCA / TrueSkill / Handicap / Synergy
3. **风险门控**
   - Entropy / Cox / freeze / budget / breaker
4. **策略选择**
   - EOMM / rule table / fallback
5. **审计落盘**
   - trace + decision + artifact_version + replay fixture export
6. **离线再训练**
   - observation log -> artifact -> runtime hydrate

这个结构可以迁移到发布控制、容量调度、故障分流、巡检节流、告警降噪、回滚决策等场景。

## 控制原语目录
- 代码：`gan_matchmaking/sre/primitives.py`
- 文档：`docs/sre-control-primitives.md`
- 核心抽象：
  - `belief_state_estimator`
  - `objective_aware_strategy_ranker`
  - `adaptive_gain_scheduler`
  - `latent_signal_compressor`
  - `graph_blast_radius_scorer`
  - `risk_adjusted_probability_scorer`
  - `information_value_gate`
  - `time_to_incident_forecaster`
  - `adversarial_policy_arbitrator`
- 作用：把 GAN 九机制从“算法列表”提升为可被其它 SRE 控制面复用的能力目录

## 下一步
1. **✅ B+A2 本轮已关闭** (commits `704765d` + `6834ab3`, 2026-05-12)：F-001 / F-002 / F-003 / F-004 全部 resolved。收尾报告见
   [`docs/claude-review/2026-05-spec-completion.md`](claude-review/2026-05-spec-completion.md)，
   `pytest -q` = 123 passed, `bench p99` = 1.03 ms。
2. **✅ C+A2 本轮已关闭** (2026-05-12)：F-005 / F-006 / F-007 / F-008 / F-009 / F-010 全部 resolved。
   收尾报告：[`docs/claude-review/2026-06-spec-completion.md`](claude-review/2026-06-spec-completion.md)；
   `pytest -q` = 138 passed，`bench p99` = 1.39 ms；新增 ADR-0008
   [artifact rating scaling compatibility](adr/0008-artifact-rating-scaling-compat.md)。
3. V3 Knowledge 差量快照：[`docs/V3_Knowledge/knowledge-base.html`](V3_Knowledge/knowledge-base.html)
   （本轮 PR 落地后，请把 pending PR 状态翻成 resolved (commit `<sha>`)，
   然后冻结该目录）；系统全景仍读
   [`docs/V2_Knowledge/knowledge-base.html`](V2_Knowledge/knowledge-base.html)。
4. 下一轮评审可开 `docs/claude-review/2026-07-session-review.md` 与
   `docs/V4_Knowledge/`。本轮没有新增 blocking finding；建议覆盖
   [`docs/implementation-roadmap.md#5-next-delivery-target`](implementation-roadmap.md#5-next-delivery-target)
   列出的 4 项（incident replay 扩展 / 分布式 lease 原型 / artifact bundle 存储策略 / 真实观测校准）。

## Claude 评审结论（2026-05 session）
- 评审报告：[`docs/claude-review/2026-05-session-review.md`](claude-review/2026-05-session-review.md)
- 结构化 findings：[`docs/claude-review/findings.md`](claude-review/findings.md)（P1 / P2 / P3 分级）
- Follow-up PR 清单：[`docs/claude-review/action-items.md`](claude-review/action-items.md)
- 测试覆盖缺口：[`docs/claude-review/test-coverage-gaps.md`](claude-review/test-coverage-gaps.md)

评审结论是 **merge with the P1 fix, then land 3 follow-up PRs**。evaluation 评分：交付度 ★★★★★、测试质量 ★★★★☆、契约清晰度 ★★★★★、抽象迁移能力 ★★★★★、生产鲁棒性 ★★★☆☆、文档结构 ★★★☆☆。

## 可执行 Spec（B+A2，2026-05）· 已完成 ✅
- 完成报告：[`docs/claude-review/2026-05-spec-completion.md`](claude-review/2026-05-spec-completion.md)
- Spec 入口：[`docs/claude-review/spec/README.md`](claude-review/spec/README.md)
- 需求（EARS-A2）：[`docs/claude-review/spec/requirements.md`](claude-review/spec/requirements.md)
- 设计（组件 / 时序）：[`docs/claude-review/spec/design.md`](claude-review/spec/design.md)
- 任务 checkbox（29 条 T-XXX）：[`docs/claude-review/spec/tasks.md`](claude-review/spec/tasks.md)
- 验证命令 + 快照：[`docs/claude-review/spec/verification.md`](claude-review/spec/verification.md)
- 代码补丁草案：[`docs/claude-review/patches/`](claude-review/patches/) — F-001 / F-002 / F-003 各一份 before/after + 测试 shape

本轮覆盖 F-001 (合入前必修) + F-002 / F-003 (上产前必修) 全部已 resolved。
codex 已按 `spec/tasks.md` 顺序执行，各 PR 合入的 commit sha 在
`findings.md` 对应条目的 status 字段中登记。下一轮评审请开
`docs/claude-review/2026-06-session-review.md` 与 `docs/V3_Knowledge/`
（V2 快照冻结，不再变更）。

## 交接建议
- **先读 V2 知识库（一页全览）**：[`docs/V2_Knowledge/knowledge-base.html`](V2_Knowledge/knowledge-base.html) ← 新建，包含系统全景 / 决策流 / trace schema / findings / spec / 补丁入口
- **先读评审**：`docs/claude-review/README.md` → `2026-05-session-review.md` → `findings.md`（10 分钟）
- **再看 Spec**：`docs/claude-review/spec/README.md` → `requirements.md` → `tasks.md`（15 分钟）
- **准备改代码**：`docs/claude-review/patches/F-001-lease-refresh.md`（直接给出 before/after）
- **背景补强（可选）**：`docs/architecture/README.md` → `02-decision-flow.md` → `03-trace-schema.md`
- **最后做事**：按 F-005~F-010 的优先级开下一轮 PR；本轮 B+A2 三条 blocker 已在 `gan-session` 分支 resolved

这会比从数学模块倒着看更快进入真实控制面。
