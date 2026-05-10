# Codex Handoff - GAN Matchmaking / SRE Self-Iteration

## 当前状态

- 当前分支：`gan-session`
- 远端：`origin`
- 目标：把 matchmaking / rating / decision 方案稳定成可审计的 SRE 自迭代控制系统
- 当前仓库已完成：架构文档、模块契约、状态生命周期、实现路线图、模型版本化 ADR

## 已完成的主线

1. `docs/architecture.md`
   - 说明整体架构、需求、任务拆分、收敛目标。
2. `docs/module-contracts.md`
   - 逐模块说明输入、输出、状态、fallback、成熟度。
3. `docs/state-lifecycle.md`
   - 拆解 service / model / decision / breaker / shadow 五条状态机。
4. `docs/implementation-roadmap.md`
   - 把架构映射成 phase 级交付序列。
5. `docs/adr/0006-runtime-artifact-versioning.md`
   - 把 retention / Cox 的 runtime artifact 版本化正式定为架构决策。
6. `README.md`
   - 已接入 architecture / module contracts / state lifecycle / roadmap 入口。

## 核心代码定位

- `gan_matchmaking/sre/self_iteration.py`
  - 主决策管线，包含验证、分段打分、策略决策、shadow 边界、熔断、锁、trace。
- `gan_matchmaking/persistence/sqlite.py`
  - 持久化主实现，负责服务状态、协同图、观测、决策落库。
- `gan_matchmaking/training/retention.py`
  - EOMM retention 训练脚本。
- `gan_matchmaking/training/cox.py`
  - Cox 风险训练脚本。
- `gan_matchmaking/service/app.py`
  - HTTP 服务包装。
- `gan_matchmaking/cli.py`
  - CLI 决策入口。

## 生产态与研究态

### 生产形态

- `core/`
- `sre/`
- `persistence/`
- `service/`
- `training/`
- `docs/adr`
- `docs/runbooks`
- `docs/knowledge_base.html`

### 研究 / 辅助形态

- `minimax_bp.py`
- legacy `pipeline.py`
- `gnn_synergy.py` 仍是轻量显式实现，不是独立图服务
- `eomm.py` / `survival.py` 的 runtime 仍依赖 fallback 路径

## 关键风险

1. runtime artifact 版本还没有真正在线路中贯通
2. 当前锁只是进程内，不是跨进程协调
3. EOMM 和 Cox 的训练产物与 runtime 还没有完全闭环
4. replay corpus 还没有作为一等资产冻结
5. shadow / advisory / off 必须继续保持 trace 可见

## 下一步建议

1. 先把 retention / Cox 的 artifact loader 接进 runtime，并把版本写进 trace 和决策持久化。
2. 把 `PR-REQUIREMENTS.md` 按 `implementation-roadmap.md` 重排。
3. 补 golden replay corpus，覆盖 happy path / fallback path / escalation path。
4. 如果要多副本上线，再补跨进程锁或外部 lease。

## 接手建议

- 先读 `docs/architecture.md`
- 再读 `docs/module-contracts.md`
- 再读 `docs/state-lifecycle.md`
- 最后看 `sre/self_iteration.py`

这样能最快进入系统的真实控制面，而不是停留在数学模块表面。
