# PR 级功能需求清单（phase 对齐版）

这份清单把 `gan_matchmaking` 的交付拆成可独立审查、可独立合并的 PR。
它不再按原始文章顺序组织，而是按当前仓库的 **架构分层 / 状态机 / 交付阶段** 对齐。

## 使用方式

- `已完成`：仓库里已经有实现，主要用于 review、回归和后续重构参考。
- `待补强`：当前有实现但还缺 runtime 闭环、artifact 版本化、跨进程协调等关键环节。
- `待交付`：建议作为下一轮 Codex 的直接任务。

## 总体约束

1. 单 PR 只解决一个清晰问题。
2. 任何 PR 都必须保留 trace、日志和测试。
3. 任何 learned component 都必须有明确 fallback。
4. 任何 decision policy 都必须可回放。
5. 任何新增 runtime 行为都必须能被 runbook 解释。

---

## Phase 0 - Control Plane Hardening

### PR-0-01 - Typed config and error taxonomy

- **目标**：把运行时配置和错误体系固定成稳定契约。
- **范围**
  - `core/config.py`
  - `core/errors.py`
  - `tests/test_core_config.py`
- **交付标准**
  - 配置能从 dict / JSON / path 加载。
  - 非法配置返回 `ConfigError`，并带 `details`。
  - 所有核心失败路径都能映射到 typed exception。
- **状态**：已完成

### PR-0-02 - Structured logging and tracing

- **目标**：把每次决策变成可审计的 JSONL + correlation-id 链路。
- **范围**
  - `core/logging.py`
  - `core/tracing.py`
  - `tests/test_core_logging_tracing.py`
- **交付标准**
  - 每条日志都能带 `event`、`correlation_id`、`payload`。
  - `span` 能稳定记录 stage 起止时间。
  - 同一 logical decision 的日志可串起来。
- **状态**：已完成

### PR-0-03 - Metrics, RNG, and protocols

- **目标**：补齐指标、确定性随机源和协议边界。
- **范围**
  - `core/metrics.py`
  - `core/random.py`
  - `core/protocols.py`
  - `tests/test_core_metrics.py`
- **交付标准**
  - 指标可导出 Prometheus text。
  - 同 seed + 同输入可复现。
  - 协议边界允许替换实现而不改上层。
- **状态**：已完成

---

## Phase 1 - Domain Pipeline

### PR-1-01 - Domain DTOs and decision enum

- **目标**：固定 SRE 决策对象和状态枚举。
- **范围**
  - `sre/domain.py`
  - `tests/test_sre_self_iteration.py`
- **交付标准**
  - `DecisionKind` 只能是 `GO / CANARY / HOLD / ROLLBACK / ESCALATE`。
  - `Decision` 必须包含 `trace`、`rationale`、`risk_level`、`confidence`。
  - `ReleaseContext.validate()` 能拦住非法输入。
- **状态**：已完成

### PR-1-02 - Self-iteration pipeline orchestration

- **目标**：把 9 个机制串成一个清晰的决策链。
- **范围**
  - `sre/self_iteration.py`
  - `examples/sre_demo.py`
  - `tests/test_sre_self_iteration.py`
- **交付标准**
  - `decide(ctx)` 生成完整 trace。
  - 各 stage 有独立 payload。
  - guard clauses、policy resolve、emit 流程清楚分离。
- **状态**：已完成

### PR-1-03 - Lock, breaker, and shadow boundary

- **目标**：把并发、故障和灰度控制放到 pipeline 外围。
- **范围**
  - `sre/locking.py`
  - `sre/circuit.py`
  - `sre/shadow.py`
  - `sre/self_iteration.py`
- **交付标准**
  - 同一 service 的并发 decide 不互相踩状态。
  - breaker 可切 half-open / open / closed。
  - shadow / advisory / off 都在 trace 中可见。
- **状态**：已完成

---

## Phase 2 - Persistence and Replay

### PR-2-01 - Repository abstractions and in-memory parity

- **目标**：把状态抽象成可替换的持久层接口。
- **范围**
  - `persistence/base.py`
  - `persistence/memory.py`
  - `tests/test_persistence.py`
- **交付标准**
  - service / synergy / observation 三类仓库接口清楚。
  - memory 和 sqlite 的行为一致。
- **状态**：已完成

### PR-2-02 - SQLite durable store and decision persistence

- **目标**：把运行态写入真正可审计的本地持久层。
- **范围**
  - `persistence/sqlite.py`
  - `sre/self_iteration.py`
  - `tests/test_persistence.py`
- **交付标准**
  - 服务状态、协同图、观测、决策都可落库。
  - schema migration 可重复运行。
  - 失败时事务回滚。
- **状态**：已完成

### PR-2-03 - Replay corpus and reproduce runbook

- **目标**：让每次决策都能 byte-for-byte 回放。
- **范围**
  - `docs/runbooks/reproduce-decision.md`
  - `tests/test_sre_self_iteration.py`
  - `docs/codex-handoff.md`
- **交付标准**
  - 有清晰的 replay 输入 contract。
  - 有 golden trace / golden decision 样例。
  - 运行文档能指导复现和对比。
- **状态**：已完成

---

## Phase 3 - Training and Artifact Hydration

### PR-3-01 - Retention artifact versioning and loader

- **目标**：把 EOMM 的训练结果变成 runtime artifact。
- **范围**
  - `training/retention.py`
  - `eomm.py`
  - `sre/self_iteration.py`
  - `docs/adr/0006-runtime-artifact-versioning.md`
