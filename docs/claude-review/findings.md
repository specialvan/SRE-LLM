# Findings · 按严重度分层

本清单为 `gan-session` 分支的评审结论，codex 接手时以此为 tracker。
每一条都包含：严重度 / 影响面 / 复现路径 / 修复建议 / 必需测试 / 状态。

状态值：`open` / `in-progress` / `resolved` / `deferred` / `wontfix`。
已解决的条目保留记录，标 `resolved` 并记链接到对应 commit。

---

## P1 · 合入前必修

### F-001 · `LeaseRefreshLoop` 续租失败静默化

- **severity**: P1
- **status**: resolved (commit 704765d, 2026-05-12)
- **文件**: `gan_matchmaking/sre/leases.py`
- **影响面**: 违反 ADR-0007 的 split-brain 防护承诺
- **复现路径**:
  1. HTTP 服务用 `--lease-file` 启动，持有 lease
  2. 持有期间删除 lease 文件 / 另一个 owner 强占
  3. 后台续租线程抛 `LeaseNotAcquiredError`，捕获后把异常塞进 `self.error`，线程退出
  4. 主线程 `run_wsgi` 继续接受请求并写 SQLite
  5. 另一个 pod 在 lease 过期后接管，开始并发写同一个 SQLite state file
- **问题代码**:
  ```python
  def _run(self, interval: float) -> None:
      while not self._stop.wait(interval):
          try:
              self.lease.refresh()
          except BaseException as exc:  # pragma: no cover - surfaced by ``error``.
              self.error = exc
              self._stop.set()
              return
  ```
  注释写 `surfaced by error`，但没有任何 caller 在读 `self.error`。`# pragma: no cover`
  恰恰盖住了最危险的分支。
- **修复建议（二选一或组合）**:
  1. 把 httpd 句柄或一个 `shutdown_callback` 传进 `LeaseRefreshLoop`，续租失败时
     `httpd.shutdown()` 让主循环退出。
  2. 在 `DecisionApp` 里加一个 `readiness_flag` 字段，续租失败时置 false；
     `handle_ready()` 基于这个 flag 返回 503。结合 k8s readiness probe，流量会
     自动切走，然后 pod 自然重启。
  3. 同时移除 `# pragma: no cover`，补失败注入测试。
- **必需测试**:
  - `test_refresh_failure_sets_ready_false` — 拿到 lease、强制 refresh 失败、断言 `/readyz` 返回 503
  - `test_refresh_failure_emits_log_and_metric` — 断言日志出现 `lease.refresh.failed` 和 metric `gan_lease_refresh_failures_total` 递增
  - `test_refresh_failure_stops_server` — 如果走方案 1，断言主循环在短时间内退出

---

## P2 · 上产前必修

### F-002 · Shadow rewrite 导致监控/日志与最终决策不一致

- **severity**: P2
- **status**: resolved (commit 704765d, 2026-05-12)
- **文件**: `gan_matchmaking/sre/self_iteration.py`
- **影响面**: 监控 / 告警失真
- **复现路径**:
  1. `shadow_mode=shadow`，pipeline 计算出 `kind=ROLLBACK`
  2. `_emit` 先递增 `gan_decisions_total{kind="rollback"}` 并记录 `decide.finished{kind="rollback"}`
  3. 随后 `_finalize_decision` → `_shadow_wrap` 把 `decision.kind` 改成 `HOLD`
  4. 返回给 caller 的是 HOLD，SQLite 里也写 HOLD
  5. 仪表盘上 "ROLLBACK 次数" 被递增，但实际没有 rollback 发生
- **为什么是 P2 不是 P1**:
  有 `gan_shadow_diff_total{suppressed_kind}` 可以反查，但该指标语义是
  "被 shadow 吞掉的次数"，不是 "rollback 没发生"。告警规则通常不会同时读这两个指标。
- **修复建议**:
  - 方案 A: `gan_decisions_total` 增加 `enforced_kind` label；在 `_finalize_decision`
    之后统一递增一次。
  - 方案 B: 在 `_finalize_decision` 里若改了 kind，补一条 `decide.shadow_rewritten`
    日志，带 `original_kind` 和 `final_kind`。
  - 两个方案其实可以并存：metric 侧加维度，日志侧加事件。
