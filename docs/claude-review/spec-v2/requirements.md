# Requirements v2 · C+A2 本轮

EARS-A2 句式：`WHEN <trigger> THE SYSTEM SHALL <observable behavior>`。

---

## F-005 · Rating scaling 合同

### R-305 · 常数抽成命名常量

**WHEN** 开发者阅读 `sre/artifacts/retention.py::_service_player` 与
`_candidate_player`,
**THE SYSTEM SHALL** 让所有 rating 换算系数以
`_RATING_*` 模块级常量形式出现,
**AND** 每个常量附注释说明其含义（如 `_RATING_MU_BASE = 25.0  # Elo scale pivot`)。

- finding: F-005
- 验证: grep `r'= 25\.0|= 18\.0|= 14\.0'` 在实现文件中只出现在常量定义行
- 反例（当前行为）: 魔法数字散布，改动无法 review

### R-306 · Rating scaling 版本哈希

**WHEN** artifact metadata 生成,
**THE SYSTEM SHALL** 在 `ArtifactMetadata.extra["rating_scaling_version"]`
写入一个稳定 hash,
**AND** hash 只依赖 `_RATING_*` 常量集合,
**AND** 常量改动后 hash 必然变化。

- finding: F-005
- 验证: `test_rating_scaling_version_changes_with_constant`
- 反例: 改了常数却不 bump version，runtime 与 artifact 悄悄漂移

### R-307 · Artifact 加载版本校验

**WHEN** runtime 启动加载 fitted artifact 且
`artifact.metadata.extra["rating_scaling_version"] != current_version()`,
**THE SYSTEM SHALL** 降级到 bootstrap 路径（不用该 artifact）,
**AND** 发出 `WARNING` 级 `artifacts.retention.scaling_mismatch` 日志,
**AND** 在 `trace["artifacts"]["rating_scaling_status"]` 写入
`"mismatch"`（默认值为 `"match"`）。

- finding: F-005
- 验证: `test_artifact_version_mismatch_downgrades_to_bootstrap`
- 反例: 常数改了但老 artifact 还被加载，决策静默漂移

### R-308 · 字节级 rating 输出快照

**WHEN** 给定一组固定的 `Service(mu=0.95, sigma=0.03, win_streak=2, loss_streak=0)`
与 `ReleaseCandidate(expected_success=0.99, canary_fraction=0.1)` 输入,
**THE SYSTEM SHALL** 让 `_service_player(...)` 返回的 `Player` 与
`_candidate_player(...)` 返回的 `Player` 的 `(mu, sigma)` 落在固定
精度快照里（relative tolerance 1e-9）。

- finding: F-005
- 验证: `test_rating_scaling_contract_snapshot`
- 反例: 无意改动 `_RATING_MU_BASE` 等常量，没测试能拦住

---

## F-006 · artifacts 包结构

### R-405 · 模块按职责分层

**WHEN** `sre/artifacts.py` 被拆分,
**THE SYSTEM SHALL** 使每个子模块的行数 ≤ 200 行,
**AND** 子模块职责互不重叠（metadata / retention / cox / bundle）,
**AND** 对外 API（`RuntimeArtifactBundle`, `load_runtime_artifacts`,
`build_match_config`, `build_history_vector`, `EOMM_FEATURE_NAMES`,
`ArtifactMetadata` 等）通过 `sre/artifacts/__init__.py` re-export。

- finding: F-006
- 验证: `wc -l gan_matchmaking/sre/artifacts/*.py` 所有文件 ≤ 200 行
  + 现有 import 路径（`from gan_matchmaking.sre.artifacts import ...`）不变
- 反例: 拆分后 import 路径变了，伤到 8 个调用点

### R-406 · 行为不变（零回归）

**WHEN** PR-fix-06 合入,
**THE SYSTEM SHALL** 使原有 `tests/test_sre_artifacts.py` 与
`tests/test_replay_corpus.py` 全部通过 **且不修改**,
**AND** 不新增"为让旧测试通过"的 shim 代码。

- finding: F-006
- 验证: `git diff tests/test_sre_artifacts.py` 在 PR-fix-06 中为空
- 反例: 拆分改变了行为，被迫调整测试

---

## F-007 · ReleaseContext.from_dict 公共 API

### R-505 · 公共 API 存在

**WHEN** 调用方需要从 JSON 构造 `ReleaseContext`,
**THE SYSTEM SHALL** 提供 `ReleaseContext.from_dict(payload: Mapping[str, Any])`
的 `@classmethod`,
**AND** 该方法的文档字符串描述其输入契约（service / candidates /
dependencies / error_budget_remaining / freeze_window / telemetry /
correlation_id）,
**AND** 在 `gan_matchmaking.sre.__init__` 导出。