- **交付标准**
  - 训练产物带版本、时间、数据窗口、config hash。
  - runtime 能明确区分 fitted / fallback / uninitialized。
  - trace 能记录 artifact identity。
- **状态**：已完成

### PR-3-02 - Cox artifact versioning and loader

- **目标**：把生存分析模型从训练脚本接入 runtime。
- **范围**
  - `training/cox.py`
  - `survival.py`
  - `sre/self_iteration.py`
- **交付标准**
  - Cox artifact 可持久化、可水合、可回滚。
  - runtime fallback 必须有明确的 pessimistic 行为。
  - trace 中能看到 fitted / fallback 状态。
- **状态**：已完成

### PR-3-03 - Artifact metadata in trace and persistence

- **目标**：让模型版本成为决策的一部分，而不是外部注释。
- **范围**
  - `persistence/sqlite.py`
  - `sre/domain.py`
  - `sre/self_iteration.py`
- **交付标准**
  - 每条决策持久化 artifact version。
  - replay 时可区分 code drift 与 model drift。
  - 训练报告和运行日志可互相对照。
- **状态**：已完成

### PR-3-04 - Fitted artifact replay promotion

- **目标**：把 fitted artifact 决策从“可导出但需人工补 artifact”提升为可审查的 replay promotion 流程。
- **范围**
  - `sre/replay.py`
  - `sre/artifacts.py`
  - `docs/runbooks/reproduce-decision.md`
  - `tests/test_replay_corpus.py`
- **交付标准**
  - fixture 能声明 required artifact bundle / version。
  - replay 前校验 artifact manifest。
  - runbook 明确哪些 fitted 决策可以进入 golden corpus。
- **状态**：待交付

---

## Phase 4 - Runtime Surfaces

### PR-4-01 - HTTP service

- **目标**：把 pipeline 暴露成标准库 HTTP 服务。
- **范围**
  - `service/app.py`
  - `tests/test_http_service.py`
- **交付标准**
  - `POST /v1/decide`
  - `POST /v1/observe`
  - `GET /v1/services/{id}`
  - `GET /healthz`
  - `GET /readyz`
  - `GET /metrics`
- **状态**：已完成

### PR-4-02 - CLI and latency benchmark

- **目标**：给人工和自动化调用提供最小表面。
- **范围**
  - `cli.py`
  - `bench/latency.py`
  - `tests/test_cli.py`
- **交付标准**
  - CLI 可直接返回 decision JSON。
  - benchmark 有 p50 / p95 / p99。
  - 结果可用于上线前门禁。
- **状态**：已完成

### PR-4-03 - Deploy manifests and CI

- **目标**：让它能被部署和持续验证。
- **范围**
  - `Dockerfile`
  - `deploy/kubernetes/`
  - `.github/workflows/ci.yml`
- **交付标准**
  - 容器化可运行。
  - K8s 有 service / deployment / cronjob / probes。
  - CI 覆盖核心路径和 benchmark gate。
- **状态**：已完成

---

## Phase 5 - Knowledge and Reviewability

### PR-5-01 - Architecture and module contracts

- **目标**：把系统从“能跑”变成“能读懂”。
- **范围**
  - `docs/architecture.md`
  - `docs/module-contracts.md`
  - `docs/state-lifecycle.md`
- **交付标准**
  - 架构、模块、状态三层文档对齐。
  - 每个模块的 ownership、fallback、readiness 明确。
- **状态**：已完成

### PR-5-02 - ADR and runbooks

- **目标**：把设计决策和运维路径写清楚。
- **范围**
  - `docs/adr/`
  - `docs/runbooks/`
- **交付标准**
  - 每个关键架构选择都有 ADR。
  - 每个常见故障都有 runbook。
- **状态**：已完成

### PR-5-03 - Codex handoff and roadmap

- **目标**：把交接链路标准化。
- **范围**
  - `docs/codex-handoff.md`
  - `docs/implementation-roadmap.md`
  - `README.md`
- **交付标准**
  - 下一位接手的人 5 分钟内能找到主线。
  - 交接文档和 roadmap 可以直接驱动下一轮 Codex。
- **状态**：已完成

### PR-5-04 - SRE control primitive catalog

- **目标**：把 GAN 九机制从算法说明提升为可迁移的 SRE 工程能力目录。
- **范围**
  - `sre/primitives.py`
  - `docs/sre-control-primitives.md`
  - `docs/architecture.md`
  - `docs/module-contracts.md`
- **交付标准**
  - 九个机制都有稳定 primitive 名称、输入、输出、runtime stage、readiness。
  - 文档说明每个 primitive 能迁移到哪些 SRE 场景，以及误用边界。
  - 测试保护 primitive catalog 不丢机制、不重名、不空契约。
- **状态**：已完成

---

## 下一轮最值得做的 PR

1. **PR-3-04**：定义 fitted artifact replay promotion，解决 artifact bundle 如何归档、引用和校验。
2. **PR-2-03 扩展**：继续补 incident-style replay，覆盖 artifact validation failure、breaker short-circuit、shadow/advisory transition。
3. **PR-跨进程扩展**：如果要多副本上线，再补 Kubernetes Lease / PostgreSQL advisory lock / Redis lease 之一。
4. **PR-5-04**：把 `sre-control-primitives` 继续扩展成迁移模板和设计评审 checklist。
5. **PR-校准**：用真实观测数据校准 Cox / Retention 阈值和学习率。

这五项会把“可跑”推进到“可复现、可回滚、可审计”的生产形态。
