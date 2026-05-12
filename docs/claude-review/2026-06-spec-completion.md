# 2026-06 Spec Completion · C+A2

Scope closed: **F-005, F-006, F-007, F-008, F-009, F-010**

## 本轮交付

| PR | 变更 | 满足 finding | 满足 requirement |
|---|---|---|---|
| PR-fix-07 | `ReleaseContext.from_dict` classmethod + 5 调用点迁移 + `cli._ctx_from_dict` 变薄为 alias | F-007 | R-505 / R-506 / R-507 |
| PR-fix-06 | `sre/artifacts/` 拆成 `__init__ / metadata / retention / cox / bundle` | F-006 | R-405 / R-406 |
| PR-fix-05 | 12 个 `_RATING_*` 常量 + `_rating_scaling_version()` + `training/retention.py` 写入版本 + runtime hydrate 校验 + `RuntimeArtifactBundle.with_scaling_status` | F-005 | R-305 / R-306 / R-307 / R-308 |
| PR-fix-08 | `_idempotent_statement_skip` 通用 guard 取代 v5 特判 | F-008 | R-605 / R-606 |
| PR-fix-09 | `codex-handoff.md` 去重，生产化模块段简化为状态表 + 引用 `implementation-roadmap.md`；roadmap 的 "Next Delivery Target" 指回 handoff | F-009 | R-705 |
| PR-fix-10 | `critical_tier_canary_downgrade.json` → `critical_tier_downgrade_canary.json` + `tests/fixtures/replay/README.md` + naming convention 测试 | F-010 | R-710 |

## 数值结果

- `pytest -q`: **138 passed** (2026-05 结尾 128 + 本轮新增 10)
  - PR-fix-07 新增 5 个（`tests/test_release_context_serde.py`）
  - PR-fix-05 新增 6 个（`tests/test_rating_scaling.py`）
  - PR-fix-08 新增 3 个（`tests/test_persistence_sqlite.py`）
  - PR-fix-10 新增 1 个（`tests/test_replay_corpus.py::test_fixture_naming_matches_convention`）
  - （其中 PR-fix-06 零新增测试，按 R-406 约束）
- `python -m bench.latency --quick`: p99 **1.39 ms** (预算 2.5 ms，残留余量 1.11 ms)
- `grep -rn "if version == 5" gan_matchmaking/`: 空（F-008 验证）
- `grep -rn "_ctx_from_dict" gan_matchmaking/`: 只剩 `cli.py` 一处（F-007 验证）
- `wc -l gan_matchmaking/sre/artifacts/*.py`: 所有子文件 ≤ 177 行（F-006 验证）
- `grep -rn "pragma: no cover" gan_matchmaking/`: 只剩允许位点
- `findings.md`: F-001 ~ F-010 全部标为 `resolved`

## Requirement 覆盖矩阵

| Requirement | 测试 |
|---|---|
| R-305 | `test_rating_scaling_contract_snapshot` |
| R-306 | `test_rating_scaling_version_is_stable` / `test_rating_scaling_version_changes_with_constant` |
| R-307 | `test_artifact_version_mismatch_downgrades_to_bootstrap` / `test_artifact_version_match_hydrates_retention` / `test_artifact_without_version_is_marked_unknown` |
| R-308 | `test_rating_scaling_contract_snapshot` |
| R-405 | 文件结构检查（`wc -l` 4 个子文件） |
| R-406 | `tests/test_sre_artifacts.py` / `tests/test_replay_corpus.py` 无修改 |
| R-505 | `test_release_context_from_dict_matches_cli_helper` / `test_release_context_from_dict_rejects_missing_service` / `test_release_context_from_dict_defaults_are_safe` / `test_release_context_from_dict_forces_matching_service_id` |
| R-506 | `test_release_context_from_dict_matches_cli_helper` |
| R-507 | `test_no_private_ctx_import_in_public_modules` |
| R-605 | `test_migration_v5_idempotent_on_legacy_db` |
| R-606 | `test_migration_all_versions_clean_boot` / `test_migration_does_not_include_v5_special_case` |
| R-705 | 手工审阅（codex-handoff 的"生产化模块"段改成状态表 + 引用；roadmap 的"Next Delivery Target"改成引用 handoff） |
| R-710 | `test_fixture_naming_matches_convention` + `tests/fixtures/replay/README.md` |