- **必需测试**:
  - `test_shadow_mode_metric_reflects_enforced_kind` — shadow 下，
    `gan_decisions_total{kind="hold"}` 递增而 `kind="rollback"` 不递增
  - `test_shadow_mode_emits_rewrite_event` — 日志里出现 `decide.shadow_rewritten`
  - 保留 `gan_shadow_diff_total` 的现有断言，确保两个指标语义清晰

### F-003 · `trace.input.config` 无 allowlist，未来易泄密

- **severity**: P2
- **status**: resolved (commit 704765d, 2026-05-12)
- **文件**: `gan_matchmaking/sre/self_iteration.py::_decide_locked`, `core/config.py`
- **影响面**: 潜在 PII / secret 泄漏，审计行污染
- **当前代码**:
  ```python
  trace: Dict[str, Any] = {
      "input": {
          "context": _context_payload(ctx),
          "config": self.config.to_dict(),   # ← 整个 AppConfig 无筛选地写进 trace
      },
      ...
  }
  ```
  现在 `AppConfig` 里没有敏感字段，但未来一定会加 Redis URL、DB DSN、API token、
  Slack webhook 等。SQLite `decisions.trace_json` 是 on-call 直接打开的审计表。
- **修复建议**:
  1. `AppConfig.to_trace_dict()` 走 **allowlist**：只序列化明确允许的字段，
     其余字段要么去掉、要么打 `"***"`。
  2. `ObservabilityConfig` 加一个 `trace_config_allowed_keys: tuple[str, ...]`。
  3. 在 ADR-0006 补一段 "what must never enter trace"。
  4. 测试里加一条 contract：当 AppConfig 里新增任何字段，强制 allowlist 检查。
- **必需测试**:
  - `test_trace_config_only_allowlisted_keys` — 构造带模拟 secret 字段的 AppConfig，
    断言 trace 里找不到该值
  - `test_trace_config_contract_locked` — 对 `to_trace_dict()` 的键集合做快照断言，
    防止未来悄悄加字段

---

## P3 · 重构债 / 中期修

### F-004 · `ctx.service` 在 `decide()` 里被 `setattr(..., "_deps", ...)` 副作用污染

- **severity**: P3
- **status**: resolved (commit 6834ab3, 2026-05-12)
- **文件**: `gan_matchmaking/sre/self_iteration.py::decide`
- **问题**:
  ```python
  setattr(ctx.service, "_deps", list(ctx.dependencies))
  ```
  如果 caller 复用同一个 `Service` 对象（HTTP handler 的常见模式），`_deps` 会跨决策
  累积。`Service` dataclass 上根本没有这个字段，调用方永远看不到它。
- **修复建议**:
  - 改用局部 dict `deps_by_service: Dict[str, List[str]]` 在 `_decide_locked` 内部流转。
  - 或者 `ReleaseContext` 自己持有 dependencies，`observe_release` / synergy 更新
    都从 ctx 拿，不给 Service 加偷偷的属性。
- **必需测试**:
  - `test_decide_does_not_mutate_service_object` — 两次 decide 不同 dependencies，
    断言 `ctx.service` 的公共字段不变、没有额外属性

### F-005 · `_service_player` / `_candidate_player` 里硬编码常数影响 artifact 稳定性

- **severity**: P3
- **status**: open
- **文件**: `gan_matchmaking/sre/artifacts.py`
- **问题**:
  ```python
  mu = 25.0 + 18.0 * (service.mu - 0.5) + 1.5 * service.win_streak - 1.0 * service.loss_streak
  sigma = max(1.0, 5.0 + 10.0 * service.sigma + 0.5 * service.loss_streak)
  ```
  这些常数参与 EOMM feature 构造。一旦改动，之前所有已 fit 的 retention artifact
  就和 runtime 输入对不上，决策会静默漂移。但现在没有任何 contract / test
  把这些常数 freeze 住。
- **修复建议**:
  1. 把这些常数抽到命名常量：`_MU_SCALE = 18.0`，`_WIN_STREAK_GAIN = 1.5` 等，
     注释说明来源和"修改影响所有历史 artifact"。
  2. 在 `ArtifactMetadata.extra` 里加 `rating_scaling_version: str`，artifact
     落地时 snapshot 当前常数。hydrate 时对比，不一致拒绝加载。
  3. 或者更彻底：`build_match_config` 完全由 feature 向量驱动，不再依赖 Player
     rating scaling。
- **必需测试**:
  - `test_rating_scaling_contract_snapshot` — 对固定输入断言 Player rating 的
    byte-level 输出，防止无意改动
  - `test_artifact_version_invalidates_on_scaling_change` — 修改常数应导致
    artifact load 时出 version mismatch

