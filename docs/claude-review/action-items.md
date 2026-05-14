# Action Items · 建议开的 follow-up PR

> **Superseded historical tracker (2026-05/2026-06).**
> F-001 ~ F-010 已在 [`2026-06-spec-completion.md`](2026-06-spec-completion.md)
> 与 [`2026-06-codex-package-review.md`](2026-06-codex-package-review.md) 中闭环。
> 本文件保留为审计记录，不再是当前 blocker / work queue。当前可执行入口见
> [`spec-v3/README.md`](spec-v3/README.md)。

下列 PR 按推荐顺序列出。每一条都配有目标、范围、验收标准、必需测试、
以及关联的 findings。codex 可以直接把这个清单当作 PR description 的模板。

## 合入前必做（blocker）

### PR-fix-01 · `lease-refresh-failure-surfaces-through-readiness`

- **关联 findings**: [F-001](findings.md#f-001--leaserefreshloop-续租失败静默化)
- **目标**: lease refresh 失败不能静默——必须被 readiness probe / 监控看见
- **范围**:
  - `gan_matchmaking/sre/leases.py`: `LeaseRefreshLoop` 增加 `on_failure`
    callback；移除 `# pragma: no cover`
  - `gan_matchmaking/service/app.py`: `DecisionApp` 新增 `readiness_flag`
    （或 `_lease_healthy: threading.Event`），`handle_ready` 检查它；增加
    `gan_lease_refresh_failures_total` counter
  - `gan_matchmaking/service/__main__.py`: 构造 `LeaseRefreshLoop` 时把
    readiness flag / shutdown callback 注入进去
- **验收标准**:
  1. 续租失败后 `/readyz` 返回 503（在 k8s 下自动把流量切走）
  2. `gan_lease_refresh_failures_total` 递增，带 `reason` label
  3. 日志 `lease.refresh.failed` 记录 correlation_id（建议生成一个
     per-server 启动 id）、失败原因、最后一次成功时间
  4. 可选：`LeaseRefreshLoop` 支持 `shutdown_callback`，调用 `httpd.shutdown()`
- **必需测试**:
  - `test_refresh_failure_flips_readiness` — inject 假 now 让 lease 过期，
    强制 refresh 失败，断言 `/readyz` 返回 503
  - `test_refresh_failure_increments_metric`
  - `test_refresh_failure_emits_structured_log`

---

## 合入后短期（<2 周）

### PR-fix-02 · `allowlist-appconfig-in-trace`

- **关联 findings**: [F-003](findings.md#f-003--traceinputconfig-无-allowlist未来易泄密)
- **目标**: 防止未来往 AppConfig 里加 secret 时悄悄泄漏到 trace
- **范围**:
  - `gan_matchmaking/core/config.py`: 新增 `AppConfig.to_trace_dict()`；
    `ObservabilityConfig.trace_config_allowed_keys: tuple[str, ...]` 默认包含
    当前所有字段
  - `gan_matchmaking/sre/self_iteration.py::_decide_locked`: 把 `self.config.to_dict()`
    换成 `self.config.to_trace_dict()`
  - `docs/adr/0006-runtime-artifact-versioning.md`: 补一段 "what must never enter trace"
- **验收标准**:
  1. 往 AppConfig 加一个字段不会自动出现在 trace（需要显式加 allowlist）
  2. 现有 replay fixtures 都能正常回放
- **必需测试**:
  - `test_trace_config_only_allowlisted_keys`
  - `test_trace_config_contract_locked` — snapshot 当前 allowlist，未来改动需显式修快照

### PR-fix-03 · `shadow-mode-metric-and-log-alignment`

- **关联 findings**: [F-002](findings.md#f-002--shadow-rewrite-导致监控日志与最终决策不一致)
- **目标**: shadow rewrite 后，监控指标和最终决策语义一致
- **范围**:
  - `gan_matchmaking/sre/self_iteration.py`: 把 `gan_decisions_total` 的递增从
    `_emit` 挪到 `_finalize_decision` 之后；或者加 `enforced_kind` label
  - `_shadow_wrap` 里补一条 `decide.shadow_rewritten` 日志事件
- **验收标准**:
  1. `shadow_mode=off`: 行为不变
  2. `shadow_mode=shadow`: `gan_decisions_total{kind="hold"}` 递增，原 kind
     出现在 `gan_shadow_diff_total{suppressed_kind}` 和日志 / trace 里
- **必需测试**:
  - `test_shadow_mode_metric_reflects_enforced_kind`
  - `test_shadow_mode_emits_rewrite_event`

---

## 合入后中期（<6 周）

### PR-refactor-01 · `split-artifacts-module-and-freeze-scaling-constants`

- **关联 findings**: [F-005](findings.md#f-005--_service_player--_candidate_player-里硬编码常数影响-artifact-稳定性), [F-006](findings.md#f-006--sreartifactspy-单文件过大488-行)
- **目标**: 把 488 行的 `sre/artifacts.py` 拆成 4 个文件；把 rating scaling 常数
  freeze 进 artifact metadata
- **范围**:
  - `sre/artifacts/` 包化：`metadata.py` / `retention.py` / `cox.py` / `bundle.py`
  - `sre/artifacts/retention.py` 里把 scaling 常数抽命名常量 + 写进
    `ArtifactMetadata.extra.rating_scaling_version`
  - `load_retention_artifact` 做 version mismatch 检查
- **验收标准**:
  1. 所有现有测试通过
  2. 改动任一 scaling 常数会导致已有 retention artifact 加载失败（带明确错误）
  3. 拆分后每个文件 < 180 行
- **必需测试**:
  - `test_rating_scaling_contract_snapshot`
  - `test_artifact_version_invalidates_on_scaling_change`
  - 保留所有现有 artifact 测试

### PR-refactor-02 · `promote-ctx-from-dict-to-domain-serde`

- **关联 findings**: [F-007](findings.md#f-007--cli_ctx_from_dict-被跨模块-_-私有-import)
- **目标**: 消除跨模块 `_ctx_from_dict` 私有依赖
- **范围**:
  - 把 `_ctx_from_dict` 移到 `sre/domain.py::ReleaseContext.from_dict(payload: Mapping)`
    或 `sre/serde.py`
  - 更新 `cli.py` / `service/app.py` / `sre/replay.py` 以及所有测试引用
  - 加 `ReleaseContext.to_dict(...)` 让序列化对称，取代 `_context_payload`
- **验收标准**:
  1. 没有任何模块 `from ..cli import _...`
  2. `cli.py` 变瘦，只做 argparse + 调用公开 API
- **必需测试**:
  - `test_release_context_roundtrip_preserves_shape` — from_dict ∘ to_dict = identity

### PR-fix-04 · `eliminate-ctx-service-side-effects`

- **关联 findings**: [F-004](findings.md#f-004--ctxservice-在-decide-里被-setattrctxservice-_deps--副作用污染)
- **目标**: `decide()` 不再往 `Service` 对象上偷偷挂 `_deps`
- **范围**:
  - `sre/self_iteration.py::decide`: 用局部变量流转 dependencies
  - `observe_release`: dependencies 从 ctx 或显式参数拿，不从 `getattr(svc, "_deps")`
- **验收标准**: 公开 `Service` 属性集合不变；多次 decide 不累积内部状态
- **必需测试**:
  - `test_decide_does_not_mutate_service_object`
  - `test_observe_release_accepts_explicit_dependencies`

### PR-fix-05 · `idempotent-schema-migrations`

- **关联 findings**: [F-008](findings.md#f-008--sqlite-migration-v5-有列已存在跳过特殊处理)
- **目标**: 去掉 v5 migration 的特殊分支；迁移系统恢复声明式契约
- **范围**:
  - `persistence/sqlite.py`: 所有 migration 改写成 idempotent DDL
    （`ADD COLUMN IF NOT EXISTS` 或者 `CREATE ... IF NOT EXISTS`）
  - 移除 v5 特判分支
  - 补 ADR-0008 解释"为什么所有 migration 都必须 idempotent"
- **验收标准**:
  1. 空库走一遍所有 migration 正常
  2. 从旧版本升级（比如已有 artifact_version 列）不报错
  3. 重启多次不产生重复数据
- **必需测试**:
  - `test_migration_idempotent_on_fresh_db`
  - `test_migration_idempotent_from_legacy_schema`

---

## 合入后长期 / 下一轮主题

### PR-calibrate-01 · `calibrate-cox-and-retention-on-real-observations`

- **目标**: 从 bootstrap 走向 data-driven
- **范围**: 不是代码 PR，而是一份 **校准 runbook + 一次训练 + 一份校准报告**
- **产出**:
  - `docs/runbooks/calibrate-models.md`
  - `training_artifacts/calibration_report_YYYY-MM.json`
  - 首批 fitted replay fixture（带 artifact bundle 归档）
- **验收标准**: Cox β 的置信区间 / Retention 的预测命中率都有明确数字

### PR-replay-02 · `incident-style-replay-expansion`

- **关联 findings**: 无（主动扩展）
- **目标**: 把 replay corpus 从"分支覆盖"推进到"事故叙事"
- **必需 fixture**:
  - `artifact_validation_failure.json` — artifact manifest 坏 → fallback
  - `breaker_short_circuit.json` — 熔断打开时的 ESCALATE
  - `shadow_to_advisory_transition.json` — shadow 模式下各种分支
  - `storm_multi_service_rollback.json` — 多服务同时降级
- **验收标准**: `tests/test_replay_corpus.py` 参数化运行全部通过；每个
  fixture 的 `expected.rationale_contains` / `expected.trace_values` 有
  非平凡断言

### PR-scale-01 · `distributed-lease-prototype`

- **前置条件**: 只有目标部署明确需要多写者才开
- **目标**: 原型化 k8s Lease / PostgreSQL advisory lock / Redis lease 之一
- **范围**:
  - `sre/leases.py` 抽象出 `LeaseBackend` 接口，`FileLease` 成为一种实现
  - 新增 `KubernetesLease` / `PostgresAdvisoryLease` / `RedisLease` 之一
  - 相关 runbook / ADR-0009
- **验收标准**:
  - 两个 pod 同时启动，只有一个拿到 lease
  - 持有者挂掉后另一个在 TTL 内接管
  - 不引入 PyPI 外部依赖时用 subprocess / HTTP；引入时在 optional extras 里

### PR-doc-01 · `merge-handoff-and-roadmap-overlap`

- **关联 findings**: [F-009](findings.md#f-009--codex-handoffmd-与-implementation-roadmapmd-内容重叠约-30)
- **目标**: 消除两份文档的重叠
- **验收标准**: 两份文档的章节提纲不再有相同条目；"下一步建议"只出现在
  implementation-roadmap.md

### PR-doc-02 · `standardize-replay-fixture-naming`

- **关联 findings**: [F-010](findings.md#f-010--replay-fixture-命名风格不统一)
- **目标**: 统一 fixture 命名为 `{scenario}_{expected_kind}.json`
- **范围**: 重命名现有 fixture + 加 `tests/fixtures/replay/README.md`
- **验收标准**: 所有 fixture 名都能被 `^[a-z][a-z0-9]*(_[a-z0-9]+)+_(go|canary|hold|rollback|escalate)\.json$` 匹配

---

## 关联追踪

| Action Item | 关联 Findings |
|---|---|
| PR-fix-01 | F-001 |
| PR-fix-02 | F-003 |
| PR-fix-03 | F-002 |
| PR-fix-04 | F-004 |
| PR-fix-05 | F-008 |
| PR-refactor-01 | F-005, F-006 |
| PR-refactor-02 | F-007 |
| PR-doc-01 | F-009 |
| PR-doc-02 | F-010 |
| PR-calibrate-01 | — |
| PR-replay-02 | — |
| PR-scale-01 | — |