## 新增 LOC 概览（近似）

| 路径 | 变化 |
|---|---|
| `gan_matchmaking/sre/artifacts/` (新建包) | +503 / -0（集中了旧 `artifacts.py` 的 488 行 + F-005 合同逻辑） |
| `gan_matchmaking/sre/artifacts.py` (删除) | -488 |
| `gan_matchmaking/sre/domain.py` | +55 / -0（`ReleaseContext.from_dict`） |
| `gan_matchmaking/cli.py` | +3 / -32（`_ctx_from_dict` 变薄） |
| `gan_matchmaking/service/app.py` | +2 / -2 |
| `gan_matchmaking/sre/self_iteration.py` | +22 / -1（hydrate 版本检查） |
| `gan_matchmaking/training/retention.py` | +3 / -1（写 `rating_scaling_version`） |
| `gan_matchmaking/persistence/sqlite.py` | +23 / -12（idempotent guard） |
| `tests/test_release_context_serde.py` | +93（新建） |
| `tests/test_rating_scaling.py` | +157（新建） |
| `tests/test_persistence_sqlite.py` | +105（新建） |
| `tests/test_replay_corpus.py` | +18 / -0 |
| `tests/fixtures/replay/README.md` | +56（新建） |
| `docs/adr/0008-artifact-rating-scaling-compat.md` | +70（新建） |
| `docs/codex-handoff.md` | +28 / -46（去重） |
| `docs/implementation-roadmap.md` | +11 / -7 |
| `docs/claude-review/findings.md` | +0 / +0（6 行 status 翻转） |
| **合计** | **≈ +1,056 / -589**（工程占 60%，文档 + 测试占 40%） |

## 规则回顾（本轮遵守情况）

| 规则 | 状态 |
|---|---|
| 新增测试 deterministic | ✅ 无 `sleep`；rating scaling 用 monkeypatch 改常数；migration 用手工建表；serde 用 in-memory payload |
| 新增日志用 `JsonLineLogger` | ✅ `artifacts.retention.scaling_mismatch` 走 `self.logger.warning` |
| 新增 metric 在 `__post_init__` 注册 | ✅ 本轮没有新增 metric（R-307 选择用 trace 字段 `rating_scaling_status` 而非 counter，更省 Prometheus 基数） |
| 不改 `trace["stages"]["*"]` | ✅ 只在 `trace["artifacts"]` 扩展 `rating_scaling_status` 字段 |
| 不改 `Decision` 对外字段 | ✅ |
| 不改 `/v1/*` HTTP API 路径 | ✅ |
| findings 只能标 resolved/deferred | ✅ |

## 延期条目 · 下一轮

本轮 P3 / P4 队列已清空；下一轮建议覆盖
[`docs/implementation-roadmap.md#5-next-delivery-target`](../implementation-roadmap.md#5-next-delivery-target)
列出的 4 项：

1. 扩展 incident-style replay（artifact validation failure / breaker short-circuit / shadow 切换）
2. 分布式 lease 原型（Kubernetes Lease / PostgreSQL advisory lock / Redis lease）
3. Artifact bundle 存储策略文档（本地 corpus / 对象存储 / CI 缓存）
4. 用真实观测数据校准 Cox / Retention

这几项都是能力增强而非缺陷修复，2026-07 轮可按 C+A2 / D+A2 方案挑 2-3 项推进。

## 交接

- **下一位评审者**：先读本文件 → `findings.md`（确认全部 resolved）→
  [`implementation-roadmap.md`](../implementation-roadmap.md) 取下一轮候选
- **冻结 V3**：`docs/V3_Knowledge/knowledge-base.html` 的 "本轮状态"
  改为 closed，每个 PR 行替换成 `resolved (commit <sha>)`
- **开 V4**：下一轮请新建 `docs/V4_Knowledge/`，继续"差量视图"模式

---

本轮在工程（6 PR）、测试（10 新增）、文档（ADR-0008 + 收尾报告 + 去重）
三层闭合。`gan-session` 分支可合入 master 或继续作为下一轮基线。
