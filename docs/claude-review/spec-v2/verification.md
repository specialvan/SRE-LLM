# Verification v2 · C+A2 本轮

本文列出**验证命令 / 快照断言 / 契约快照**。跑通全部即达成本轮 DoD。

---

## 1. 按 PR 验证

### PR-fix-07 · ReleaseContext.from_dict

```powershell
# R-505 / R-506 / R-507
python -m pytest tests/test_release_context_serde.py -v
python -m pytest tests/test_replay_corpus.py tests/test_replay_export.py -v
python -m pytest tests/test_cli.py -v

# 私有 import 残留检查（R-507）
Select-String -Path gan_matchmaking\*\*.py, tests\*.py -Pattern "_ctx_from_dict" `
  | Where-Object { $_.Filename -notin @("cli.py", "test_cli.py") }
# 期望: 空结果
```

期望：
- `test_release_context_serde.py` 全绿（3 个新测试）
- `test_replay_corpus.py` / `test_replay_export.py` **不修改**的前提下全绿
- 私有 import 扫描结果为空

### PR-fix-06 · artifacts 包拆分

```powershell
# R-405: 结构
Get-ChildItem gan_matchmaking\sre\artifacts\ -File | `
  ForEach-Object { "$($_.Name): $((Get-Content $_.FullName | Measure-Object -Line).Lines) lines" }
# 期望: 每个文件 ≤ 200 行

# R-406: 零回归
python -m pytest tests/test_sre_artifacts.py tests/test_replay_corpus.py `
  tests/test_training_retention.py -v

# 契约检查: 旧 import 路径仍能工作
python -c "from gan_matchmaking.sre.artifacts import ArtifactMetadata, RetentionArtifact, CoxArtifact, RuntimeArtifactBundle, load_runtime_artifacts, build_history_vector, build_match_config, EOMM_FEATURE_NAMES; print('ok')"
```

### PR-fix-05 · Rating scaling 合同

```powershell
# R-305 / R-306 / R-307 / R-308
python -m pytest tests/test_sre_artifacts.py -v -k "scaling or rating"

# 魔法数字残留扫描（R-305）
Select-String -Path gan_matchmaking\sre\artifacts\retention.py `
  -Pattern "[^_a-zA-Z]25\.0|[^_a-zA-Z]18\.0|[^_a-zA-Z]14\.0" | `
  Where-Object { $_.Line -notmatch "_RATING_" }
# 期望: 空结果（所有魔法数字仅出现在 _RATING_* 定义行）
```

期望输出快照（T-515 snapshot test 锁定的数值，仅作为 review 参考；
真实断言在 `test_rating_scaling_contract_snapshot`）：

```
Service(mu=0.95, sigma=0.03, win_streak=2, loss_streak=0)
  → Player(mu ≈ 36.1, sigma ≈ 5.3)

ReleaseCandidate(expected_success=0.99, canary_fraction=0.1)
  → Player(mu ≈ 32.42, sigma ≈ 6.005)
```

### PR-fix-08 · SQLite migration 正常化

```powershell
# R-605 / R-606
python -m pytest tests/test_persistence_sqlite.py -v

# 特判残留扫描
Select-String -Path gan_matchmaking\persistence\sqlite.py -Pattern "if version =="
# 期望: 空结果（或仅在 ADR 引用注释中）
```

### PR-fix-09 · 文档去重

```powershell
# R-705: 人工 diff
git diff --stat docs/codex-handoff.md docs/implementation-roadmap.md
# 期望: 两份都变薄，总行数显著下降

# "下一步建议"字样只出现在一处
Select-String -Path docs\*.md -Pattern "下一步建议|下一位该做什么"
# 期望: 只在 codex-handoff.md 出现一处
```

### PR-fix-10 · Fixture 命名

```powershell
# R-710
python -m pytest tests/test_replay_corpus.py -v -k fixture

# 命名约定
Get-ChildItem tests\fixtures\replay\*.json | `
  Where-Object { $_.Name -notmatch '^[a-z0-9_]+_(go|canary|hold|rollback|escalate)\.json$' }
# 期望: 空结果

Test-Path tests\fixtures\replay\README.md
# 期望: True
```

---

## 2. 全局验收命令

合并所有 PR 后运行：

