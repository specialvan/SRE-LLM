# Codex Handoff - GAN Matchmaking / SRE Self-Iteration

## 当前状态
- 当前分支：`gan-session`
- 当前方向：把 matchmaking / rating / decision 方案稳定成可审计、可训练、可回放的 SRE 决策流水线
- 现状：九个机制的语义映射、架构拆解、模块契约、状态生命周期、实施路线图、ADR 已经成体系
- 最新进展：runtime artifact 版本化已经接入在线决策链路，`Decision.artifact_version`、SQLite 决策审计表、训练产物元数据、runtime hydrate 都已打通；golden replay corpus 已覆盖 fallback / fitted artifact / freeze / rollback / escalation；artifact manifest 已校验 feature_names / shape / Cox baseline，不合格会降级为 bootstrap 并写入 trace；新决策 trace 已记录 `trace.input.context/config`，并新增 SQLite 审计行导出 replay fixture 的工具与 CLI

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
- 入口：`tests/fixtures/replay/*.json`
- 测试：`tests/test_replay_corpus.py`
- 导出：`python -m gan_matchmaking.cli export-replay --state-db state.sqlite --correlation-id <id> --output tests/fixtures/replay/<name>.json`
- 覆盖：bootstrap fallback、fitted artifact、freeze hold、budget rollback、unknown strategy escalation
- 作用：把“可回放”从 runbook 描述推进到可执行回归资产
- 边界：bootstrap 决策可直接导出成 standalone fixture；fitted artifact 决策默认拒绝导出，除非显式允许并在回放环境提供匹配 artifact bundle

## 生产化模块
### 已经接近生产形态
- `core/`
  - 配置、错误类型、指标、日志、seed 管理都比较完整
- `persistence/`
  - SQLite / memory 双实现
  - 决策审计表已支持 `artifact_version`
- `service/`
  - HTTP boundary 已可用
  - 健康检查、准备就绪、观测写入、决策查询都齐了
- `sre/self_iteration.py`
  - 主决策链路可运行
  - 已接 runtime artifact hydrate
  - 已把决策落回存储
  - 已在 trace 中写入可回放输入快照
- `sre/artifacts.py`
  - 已支持 runtime artifact manifest 校验
  - 校验失败会跳过对应 artifact，并把错误写入 `trace["artifacts"]["validation_errors"]`
- `sre/replay.py`
  - 已支持从 SQLite `decisions` 审计行导出 replay fixture
  - 会识别缺失 `trace.input.context` 的旧审计行，避免伪造不可复现样本
- `training/`
  - 已能从 store 训练 Cox / Retention，并输出权重 + 元数据
- `tests/fixtures/replay/`
  - 已有第一组 golden replay fixtures，可作为事故复盘和回归基线

### 仍偏研究态
- `minimax_bp.py`
  - 更像解释性辅助层，不是主生产路径
- `gnn_synergy.py`
  - 现在是轻量图推理，不是完整图服务
- `EOMM / Cox` 的特征空间已经开始共享 feature builders，但还需要更多真实观测校准
- replay corpus 已经起步，但还不是完整事故场景库

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
   - fitted artifact 决策需要匹配 artifact bundle，否则只能导出“需要外部 artifact”的半成品

4. **SQLite 仍是单进程友好，不是跨进程协调方案**
   - 真要多实例并发，需要外部 lease / lock

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

## 下一步
1. 给多实例部署补外部锁或 lease
2. 扩展 golden replay corpus，从分支覆盖升级成事故叙事场景
3. 为 fitted artifact 决策定义 replay promotion 规则：artifact bundle 如何归档、引用和校验
4. 把 `PR-REQUIREMENTS.md` 继续收敛成可执行的 phase 任务单
5. 用真实观测数据校准 Cox / Retention 的阈值和学习率

## 交接建议
- 下一位先读 `docs/architecture.md`
- 然后读 `docs/module-contracts.md`
- 再看 `docs/state-lifecycle.md`
- 最后看 `sre/self_iteration.py` 和 `sre/artifacts.py`

这会比从数学模块倒着看更快进入真实控制面。
