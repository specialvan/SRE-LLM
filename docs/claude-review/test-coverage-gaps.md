# Test Coverage Gaps

这份清单列出 `gan-session` 分支**现有 105 个测试**未覆盖的风险场景。分三档：

- **🔴 必须补**: 对应 P1/P2 finding，不补上会在生产暴露
- **🟡 建议补**: 对应 P3 finding，补上显著降低回归风险
- **🟢 机会性补**: 对应 P4 finding 或长期健壮性

每条给出：场景、建议测试位置、断言要点。

---

## 🔴 必须补

### CG-001 · Lease 续租失败的可见性

- **对应 finding**: F-001
- **位置**: `tests/test_leases.py` + `tests/test_http_service.py`
- **场景**:
  - 获取 lease 后，lease file 被删除（模拟另一个 owner 强占）
  - 获取 lease 后，`now()` 跳到 TTL 之后（模拟 refresh 线程 starve）
  - 获取 lease 后，lease file 内容被改成非法 JSON（模拟磁盘损坏）
- **断言**:
  1. `/readyz` 在 N 秒内返回 503
  2. `gan_lease_refresh_failures_total` 递增，`reason` label 正确
  3. 日志里能找到 `lease.refresh.failed` 事件及其 `error_type`
  4. （可选）HTTP server 主动 shutdown
- **优先级理由**: F-001 的 `# pragma: no cover` 恰好盖住了最危险分支，必须显式测

### CG-002 · Shadow 模式下监控指标语义

- **对应 finding**: F-002
- **位置**: `tests/test_sre_self_iteration.py`
- **场景**:
  - pipeline 决策出 ROLLBACK，`shadow_mode=shadow`
  - pipeline 决策出 GO/CANARY 各种 kind，`shadow_mode=shadow`
  - `shadow_mode=advisory` 时对比
- **断言**:
  1. `gan_decisions_total{kind=<enforced>}` 反映的是实际下发的 kind（HOLD）
  2. `gan_shadow_diff_total{suppressed_kind=<original>}` 反映被吞的原 kind
  3. 日志或 trace 中能找到 `original_kind` 和 `final_kind` 两者
  4. SQLite `decisions.kind` 存的是 `final_kind`，`trace_json` 里能回溯 original

### CG-003 · Config 通过 trace 泄漏秘密字段的回归

- **对应 finding**: F-003
- **位置**: `tests/test_sre_self_iteration.py` 或新建 `tests/test_trace_privacy.py`
- **场景**:
  - 构造一个 `AppConfig`，给 `ObservabilityConfig` 加一个模拟 secret 字段
    （未来真的加 Redis URL / token 时就是这个形态）
  - 或者用 mock/monkeypatch 注入一个字段到 dataclass
- **断言**:
  1. `trace["input"]["config"]` 里找不到该字段值（被 allowlist 过滤）
  2. 默认 allowlist 的键集合通过 snapshot 测试锁死
  3. 把字段手动加进 allowlist 后，值会出现在 trace

---

## 🟡 建议补

### CG-004 · `Service` 对象不被 `decide()` 副作用污染

- **对应 finding**: F-004
- **位置**: `tests/test_sre_self_iteration.py`
- **场景**:
  - 同一个 `Service` 实例连续传入 `decide()` 两次，每次 `dependencies` 不同
  - 或者调用 `observe_release` 之后检查 `Service` 公开字段
- **断言**:
  1. `Service` 实例上没有 `_deps` 属性（或存在但不跨调用累积）
  2. 多次 decide 后，`Service` 公开字段只被公开 API 修改
  3. `Service.as_dict()` 在多次 decide 后保持稳定的键集合

### CG-005 · Rating scaling 常数的 contract 快照

- **对应 finding**: F-005
- **位置**: `tests/test_artifacts_scaling_contract.py`（新建）
- **场景**:
  - 固定 `Service(mu=0.99, sigma=0.02, win_streak=3, loss_streak=1)` 和
    `ReleaseCandidate(expected_success=0.98, canary_fraction=0.1)`
  - 调 `build_match_config(service, candidate)`
- **断言**:
  1. `team_a[0].rating.mu` / `team_b[0].rating.mu` 与固定数值吻合（snapshot）
  2. 如果 `_service_player` 里任何常数变了，测试应该失败
  3. 同时 artifact metadata 里的 `rating_scaling_version` 会变
- **优先级理由**: 这些常数一旦无意改动，所有线上 retention artifact 会静默失效

### CG-006 · SQLite migration 在老库 / 空库上的幂等性