- finding: F-007
- 验证: `from gan_matchmaking.sre import ReleaseContext; ReleaseContext.from_dict(...)`
- 反例: 外部仍要 import `_ctx_from_dict`

### R-506 · 历史私有 API 成为 thin alias

**WHEN** 调用 `gan_matchmaking.cli._ctx_from_dict(payload)`,
**THE SYSTEM SHALL** 返回与 `ReleaseContext.from_dict(payload)` 相同的对象,
**AND** 内部仅把调用转发给 `ReleaseContext.from_dict` 而不维护独立逻辑,
**AND** 在下一个 minor 版本的 release note 中标记 deprecation。

- finding: F-007
- 验证: `test_cli_helper_delegates_to_release_context`
- 反例: 两条路径各自演化，又漂移回 F-007

### R-507 · 调用点迁移

**WHEN** PR-fix-07 合入,
**THE SYSTEM SHALL** 使以下文件不再 import `_ctx_from_dict`:
`gan_matchmaking/service/app.py`、
`tests/test_replay_corpus.py`、
`tests/test_replay_export.py`,
**AND** 它们改用 `ReleaseContext.from_dict`。

- finding: F-007
- 验证: `grep -rn "_ctx_from_dict" gan_matchmaking/ tests/` 只在
  `gan_matchmaking/cli.py` 与 `tests/test_cli.py` 的 noqa 行中出现
- 反例: 私有 import 继续扩散

---

## F-008 · SQLite migration v5 正常化

### R-605 · 幂等 DDL

**WHEN** migration v5 在老库（已有 `artifact_version` 列）上重跑,
**THE SYSTEM SHALL** 跳过 DDL 但**仍**写入 migration 记录,
**AND** 不再需要针对 v5 的"列是否存在"特判分支,
**AND** 同样的保护扩展到未来所有 `ALTER TABLE ... ADD COLUMN` migration。

- finding: F-008
- 验证: `test_migration_v5_idempotent_on_legacy_db`
- 反例: 每加一次列都写特判

### R-606 · Migration 代码结构

**WHEN** 开发者新增一条 migration,
**THE SYSTEM SHALL** 使 `_migrate` 内仅含"版本 → SQL 列表"的映射,
**AND** 版本号、SQL、幂等标记集中在一处,
**AND** 任何 version 的"兼容性例外"必须挂 ADR 引用。

- finding: F-008
- 验证: code review check + `grep -n "if version == " gan_matchmaking/persistence/sqlite.py`
  结果只剩声明式比较
- 反例: 特判继续繁殖

---

## F-009 · 文档去重

### R-705 · 文档职责分工

**WHEN** 读者查阅 `docs/codex-handoff.md`,
**THE SYSTEM SHALL** 仅看到 4 大块：**当前状态 + 机制地图 + 下一位该做什么 + 风险边界**,
**AND** 查阅 `docs/implementation-roadmap.md` 时仅看到
**phase 定义 + PR 映射 + 未来方向**,
**AND** "下一步建议"只出现一次，另一边用链接指向。

- finding: F-009
- 验证: 人工对照 + `grep "下一步"` 结果集中在单一文档
- 反例: 双处更新、互相漂移

---

## F-010 · Fixture 命名统一

### R-710 · 命名约定

**WHEN** `tests/fixtures/replay/` 下新增 fixture,
**THE SYSTEM SHALL** 使文件名符合 `{scenario}_{expected_kind}.json` 模式,
**AND** `tests/fixtures/replay/README.md` 描述该约定与每个 fixture 的场景,
**AND** 现有 8 个 fixture 全部符合命名约定（必要时 rename 并同步
`test_replay_corpus.py` 的断言）。

- finding: F-010
- 验证: `tests/fixtures/replay/README.md` 存在 + 测试跑过
- 反例: 命名继续发散

---

## 共同契约（延续 2026-05）

- 所有新增测试 deterministic（不依赖 `sleep` / 真实时钟）
- 新增日志用 `JsonLineLogger`
- 新增 metric 在 `__post_init__` 注册，label 基数受控
- 本轮禁止改 `trace["stages"]["*"]` 字段语义
- 本轮禁止改 `Decision` 对外字段集
- 本轮禁止改 `/v1/*` HTTP API 路径

---

## 需求编号与 finding 的反查

| requirement | finding | 关联测试文件 |
|---|---|---|
| R-305 ~ R-308 | F-005 | `tests/test_sre_artifacts.py`（新增） |
| R-405 ~ R-406 | F-006 | 所有现有 artifact 测试 |
| R-505 ~ R-507 | F-007 | `tests/test_release_context_serde.py`（新建）+ 现有 replay tests |
| R-605 ~ R-606 | F-008 | `tests/test_persistence_sqlite.py`（新增） |
| R-705 | F-009 | 文档审计（人工） |
| R-710 | F-010 | `tests/test_replay_corpus.py` + `tests/fixtures/replay/README.md` |
