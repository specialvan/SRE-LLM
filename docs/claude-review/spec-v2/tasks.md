# Implementation Plan v2 · C+A2 本轮

本文是本轮唯一的 **编码活动** 清单。每条任务：

- 有唯一 task id（`T-XXX`）
- 显式引用需满足的 requirement id（`R-XXX`，来自
  [`requirements.md`](requirements.md)）
- 只命名要改的文件 / 符号 / 测试函数
- 不涉及审阅 / 状态更新 / 报告撰写（那些在本文末尾的「验收与收尾」中
  单独列出，不在编码活动内）

PR 依赖顺序：`PR-fix-07` → `PR-fix-06` → `PR-fix-05` → `PR-fix-08` →
`PR-fix-09` → `PR-fix-10`（07 / 06 / 05 之间是串行，08 / 09 / 10 互相独立，
可并行）。理由见 [`README.md`](README.md)。

---

## PR-fix-07 · ReleaseContext.from_dict 公共 API

> 满足的 requirements: **R-505 / R-506 / R-507**
>
> 先做：纯加法 + 替换，避免 06/05 扩散时再返工。

### T-705 · 在 ReleaseContext 上新增 from_dict classmethod

- 文件: `gan_matchmaking/sre/domain.py`
- 符号: `ReleaseContext.from_dict`
- 动作: 新增 `@classmethod from_dict(cls, payload: Mapping[str, Any])`，
  把 `gan_matchmaking/cli.py::_ctx_from_dict` 的函数体原封复制过来，
  内部 `from .errors import DataError` 改为包级现有引用。文档字符串按
  [`design.md#f-007`](design.md#f-007--releasecontextfrom_dict-公共-api)
  列出的字段契约。
- 参考补丁: [`../patches/F-007-release-context-from-dict.md`](../patches/F-007-release-context-from-dict.md)
- Requirement: R-505

### T-706 · cli._ctx_from_dict 变为 thin alias

- 文件: `gan_matchmaking/cli.py`
- 符号: `_ctx_from_dict`
- 动作: 整个函数体替换为
  `return ReleaseContext.from_dict(payload)`，docstring 加
  `Deprecated: use ReleaseContext.from_dict instead.`，顶部 import
  `from .sre.domain import ReleaseContext` 保留（本来就有）。
- Requirement: R-506

### T-707 · HTTP app 改用公共 API

- 文件: `gan_matchmaking/service/app.py`
- 动作:
  1. 删除 `from ..cli import _ctx_from_dict`
  2. 在 import 区追加 `from ..sre import ReleaseContext`（`ReleaseContext`
     应已在 `sre/__init__.py` 导出；若未导出见 T-710）
  3. `handle_decide` 内 `ctx = _ctx_from_dict(body)` → `ctx = ReleaseContext.from_dict(body)`
- Requirement: R-507

### T-708 · replay corpus 测试改用公共 API

- 文件: `tests/test_replay_corpus.py`
- 动作: 顶部 `from gan_matchmaking.cli import _ctx_from_dict` 改为
  `from gan_matchmaking.sre import ReleaseContext`；两处调用 `_ctx_from_dict(...)`
  改为 `ReleaseContext.from_dict(...)`
- Requirement: R-507

### T-709 · replay export 测试改用公共 API

- 文件: `tests/test_replay_export.py`
- 动作: 同 T-708 的替换模式；注意此文件有 5 处调用点
- Requirement: R-507

### T-710 · 确认 sre 包对外导出 ReleaseContext

- 文件: `gan_matchmaking/sre/__init__.py`
- 动作: 若 `ReleaseContext` 不在 `__all__`，追加；已在则无需改
- Requirement: R-505

### T-711 · 文档注释同步（docstring 中的 `cli._ctx_from_dict` 路标）

- 文件:
  - `gan_matchmaking/sre/self_iteration.py` L105 (`_context_payload` 的 docstring)
  - `gan_matchmaking/service/__init__.py` L20
- 动作: 把 `cli._ctx_from_dict` 字样改为 `ReleaseContext.from_dict`
- Requirement: R-506（文档对外契约保持一致）

### T-712 · 测试 test_release_context_from_dict_roundtrip

- 文件: **新建** `tests/test_release_context_serde.py`
- 签名: `def test_release_context_from_dict_roundtrip(): ...`
- 断言:
  - 构造一个 payload（含 `service`, `candidates`, `dependencies`,
    `error_budget_remaining`, `freeze_window`, `telemetry`, `correlation_id`）
  - `ctx = ReleaseContext.from_dict(payload)`
  - 逐字段比较 `ctx.service.id`、`ctx.candidates[0].id`、
    `ctx.error_budget_remaining`、`ctx.freeze_window`、`ctx.telemetry`、
    `ctx.correlation_id`、`ctx.dependencies`
- Requirement: R-505

### T-713 · 测试 test_cli_helper_delegates_to_release_context

- 文件: `tests/test_release_context_serde.py`
- 签名: `def test_cli_helper_delegates_to_release_context(): ...`
- 断言: `cli._ctx_from_dict(payload) == ReleaseContext.from_dict(payload)`
  （两者对同一 payload 返回结构等价对象；用逐字段比较或 asdict 对比）
- Requirement: R-506

### T-714 · 测试 test_private_helper_not_imported_outside_cli

- 文件: `tests/test_release_context_serde.py`
- 签名: `def test_private_helper_not_imported_outside_cli(): ...`
- 手法: 读 `gan_matchmaking/service/app.py` 与
  `tests/test_replay_corpus.py`、`tests/test_replay_export.py` 的源文件文本，
  用 `"_ctx_from_dict" not in src` 断言
- Requirement: R-507

---

## PR-fix-06 · artifacts 包结构拆分（机械）

> 满足的 requirements: **R-405 / R-406**
>
> 禁止改行为。拆分完成后运行全量测试，零改动全绿即收工。

### T-605 · 创建 artifacts 包目录

- 动作: 在 `gan_matchmaking/sre/` 下新建 `artifacts/` 目录 + 四个子文件
  占位（空）：
  - `artifacts/__init__.py`
  - `artifacts/metadata.py`
  - `artifacts/retention.py`
  - `artifacts/cox.py`
  - `artifacts/bundle.py`
- Requirement: R-405（结构）

### T-606 · 迁移 metadata 部分

- 源: `gan_matchmaking/sre/artifacts.py` 中 `ArtifactMetadata`、
  `_stable_version`、`_build_id`、`_json_safe` 相关 symbols
- 目标: `gan_matchmaking/sre/artifacts/metadata.py`
- 动作: 移动原文件段（含其依赖的 imports），不改动函数 / 方法签名
- Requirement: R-405

### T-607 · 迁移 retention 部分

- 源: `gan_matchmaking/sre/artifacts.py` 中
  `RetentionArtifact`、`_service_player`、`_candidate_player`、
  `build_match_config`、`build_history_vector`、`EOMM_FEATURE_NAMES`
- 目标: `gan_matchmaking/sre/artifacts/retention.py`
- 动作: 移动，保持所有公开符号名不变
- Requirement: R-405 / R-406

### T-608 · 迁移 cox 部分

- 源: `gan_matchmaking/sre/artifacts.py` 中 `CoxArtifact` 及其辅助
- 目标: `gan_matchmaking/sre/artifacts/cox.py`
- Requirement: R-405

### T-609 · 迁移 bundle 部分

- 源: `gan_matchmaking/sre/artifacts.py` 中
  `RuntimeArtifactBundle`、`load_runtime_artifacts`
- 目标: `gan_matchmaking/sre/artifacts/bundle.py`
- Requirement: R-405

### T-610 · artifacts/__init__.py re-export

- 文件: `gan_matchmaking/sre/artifacts/__init__.py`
- 动作: 按 [`design.md#f-006`](design.md#f-006--artifacts-包结构) 列出的
  10 个符号写 re-export + `__all__`
- Requirement: R-405（对外 import 路径不变）

### T-611 · 删除旧单文件

- 文件: `gan_matchmaking/sre/artifacts.py`（旧）
- 动作: 删除（所有内容已迁移）
- Requirement: R-406

### T-612 · 各子模块 ≤ 200 行断言

- 动作: 拆分后手工检查 `wc -l gan_matchmaking/sre/artifacts/*.py`，
  每文件 ≤ 200；超过的就在 T-607/T-608 里进一步拆（优先按"私有
  helper 下沉到内部 `_helpers.py`"）
- Requirement: R-405

### T-613 · 零回归运行既有测试

- 动作: `pytest tests/test_sre_artifacts.py tests/test_replay_corpus.py
  tests/test_training_retention.py -v`
- 要求: **不修改**任何测试文件内容。如果失败，回到 T-606~T-611 复核
  位置 / 符号名，不允许改测试
- Requirement: R-406

---

## PR-fix-05 · Rating scaling 合同

> 满足的 requirements: **R-305 / R-306 / R-307 / R-308**
>
> 基于 PR-fix-06 拆分后的新结构。所有改动集中在 `artifacts/retention.py`
> 与 `self_iteration.py` 两处。

### T-505 · 抽常数

- 文件: `gan_matchmaking/sre/artifacts/retention.py`
- 动作: 在 `_service_player` 定义之前按
  [`design.md#f-005`](design.md#f-005--rating-scaling-合同)
  列出 12 个 `_RATING_*` 模块级常量，每个带行内注释
- Requirement: R-305

### T-506 · 替换函数体使用常量

- 文件: `gan_matchmaking/sre/artifacts/retention.py`
- 符号: `_service_player`、`_candidate_player`
- 动作: 把魔法数字 `25.0 / 18.0 / 1.5 / -1.0 / 1.0 / 5.0 / 10.0 / 0.5 /
  -14.0 / 20.0 / 4.0` 全部替换为对应 `_RATING_*` 常量。数值不变
- Requirement: R-305

### T-507 · 新增 _rating_scaling_version 纯函数

- 文件: `gan_matchmaking/sre/artifacts/retention.py`
- 符号: `_rating_scaling_version() -> str`
- 动作: 按 [`design.md#f-005`](design.md#f-005--rating-scaling-合同)
  写一个 SHA-256 前 12 位的稳定 hash；必须是 **纯函数**（零副作用）
- Requirement: R-306

### T-508 · 把 scaling version 写入 metadata.extra

- 文件: `gan_matchmaking/training/retention.py`（retention artifact 保存处）
- 动作: 在构造 `ArtifactMetadata(extra=...)` 时把
  `"rating_scaling_version": _rating_scaling_version()` 加入 extra dict
- Requirement: R-306

### T-509 · Runtime hydration 加 mismatch 检查

- 文件: `gan_matchmaking/sre/self_iteration.py`
- 符号: `SelfIterationPipeline._hydrate_runtime_artifacts`
  （或当前 artifact 加载入口，名字以实际为准）
- 动作: artifact 加载后比较
  `retention.metadata.extra.get("rating_scaling_version")` 与
  `_rating_scaling_version()`；不匹配则走降级路径（不 hydrate，返回
  bootstrap），并发 `self.logger.warning("artifacts.retention.scaling_mismatch", ...)`
- Requirement: R-307

### T-510 · Bundle 暴露 rating_scaling_status

- 文件: `gan_matchmaking/sre/artifacts/bundle.py`
- 符号: `RuntimeArtifactBundle`
- 动作: 新增只读字段 `rating_scaling_status: str`（默认 `"unknown"`，
  可选 `"match"` / `"mismatch"`），以及
  `_with_scaling_status(status: str) -> RuntimeArtifactBundle`
  immutable helper（返回带新状态的新 bundle）。`as_trace()` 输出里加
  `"rating_scaling_status"` 字段
- Requirement: R-307

### T-511 · 测试 test_rating_scaling_constants_grouped

- 文件: `tests/test_sre_artifacts.py`
- 签名: `def test_rating_scaling_constants_grouped(): ...`
- 手法: 读 `gan_matchmaking/sre/artifacts/retention.py` 源文件文本，
  断言所有 rating 相关魔法数字（`25.0`、`18.0`、`1.5`、`-1.0`、`5.0`、
  `10.0`、`0.5`、`-14.0`、`20.0`、`4.0`）只出现在 `_RATING_*` 定义行
- Requirement: R-305

### T-512 · 测试 test_rating_scaling_version_is_stable

- 文件: `tests/test_sre_artifacts.py`
- 签名: `def test_rating_scaling_version_is_stable(): ...`
- 断言: 两次 `_rating_scaling_version()` 返回同一字符串，长度 12，
  全小写 hex
- Requirement: R-306

### T-513 · 测试 test_rating_scaling_version_changes_with_constant

- 文件: `tests/test_sre_artifacts.py`
- 签名: `def test_rating_scaling_version_changes_with_constant(monkeypatch): ...`
- 断言:
  - 记录 `v_before = _rating_scaling_version()`
  - `monkeypatch.setattr(retention, "_RATING_MU_SLOPE", retention._RATING_MU_SLOPE + 1.0)`
  - `v_after = _rating_scaling_version()`
  - `assert v_before != v_after`
- Requirement: R-306

### T-514 · 测试 test_artifact_version_mismatch_downgrades_to_bootstrap

- 文件: `tests/test_sre_artifacts.py`
- 签名: `def test_artifact_version_mismatch_downgrades_to_bootstrap(tmp_path): ...`
- 手法: 保存一个 RetentionArtifact 且其
  `metadata.extra["rating_scaling_version"]` 设为 `"stale-hash"`；用
  `SelfIterationPipeline` hydrate
- 断言:
  - `pipeline.artifacts.rating_scaling_status == "mismatch"`
  - `pipeline.artifacts.retention is None`（或等价的"未加载"标记）
  - 捕获日志中出现 `artifacts.retention.scaling_mismatch`
- Requirement: R-307

### T-515 · 测试 test_rating_scaling_contract_snapshot

- 文件: `tests/test_sre_artifacts.py`
- 签名: `def test_rating_scaling_contract_snapshot(): ...`
- 断言:
  - `svc = Service(mu=0.95, sigma=0.03, win_streak=2, loss_streak=0, ...)`
  - `cand = ReleaseCandidate(expected_success=0.99, canary_fraction=0.1, ...)`
  - `p_svc = _service_player(svc)`；断言 `p_svc.mu` 与 `p_svc.sigma`
    在 `pytest.approx(..., rel=1e-9)` 内匹配预计算值
  - `p_cand = _candidate_player(cand)`；同样断言
- Requirement: R-308

### T-516 · 测试 test_bundle_as_trace_includes_scaling_status

- 文件: `tests/test_sre_artifacts.py`
- 签名: `def test_bundle_as_trace_includes_scaling_status(): ...`
- 断言: 默认 bundle 的 `as_trace()` 返回包含
  `"rating_scaling_status"` 键，且值为 `"unknown"` 或 `"match"` / `"mismatch"`
  之一
- Requirement: R-307（trace 输出契约）

---

## PR-fix-08 · SQLite migration v5 正常化

> 满足的 requirements: **R-605 / R-606**

### T-805 · 重写 _migrate 为声明式

- 文件: `gan_matchmaking/persistence/sqlite.py`
- 符号: `_migrate` 方法
- 动作: 按 [`design.md#f-008`](design.md#f-008--sqlite-migration-v5-正常化)
  的目标结构重写：删除 `if version == 5:` 特判块，全部 migration 走同一
  `for v, statements in _MIGRATIONS:` 循环
- Requirement: R-605 / R-606

### T-806 · 将 v5 DDL 改为 idempotent

- 文件: `gan_matchmaking/persistence/sqlite.py`
- 动作: 将 `_MIGRATIONS` 表中 v5 的 SQL 从
  `ALTER TABLE decisions ADD COLUMN artifact_version TEXT;` 改为
  `ALTER TABLE decisions ADD COLUMN IF NOT EXISTS artifact_version TEXT;`
  （SQLite ≥ 3.35 支持）
  备用方案: 若项目必须支持 SQLite < 3.35，加一个统一的
  `_apply_add_column(table, column, sql_type)` helper，先 `PRAGMA
  table_info` 查列，缺失才 DDL；但 **禁止**在 `_migrate` 内 inline 判分支
- Requirement: R-605

### T-807 · 测试 test_migration_v5_idempotent_on_legacy_db

- 文件: `tests/test_persistence_sqlite.py`（若无则新建）
- 签名: `def test_migration_v5_idempotent_on_legacy_db(tmp_path): ...`
- 手法:
  - 用裸 `sqlite3.connect` 建一个老库（含 `decisions` 表但已手工加了
    `artifact_version` 列）
  - 实例化 `SQLitePipelineStore(path)`；不应抛异常
  - 查询 `SELECT version FROM schema_migrations ORDER BY version`，应
    包含 v5
- Requirement: R-605

### T-808 · 测试 test_migration_v5_on_empty_db

- 文件: `tests/test_persistence_sqlite.py`
- 签名: `def test_migration_v5_on_empty_db(tmp_path): ...`
- 断言: 空库启动后 `PRAGMA table_info(decisions)` 包含
  `artifact_version` 列；`schema_migrations` 表里 v1..v5 全部存在
- Requirement: R-605（反向保护，回归）

### T-809 · 测试 test_no_version_specific_branches_in_migrate

- 文件: `tests/test_persistence_sqlite.py`
- 签名: `def test_no_version_specific_branches_in_migrate(): ...`
- 手法: 读 `gan_matchmaking/persistence/sqlite.py` 源码文本，断言
  `"if version == " not in src`（允许 `ADR-XXX` 引用注释形式的例外
  说明，但代码层无特判）
- Requirement: R-606

---

## PR-fix-09 · 文档去重

> 满足的 requirements: **R-705**
>
> 本 PR 仅改 `.md`，不改代码 / 测试。

### T-905 · codex-handoff.md 精简

- 文件: `docs/codex-handoff.md`
- 动作:
  1. 保留 4 块：**当前状态** / **机制地图** / **下一位该做什么** /
     **风险边界**
  2. 删除与 `implementation-roadmap.md` 重叠的 "下一步建议" 章节 ±
     30% 文字量
  3. 在 "下一位该做什么" 段末尾追加一行
     `> 完整 phase / PR 映射见 [`implementation-roadmap.md`](implementation-roadmap.md)`
- Requirement: R-705

### T-906 · implementation-roadmap.md 精简

- 文件: `docs/implementation-roadmap.md`
- 动作:
  1. 保留 3 块：**Phase 定义** / **PR 映射表** / **未来方向**
  2. 删除与 `codex-handoff.md` 重叠的 "当前状态快照" 章节
  3. 顶部追加一行
     `> 当前状态 / 分支 / 机制地图见 [`codex-handoff.md`](codex-handoff.md)`
- Requirement: R-705

### T-907 · 交叉链接审计

- 文件: `docs/codex-handoff.md` 与 `docs/implementation-roadmap.md`
- 动作: 所有 `ADR-XXXX`、`F-XXX`、`R-XXX`、`T-XXX` 引用改为链接到
  对应的 .md 文件；重复说明只保留其中一处
- Requirement: R-705

---

## PR-fix-10 · Fixture 命名统一

> 满足的 requirements: **R-710**

### T-1005 · Rename 不合规的 fixture 文件

- 文件: `tests/fixtures/replay/critical_tier_canary_downgrade.json`
- 动作: 使用版本控制的 rename 到
  `tests/fixtures/replay/critical_tier_downgrade_canary.json`
  （git mv，保留历史）
- Requirement: R-710

### T-1006 · 同步 test_replay_corpus.py 断言

- 文件: `tests/test_replay_corpus.py`
- 动作: 如该测试通过 fixture 文件名驱动，更新硬编码 / fixture 列表
  中的新文件名
- Requirement: R-710

### T-1007 · 新建 fixtures/replay/README.md

- 文件: **新建** `tests/fixtures/replay/README.md`
- 动作: 按 [`design.md#f-010`](design.md#f-010--fixture-命名统一)
  的模板写入（命名约定 + 8 行 catalog 表）
- Requirement: R-710

### T-1008 · 测试 test_fixture_naming_convention

- 文件: `tests/test_replay_corpus.py`
- 签名: `def test_fixture_naming_convention(): ...`
- 手法: 遍历 `tests/fixtures/replay/*.json`，对每个文件名验证
  匹配正则 `^[a-z0-9_]+_(go|canary|hold|rollback|escalate)\.json$`
- Requirement: R-710

---

## 任务依赖矩阵

```
PR-fix-07
  T-705 → T-706 → T-707 → T-708 → T-709 → T-710 → T-711
  T-712..T-714 依赖 T-705~T-707

PR-fix-06  (依赖 PR-fix-07 合入)
  T-605 → T-606 → T-607 → T-608 → T-609 → T-610 → T-611
  T-612 / T-613 作为 PR gate

PR-fix-05  (依赖 PR-fix-06 合入)
  T-505 → T-506 → T-507 → T-508 → T-509 → T-510
  T-511..T-516 依赖 T-505~T-510

PR-fix-08  (独立, 可与 09/10 并行)
  T-805 → T-806
  T-807..T-809 依赖 T-805/T-806

PR-fix-09  (独立, 纯文档)
  T-905 / T-906 / T-907 可并行

PR-fix-10  (独立)
  T-1005 → T-1006
  T-1007 / T-1008 可并行
```

---

## 验收与收尾（非编码活动）

以下**不是**编码任务，但列出以明确 PR 完结的判定与归档动作。实际跑的
命令与断言来自 [`verification.md`](verification.md)。

- **验收 1**: 执行 `pytest -q`，期望 `≥ 135 passed`（123 + 新增 ~12）。
- **验收 2**: 执行 `python -m bench.latency --quick`，期望 `p99 < 2.5 ms`。
- **验收 3**: 执行 `grep -rn "_ctx_from_dict" gan_matchmaking/ tests/`，
  结果只在 `cli.py` 与 `tests/test_cli.py` 中出现。
- **验收 4**: 执行 `grep -rn "if version ==" gan_matchmaking/persistence/`，
  结果为空（允许的 ADR 引用注释在文件开头，不在代码段）。
- **验收 5**: `wc -l gan_matchmaking/sre/artifacts/*.py`，每行 ≤ 200。
- **归档 1**: 把 `docs/claude-review/findings.md` 中 F-005 / F-006 /
  F-007 / F-008 / F-009 / F-010 的 `status` 从 `open` 改为
  `resolved (commit <sha>, 2026-06-xx)`。
- **归档 2**: 新建 `docs/claude-review/2026-06-spec-completion.md`，
  参照 `2026-05-spec-completion.md` 的结构填写。
- **归档 3**: 新建 `docs/V3_Knowledge/knowledge-base.html` + `README.md`
  快照（本轮冻结），`docs/V2_Knowledge/` 保持不变。
- **归档 4**: 新建 `docs/adr/0008-artifact-rating-scaling-compatibility.md`，
  正式化 F-005 的版本合同规则。

---

## Requirement → Task 反查

| Requirement | Task(s) |
|---|---|
| R-305 | T-505, T-506, T-511 |
| R-306 | T-507, T-508, T-512, T-513 |
| R-307 | T-509, T-510, T-514, T-516 |
| R-308 | T-515 |
| R-405 | T-605 ~ T-612 |
| R-406 | T-611, T-613 |
| R-505 | T-705, T-710, T-712 |
| R-506 | T-706, T-711, T-713 |
| R-507 | T-707, T-708, T-709, T-714 |
| R-605 | T-805, T-806, T-807, T-808 |
| R-606 | T-805, T-809 |
| R-705 | T-905, T-906, T-907 |
| R-710 | T-1005, T-1006, T-1007, T-1008 |

**所有 R-XXX 都有至少两条 Task 覆盖**（实现 + 测试，除纯文档 R-705
由三条文档任务覆盖），符合"可执行 spec"的最低契约。