```powershell
# 全套测试
python -m pytest -q
# 期望: ≥ 135 passed

# 性能 SLO
python -m bench.latency --quick 2>$null
# 期望: p99 < 2.5 ms；$LASTEXITCODE = 0

# 覆盖率（可选）
python -m pytest --cov=gan_matchmaking --cov-report=term-missing
# 期望: 关键模块覆盖率 ≥ 85%

# 静态扫描
Select-String -Path gan_matchmaking\**\*.py -Pattern "pragma: no cover" | `
  Where-Object { $_.Line -notmatch "HTTP boundary|last-resort" }
# 期望: 空结果（只保留明确允许的 pragma）
```

---

## 3. 契约快照

### Metric 契约（不变）

本轮**不新增** metric。继续保持以下集合稳定：

| Metric | Type | Labels |
|---|---|---|
| `gan_decisions_total` | counter | `kind`, `risk_level` |
| `gan_shadow_diff_total` | counter | `suppressed_kind` |
| `gan_lease_refresh_failures_total` | counter | `reason` |
| `gan_breaker_state` | gauge | — |
| `gan_stage_latency_seconds` | histogram | `stage` |

### Log 事件契约（新增一条）

本轮新增：`artifacts.retention.scaling_mismatch`（WARNING）

| Event | Level | Payload |
|---|---|---|
| `artifacts.retention.scaling_mismatch` | WARNING | `expected`, `actual`, `artifact_version` |

### Trace schema 契约（可选字段新增）

`trace["artifacts"]` 新增可选键 `"rating_scaling_status"`，值域
`"match" / "mismatch" / "unknown"`。默认 `"unknown"`（兼容老 trace）。

其余 `trace["input"]["config"]` / `trace["stages"]["*"]` / `trace["decision"]`
**无改动**。

### Public API 契约

本轮**新增**：

- `gan_matchmaking.sre.ReleaseContext.from_dict(payload: Mapping) -> ReleaseContext`
  （classmethod）

**已废弃**：

- `gan_matchmaking.cli._ctx_from_dict(payload)` —— 保留为 thin alias；
  下个 minor 版本移除（至少提供 2 个周期的 deprecation window）

---

## 4. 全局收尾（归档模板）

PR 全部合入后：

1. 更新 `docs/claude-review/findings.md`：F-005 / F-006 / F-007 / F-008 /
   F-009 / F-010 的 `status` → `resolved (commit <sha>, 2026-06-xx)`。
2. 新建 `docs/claude-review/2026-06-spec-completion.md`：
   - Scope: F-005 / F-006 / F-007 / F-008 / F-009 / F-010
   - Commits: 6 条（PR-fix-05 ~ PR-fix-10）
   - Requirement 覆盖矩阵（抄本文 section 1 的 PR → R-XXX 映射）
   - 数值结果：`pytest` / `bench` / grep 扫描的结果
   - 新增代码统计（`git diff --stat` 汇总）
   - 未覆盖条目（本轮 10 条已清空，无）
   - 规则回顾（本轮遵守情况表）
3. 新建 `docs/adr/0008-artifact-rating-scaling-compatibility.md`：
   - Context: F-005 合同的动机（artifact 静默漂移问题）
   - Decision: `_RATING_*` 常量集 + `rating_scaling_version` hash 写入
     metadata + hydration 不匹配走 bootstrap
   - Consequences: 常数修改时的人工流程（bump commit 消息 +
     考虑 artifact 重训）
4. 新建 `docs/V3_Knowledge/knowledge-base.html` + `README.md` 快照，
   **`docs/V2_Knowledge/` 保持不动** 作为 2026-05 的冻结基线。
5. 更新 `docs/codex-handoff.md` 顶部路标指向 V3 Knowledge + 本轮
   completion 文档。

---

## 5. 风险与回退

- **PR-fix-05** 是本轮唯一有"行为变更"风险的 PR（hydration 的
  mismatch 降级路径）。部署前在 staging 上用真实 artifact 跑一次
  hydration 观察 `rating_scaling_status` 标签与日志。
- **PR-fix-06** 是机械拆分，风险最低，但需确认 `sys.modules` 里旧
  路径 `gan_matchmaking.sre.artifacts` 仍可解析（Python 的 package
  优先于 module，拆分后自动走 `__init__.py`）。
- **PR-fix-07** 改了 5 个调用点，合入前用 `grep -rn "_ctx_from_dict"`
  最终巡视一次。
- **PR-fix-08** 若目标部署的 SQLite < 3.35，用 T-806 的备用方案
  （helper）而非 `IF NOT EXISTS` 语法。
- **PR-fix-09 / PR-fix-10** 仅文档 + 命名，风险可忽略。

回退策略：每个 PR 独立 revert 即可，无数据迁移。