### F-006 · `sre/artifacts.py` 单文件过大（488 行）

- **severity**: P3
- **status**: open
- **影响面**: 可读性 / 导航
- **修复建议**: 拆成
  - `sre/artifacts/__init__.py` — re-export
  - `sre/artifacts/metadata.py` — `ArtifactMetadata` + `build_metadata` + `_stable_version`
  - `sre/artifacts/retention.py` — `RetentionArtifact` + save/load/validate + `build_history_vector` + `build_match_config`
  - `sre/artifacts/cox.py` — `CoxArtifact` + save/load/validate
  - `sre/artifacts/bundle.py` — `RuntimeArtifactBundle` + `load_runtime_artifacts`
- **必需测试**: 保持现有测试通过即可，禁止添加新测试（纯机械拆分）

### F-007 · `cli._ctx_from_dict` 被跨模块 `_` 私有 import

- **severity**: P3
- **status**: resolved (commit 2278868, 2026-05-12)
- **文件**:
  - `gan_matchmaking/service/app.py`: `from ..cli import _ctx_from_dict`
  - `gan_matchmaking/sre/replay.py`: `from ..cli import _ctx_from_dict`（间接使用其契约）
  - `tests/test_replay_corpus.py`, `tests/test_replay_export.py`, `tests/test_cli.py`
- **问题**: `_` 前缀表示私有，却被 3+ 个模块引用。任何 cli 重构都会大面积打破。
- **修复建议**:
  把 `_ctx_from_dict` 晋升到 `sre/domain.py::ReleaseContext.from_dict(payload)`
  或单独的 `sre/serde.py`，cli 只做 arg parsing + 调 serde。
- **必需测试**: 所有现有测试通过。改名后不允许再 import 私有成员（加 lint 规则
  或至少 review-level check）。

### F-008 · SQLite migration v5 有"列已存在跳过"特殊处理

- **severity**: P3
- **status**: open
- **文件**: `gan_matchmaking/persistence/sqlite.py::_migrate`
- **问题**:
  ```python
  if version == 5:
      cols = {row["name"] for row in self._conn.execute("PRAGMA table_info(decisions)")}
      if "artifact_version" in cols:
          # 插入 migration 记录但不执行 DDL
          ...
          continue
  ```
  针对 v5 写了特殊分支处理"列已存在"，这通常是为了兼容手工改过的旧库。
  但这破坏了迁移的"声明式、可审计"契约——未来任何 migration 都可能复制这个模式。
- **修复建议**:
  1. 如果确实需要 idempotent DDL，统一让所有 migration 写成 idempotent 形式
     （`ALTER TABLE ... ADD COLUMN IF NOT EXISTS`，SQLite 3.35+ 支持）
  2. 或者把 v5 特判挪到一个"adopt legacy schemas"的一次性启动任务里，不污染
     migration loop
  3. 补 ADR 解释为什么需要这个例外
- **必需测试**:
  - `test_migration_v5_idempotent` — 模拟老库已有 artifact_version 列，重新启动
    pipeline 不出错
  - 全量 migration 在空库上一次跑通的 snapshot 测试

---

## P4 · 文档 / 命名洁癖

### F-009 · `codex-handoff.md` 与 `implementation-roadmap.md` 内容重叠约 30%

- **severity**: P4
- **status**: open
- **修复建议**:
  - `codex-handoff.md` 只留：**当前状态 + 机制地图 + 下一位该做什么 + 风险边界**
  - `implementation-roadmap.md` 只留：**phase 定义 + PR 映射 + 未来方向**
  - "下一步建议"章节二选一，另一边链接过去

### F-010 · replay fixture 命名风格不统一

- **severity**: P4
- **status**: open
- **现有命名**:
  - `fallback_go.json`
  - `artifact_canary.json`
  - `budget_rollback.json`
  - `critical_tier_canary_downgrade.json`
  - `freeze_hold.json`
  - `risk_warn_canary.json`
  - `shadow_strategy_hold.json`
  - `unknown_strategy_escalate.json`
- **修复建议**: 统一成 `{scenario}_{expected_kind}.json` 模式，并在
  `tests/fixtures/replay/README.md` 写命名约定。现有 fixture 大部分已经
  是这个形态，只需要微调。

---

## 变更日志

| 日期 | 修改 |
|---|---|
| 2026-05 | 初版，基于 `gan-session` 分支评审 |
