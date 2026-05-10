# Codex Handoff - GAN Matchmaking / SRE Self-Iteration

## 当前状态
- 当前分支：`gan-session`
- 当前方向：把 matchmaking / rating / decision 方案稳定成可审计、可训练、可回放的 SRE 决策流水线
- 现状：九个机制的语义映射、架构拆解、模块契约、状态生命周期、实施路线图、ADR 已经成体系
- 最新进展：runtime artifact 版本化已经接入在线决策链路，`Decision.artifact_version`、SQLite 决策审计表、训练产物元数据、runtime hydrate 都已打通

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
- `training/`
  - 已能从 store 训练 Cox / Retention，并输出权重 + 元数据

### 仍偏研究态
- `minimax_bp.py`
  - 更像解释性辅助层，不是主生产路径
- `gnn_synergy.py`
  - 现在是轻量图推理，不是完整图服务
- `EOMM / Cox` 的特征空间仍需要继续统一和校准
- replay corpus 还没有成为一等资产

## 风险与边界
1. **训练/运行特征不完全同构**
   - Cox 训练和 runtime 现在能降级兼容，但语义上还没完全统一
   - 这是最需要继续补的边界

2. **artifact 与 fallback 的切换要可见**
   - 线上必须能看出当前是 artifact 路径还是 bootstrap 路径
   - `trace["artifacts"]` 是主入口

3. **决策审计和幂等性**
   - `correlation_id` 不能乱复用
   - 熔断短路场景要避免重复主键

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
   - trace + decision + artifact_version
6. **离线再训练**
   - observation log -> artifact -> runtime hydrate

这个结构可以迁移到发布控制、容量调度、故障分流、巡检节流、告警降噪、回滚决策等场景。

## 下一步
1. 把 Cox / EOMM 的训练特征空间彻底对齐，消掉“能跑但不够同构”的边角
2. 给 runtime artifact 增加更强的校验与 manifest
3. 建 golden replay corpus，覆盖 happy path / fallback / rollback / escalation
4. 给多实例部署补外部锁或 lease
5. 把 `PR-REQUIREMENTS.md` 继续收敛成可执行的 phase 任务单

## 交接建议
- 下一位先读 `docs/architecture.md`
- 然后读 `docs/module-contracts.md`
- 再看 `docs/state-lifecycle.md`
- 最后看 `sre/self_iteration.py` 和 `sre/artifacts.py`

这会比从数学模块倒着看更快进入真实控制面。
