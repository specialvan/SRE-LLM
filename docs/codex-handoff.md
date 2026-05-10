# Codex Handoff - GAN Matchmaking / SRE Self-Iteration

## 当前状态
- 当前分支：`gan-session`
- 远端：`origin`
- 当前目标：把 matchmaking / rating / decision 这条链收拢成可审计、可回放、可训练、可灰度的 SRE 自迭代控制面
- 当前仓库已有：HTTP 服务、SQLite 持久化、离线训练脚本、Prometheus text metrics 输出
- 当前工作区仍有一组未提交的 artifact 版本化改动，核心方向是把 runtime artifact 变成一等公民

## 已完成主线
1. `docs/architecture.md`
   - 说明整体架构、模块分层、需求、任务拆分与下一步收敛点
2. `docs/module-contracts.md`
   - 按模块说明输入、输出、失败模式、成熟度
3. `docs/state-lifecycle.md`
   - 拆解 service / model / decision / breaker / shadow 的状态机
4. `docs/implementation-roadmap.md`
   - 把架构映射成 phase 与 PR 顺序
5. `docs/adr/0006-runtime-artifact-versioning.md`
   - 把 retention / Cox 的 runtime artifact 版本化正式定为架构决策
6. `README.md`
   - 已接入上述架构文档入口

## 当前代码地图

### 1. 控制面与领域
- `gan_matchmaking/sre/self_iteration.py`
  - 这是主决策循环，负责验证、分段打分、policy resolution、shadow 边界与 trace 产出
  - 当前已引入 `RuntimeArtifactBundle` / `load_runtime_artifacts` / `build_match_config` / `build_history_vector`
  - 但 artifact hydration 还没有完全贯穿到决策 trace 和最终 decision 记录
- `gan_matchmaking/sre/domain.py`
  - `Decision` 已新增 `artifact_version`
  - `Decision.to_dict()` 已输出该字段
- `gan_matchmaking/sre/shadow.py`
  - 只负责 off / shadow / advisory 的边界改写，不负责模型切换

### 2. Runtime artifact 桥接
- `gan_matchmaking/sre/artifacts.py`
  - 新增 runtime artifact 元数据、版本计算、保存 / 加载、bundle 组合
  - 提供 `ArtifactMetadata`、`RetentionArtifact`、`CoxArtifact`、`RuntimeArtifactBundle`
  - 这是后续灰度发布 / 回滚 / 回放时的关键桥梁
- `gan_matchmaking/core/config.py`
  - 新增 `ArtifactsConfig`
  - 允许在配置层指定 artifact 目录、文件名和 metadata 文件名
- `gan_matchmaking/core/__init__.py`
  - 已导出 `ArtifactsConfig`

### 3. 持久化
- `gan_matchmaking/persistence/sqlite.py`
  - `decisions` 表已加 `artifact_version`
  - 迁移已加入 schema migrations
  - 决策落库已支持版本字段

### 4. 训练
- `gan_matchmaking/training/retention.py`
  - 离线产出 `retention_weights.npz`
- `gan_matchmaking/training/cox.py`
  - 离线产出 `cox_beta.npz`
- 训练链已经能产出 artifact，但还没有完整的“加载最新模型 -> 灰度切换 -> 回写效果 -> 再训练”闭环

### 5. 服务与观测
- `gan_matchmaking/service/app.py`
  - 已有 `/v1/decide`、`/v1/observe`、`/healthz`、`/readyz`、`/metrics`
  - 目前是服务内暴露指标，还没有主动接外部 Prometheus / Alertmanager / Grafana / 日志上下文

## 当前缺口

### 1. 真实数据接入层
- 现在训练和 observe 主要吃手工 / 样例输入
- 缺少从外部发布记录、告警、时序指标自动构造 `ReleaseContext` / `Observation` 的采集器

### 2. 现有监控系统适配层
- 现在只有 `/metrics` 暴露
- 还没有从 Prometheus / Alertmanager / Grafana / 日志系统主动拉上下文

### 3. 在线学习闭环
- 训练脚本能产出 `.npz`
- 但 pipeline 还没有完整的 rollout 机制：
  - 加载最新模型
  - 灰度切换
  - 回写效果
  - 再训练

## 风险与边界
1. `artifact_version` 已进领域对象和数据库，但 pipeline 里还没有真正把它写进每次决策的 trace / emit 路径
2. `SelfIterationPipeline` 仍然默认构造 `RetentionModel()` / `CoxModel()`，artifact hydration 还没完全接管 runtime
3. 目前没有 collector 层，外部世界和 `ReleaseContext` 之间仍是手工拼接
4. 没有独立的 rollout controller / registry，因此还不能做“新模型先 shadow、再 canary、再 promote、再 rollback”
5. replay corpus 还没固化成一等资产，回归更多是单元测试而不是端到端灰度回放

## 下一步建议
1. 先把 `load_runtime_artifacts()` 真正接入 `SelfIterationPipeline.__post_init__`，并把 `artifact_version` 写入 `Decision.trace`
2. 再补采集器层，把 release records、Prometheus、Alertmanager、Grafana、日志系统统一映射成 `EvidenceEnvelope` / `ReleaseContext`
3. 然后实现 rollout controller：
   - `bootstrap`
   - `shadow`
   - `advisory`
   - `canary`
   - `promote`
   - `rollback`
4. 最后补 replay corpus：
   - happy path
   - fallback path
   - escalation path

## 接手顺序
1. 先读 `docs/architecture.md`
2. 再读 `docs/module-contracts.md`
3. 再读 `docs/state-lifecycle.md`
4. 再看 `gan_matchmaking/sre/artifacts.py`
5. 最后看 `gan_matchmaking/sre/self_iteration.py`

## 需要继续盯住的文件
- `gan_matchmaking/sre/self_iteration.py`
- `gan_matchmaking/sre/artifacts.py`
- `gan_matchmaking/core/config.py`
- `gan_matchmaking/sre/domain.py`
- `gan_matchmaking/persistence/sqlite.py`
- `gan_matchmaking/service/app.py`
- `gan_matchmaking/training/cox.py`
- `gan_matchmaking/training/retention.py`