- **对应 finding**: F-008
- **位置**: `tests/test_persistence.py`
- **场景 A · 空库**: 新建数据库，重复启动 `SQLitePipelineStore` 3 次
- **场景 B · 历史库**: 手工把数据库造成"已经有 artifact_version 列、但
  schema_migrations 里没记录 v5"的老状态，再启动
- **场景 C · 超前库**: 数据库里已经有 v5 记录但 artifact_version 列不存在
  （极端 edge case）
- **断言**:
  1. `schema_migrations` 表里 v1-v5 恰好各一行
  2. 没有重复数据
  3. 现有 CRUD 都工作
  4. 任何异常都不吞到 migration 之外

### CG-007 · `ReleaseContext.from_dict` / `to_dict` 往返完整性

- **对应 finding**: F-007
- **位置**: `tests/test_sre_domain.py`（新建）
- **场景**: 随机构造 ReleaseContext 对象，跑 `from_dict(to_dict(ctx))` 往返
- **断言**: 关键字段 byte-level 相等（除了被明确标为 non-serializable 的）

### CG-008 · Artifact hydrate 失败的边界

- **位置**: `tests/test_sre_self_iteration.py`
- **现有测试**: `test_invalid_artifact_manifest_falls_back` 已经覆盖
  feature_names 错的情况
- **未覆盖场景**:
  1. Artifact 文件存在但 JSON metadata 缺失（只有 `.npz`）
  2. Retention 的 weights shape 对，但 bias 是 NaN
  3. Cox 的 baseline_t / baseline_H 长度不一致
  4. Artifact 目录不存在（`directory="/nonexistent"`）
  5. Artifact 目录存在但无读权限（仅 linux 上测）
- **断言**: 每种情况都降级为 bootstrap，`trace["artifacts"]["validation_errors"]`
  里记录具体原因

---

## 🟢 机会性补

### CG-009 · 并发决策下 per-service lock 的公平性

- **位置**: `tests/test_sre_self_iteration.py` 或新建压测测试
- **场景**: 10 个线程同时对同一 `service_id` 调 `decide`，各自拿不同
  `correlation_id`
- **断言**:
  1. 所有 decide 按串行顺序执行
  2. Service 的 `mu / sigma` 更新链路没有丢更新
  3. 所有 correlation_id 都出现在审计表
  4. 无死锁，总耗时 < 合理阈值

### CG-010 · Replay corpus 覆盖矩阵

- **位置**: `tests/fixtures/replay/` + 新增一个 meta-test
- **场景**: 断言 fixture 覆盖了所有 `(DecisionKind, RiskLevel, ShadowMode)` 组合
  的关键子集
- **断言**: 用 set 操作证明 corpus 至少覆盖了以下矩阵：
  - `(GO, OK, OFF)` · `(CANARY, OK, OFF)` · `(CANARY, WARN, OFF)`
  - `(HOLD, WARN, OFF)` · `(HOLD, ALARM, OFF)` · `(ROLLBACK, ALARM, OFF)`
  - `(ESCALATE, ALARM, OFF)` · `(*, *, SHADOW)` · `(*, *, ADVISORY)`

### CG-011 · Benchmark SLO 回归

- **位置**: `bench/latency.py` + CI job
- **现状**: CI 里跑 `python -m bench.latency --quick`，但没有失败门禁
- **建议**: 加 `--p99-ms 5.0` 参数，CI 强制通过
- **优先级理由**: 这是性能回归的唯一护栏

### CG-012 · Lease backend 替换的接口契约

- **位置**: 等 `PR-scale-01` 落地时同步补
- **场景**: 抽出 `LeaseBackend` 接口后，用同一套契约测试 FileLease 和
  任一分布式实现
- **断言**: 两种实现在 acquire / refresh / release / takeover 上语义一致

---

## 统计

| 档位 | 条目数 | 对应 finding |
|---|---|---|
| 🔴 必须补 | 3 | F-001, F-002, F-003 |
| 🟡 建议补 | 5 | F-004, F-005, F-008, F-007, 边界 |
| 🟢 机会性补 | 4 | F-010, 压测, SLO 回归, 接口契约 |
| 合计 | 12 | — |

如果按优先级推进：

- PR-fix-01 带 CG-001（合入前）
- PR-fix-02 带 CG-003
- PR-fix-03 带 CG-002
- PR-fix-04 带 CG-004
- PR-fix-05 带 CG-006
- PR-refactor-01 带 CG-005
- PR-refactor-02 带 CG-007
- PR-replay-02 带 CG-010

剩下的 CG-008 / CG-009 / CG-011 / CG-012 可作为独立的"健壮性补强"小 PR。
