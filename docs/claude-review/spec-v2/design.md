# Design v2 · C+A2 本轮

本文档详述 6 个 finding 的**how**。`what/why` 在 `requirements.md` 与
`findings.md`。

---

## F-005 · Rating scaling 合同

### 新增常量（`sre/artifacts/retention.py`）

```python
# Elo-style rating scaling for EOMM feature construction.
#
# Any change to the following constants invalidates previously saved
# retention artifacts. ``_rating_scaling_version()`` must bump when these
# change; runtime hydration will refuse to load mismatched artifacts.
_RATING_MU_BASE = 25.0               # pivot of Elo scale
_RATING_MU_SLOPE = 18.0               # service.mu → Player.mu gain
_RATING_MU_WIN_GAIN = 1.5             # bonus per consecutive win
_RATING_MU_LOSS_GAIN = -1.0           # penalty per consecutive loss
_RATING_SIGMA_FLOOR = 1.0             # minimum sigma after scaling
_RATING_SIGMA_BASE = 5.0
_RATING_SIGMA_SIGMA_GAIN = 10.0       # service.sigma → Player.sigma gain
_RATING_SIGMA_LOSS_STREAK_GAIN = 0.5
_RATING_CANARY_PENALTY = -14.0        # canary fraction penalty on mu
_RATING_CANARY_SIGMA_GAIN = 20.0      # canary fraction uncertainty gain
_RATING_CANDIDATE_SIGMA_BASE = 4.0
_RATING_CANDIDATE_SUCCESS_SIGMA_GAIN = 0.5
```

### `_rating_scaling_version()` 纯函数

```python
def _rating_scaling_version() -> str:
    """Stable hash of rating scaling constants. Bumps when any constant
    changes, enabling artifacts to refuse mismatched runtime code."""
    payload = {
        "mu_base": _RATING_MU_BASE,
        "mu_slope": _RATING_MU_SLOPE,
        "mu_win_gain": _RATING_MU_WIN_GAIN,
        "mu_loss_gain": _RATING_MU_LOSS_GAIN,
        "sigma_floor": _RATING_SIGMA_FLOOR,
        "sigma_base": _RATING_SIGMA_BASE,
        "sigma_sigma_gain": _RATING_SIGMA_SIGMA_GAIN,
        "sigma_loss_streak_gain": _RATING_SIGMA_LOSS_STREAK_GAIN,
        "canary_penalty": _RATING_CANARY_PENALTY,
        "canary_sigma_gain": _RATING_CANARY_SIGMA_GAIN,
        "candidate_sigma_base": _RATING_CANDIDATE_SIGMA_BASE,
        "candidate_success_sigma_gain": _RATING_CANDIDATE_SUCCESS_SIGMA_GAIN,
    }
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:12]
```

### Artifact metadata 扩展

`training/retention.py` 的 artifact 保存逻辑：

```python
metadata = ArtifactMetadata(
    ...,
    extra={
        ...,
        "rating_scaling_version": _rating_scaling_version(),
    },
)
```

### Runtime hydration（`SelfIterationPipeline._hydrate_runtime_artifacts`）

```python
if retention is not None:
    expected = _rating_scaling_version()
    actual = retention.metadata.extra.get("rating_scaling_version")
    if actual is not None and actual != expected:
        self.logger.warning(
            "artifacts.retention.scaling_mismatch",
            expected=expected,
            actual=actual,
            artifact_version=retention.metadata.version,
        )
        self.artifacts = self.artifacts._with_scaling_status("mismatch")
        return  # bootstrap path, do not hydrate retention weights
    ...
```

`RuntimeArtifactBundle.as_trace()` 输出新增 `"rating_scaling_status":
"match" | "mismatch" | "unknown"`（unknown 对应老 artifact 无此元数据）。

---

## F-006 · artifacts 包结构

### 目标结构

```
gan_matchmaking/sre/artifacts/
├── __init__.py              # 只做 re-export，保持外部 import 路径不变
├── metadata.py              # ArtifactMetadata、_stable_version、_build_id、_json_safe
├── retention.py             # RetentionArtifact、_service_player、_candidate_player、
│                            # build_match_config、build_history_vector、
│                            # EOMM_FEATURE_NAMES、_RATING_* 常量、_rating_scaling_version
├── cox.py                   # CoxArtifact、cox 保存与加载
└── bundle.py                # RuntimeArtifactBundle、load_runtime_artifacts
```

### `__init__.py` 的 re-export

```python
from .metadata import ArtifactMetadata
from .retention import (
    EOMM_FEATURE_NAMES,
    RetentionArtifact,
    build_history_vector,
    build_match_config,
)
from .cox import CoxArtifact
from .bundle import RuntimeArtifactBundle, load_runtime_artifacts

__all__ = [
    "ArtifactMetadata",
    "RetentionArtifact",
    "CoxArtifact",
    "RuntimeArtifactBundle",
    "load_runtime_artifacts",
    "build_history_vector",
    "build_match_config",
    "EOMM_FEATURE_NAMES",
]
```

### 迁移步骤（纯机械）

1. 创建 `sre/artifacts/` 目录 + 四个子文件
2. 移动原文件内容按职责分发
3. 删除旧的 `sre/artifacts.py` 单文件
4. 运行 `pytest tests/test_sre_artifacts.py tests/test_replay_corpus.py -v`
5. 全部绿即完成

**禁止**在此 PR 修改行为，常量提升 / 版本合同留给 F-005 PR。

---

## F-007 · ReleaseContext.from_dict 公共 API

### 新增方法（`sre/domain.py`）

```python
@dataclass
class ReleaseContext:
    ...

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ReleaseContext":
        """Reconstruct a ReleaseContext from a JSON-friendly mapping.

        Expected keys:
        - ``service``      (required, see ``Service.from_dict``)
        - ``candidates``   (required, list of ReleaseCandidate-shaped dicts)
        - ``dependencies`` (optional, list of service-id strings)
        - ``error_budget_remaining`` (optional, default 1.0)
        - ``freeze_window``          (optional, default False)
        - ``telemetry``              (optional, dict[str, float])
        - ``correlation_id``         (optional)

        Raises :class:`DataError` on malformed input.
        """
        # Implementation identical to current cli._ctx_from_dict.
        ...
```

### `cli._ctx_from_dict` 变薄

```python
def _ctx_from_dict(payload: Mapping[str, Any]) -> ReleaseContext:
    """Deprecated: use ReleaseContext.from_dict instead."""
    return ReleaseContext.from_dict(payload)
```

保留为 alias 不删除，避免现有测试无感知破坏；在 docstring 与 release notes
标记 deprecated。

### 调用点迁移

- `gan_matchmaking/service/app.py`:
  ```python
  # before
  from ..cli import _ctx_from_dict
  ctx = _ctx_from_dict(body)
  # after
  from ..sre import ReleaseContext
  ctx = ReleaseContext.from_dict(body)
  ```
- `tests/test_replay_corpus.py` / `tests/test_replay_export.py`:
  同样替换
- `tests/test_cli.py` 保留（测试 cli helper 本身）

### 导出

`gan_matchmaking/sre/__init__.py` 新增：

```python
from .domain import (
    ...,
    ReleaseContext,  # already exported
)
```

`ReleaseContext` 本身已导出；仅需确认 `ReleaseContext.from_dict`
classmethod 可用即可。

---

## F-008 · SQLite migration v5 正常化

### 目标代码结构

```python
_MIGRATIONS: list[tuple[int, tuple[str, ...]]] = [
    (1, ("CREATE TABLE IF NOT EXISTS services (...) ",)),
    ...
    (5, (
        "ALTER TABLE decisions ADD COLUMN IF NOT EXISTS artifact_version TEXT",
    )),
]

def _migrate(self) -> None:
    cur_version = self._current_version()
    for v, statements in _MIGRATIONS:
        if v <= cur_version:
            continue
        for sql in statements:
            self._conn.executescript(sql)
        self._conn.execute(
            "INSERT INTO _schema_migrations(version, applied_at) VALUES (?, ?)",
            (v, time.time()),
        )
    self._conn.commit()
```

关键：`ADD COLUMN IF NOT EXISTS` 在 SQLite 3.35+ 可用。本仓库约束
`sqlite3 >= 3.35`。如本仓库需支持老版本，改为应用前用
`PRAGMA table_info(...)` 查重并跳过 DDL，但一律走统一入口而非 v5 特判。

### 回归测试

`tests/test_persistence_sqlite.py::test_migration_v5_idempotent_on_legacy_db`

1. 用 SQL 手工建出"已经有 artifact_version 列"的旧库
2. `SQLitePipelineStore(Path(...))` 启动，不应抛 `OperationalError`
3. `_schema_migrations` 表里应该有 v5 行

---

## F-009 · 文档去重

### `docs/codex-handoff.md` 保留段

- **当前状态**：分支、基线、最新进展（保留）
- **机制地图**：9 机制 × 文件映射表（保留）
- **下一位该做什么**：简述 + 链接 `implementation-roadmap.md`
- **风险边界**：ADR-0007 的 split-brain 边界 + 当前已闭环说明

### `docs/implementation-roadmap.md` 保留段

- **Phase 定义**：P1 ~ P6
- **PR 映射**：PR-fix-01 ~ PR-fix-10 的对齐表
- **未来方向**：Kubernetes Lease / Redis Lease / PostgreSQL adv lock

### 删除/合并段

- `codex-handoff.md` 的 "Replay Corpus" 详述段 → 精简为 "见
  `tests/fixtures/replay/README.md`"
- `implementation-roadmap.md` 的 "下一步建议" → 直接替换为指向
  `codex-handoff.md::下一位该做什么` 的链接

---

## F-010 · Fixture 命名统一

### 命名模式

`{scenario}_{expected_kind}.json`

### 8 个文件的对齐

| 当前 | 目标 | 动作 |
|---|---|---|
| `fallback_go.json` | `fallback_go.json` | 保持 |
| `artifact_canary.json` | `artifact_canary.json` | 保持 |
| `budget_rollback.json` | `budget_rollback.json` | 保持 |
| `critical_tier_canary_downgrade.json` | `critical_tier_downgrade_canary.json` | rename |
| `freeze_hold.json` | `freeze_hold.json` | 保持 |
| `risk_warn_canary.json` | `risk_warn_canary.json` | 保持 |
| `shadow_strategy_hold.json` | `shadow_strategy_hold.json` | 保持 |
| `unknown_strategy_escalate.json` | `unknown_strategy_escalate.json` | 保持 |

只需 rename 1 个文件（`critical_tier_canary_downgrade.json`），其余全部已符合。

### README 模板（`tests/fixtures/replay/README.md`）

```markdown
# Replay Fixtures

Each fixture is a JSON snapshot of a decision replay:
`{"context": {...}, "config": {...}, "expected": {...}}`.

## Naming convention

File name: `{scenario}_{expected_kind}.json`

- `{scenario}`: short snake_case description of the trigger
- `{expected_kind}`: final Decision.kind value (`go`, `canary`,
  `hold`, `rollback`, `escalate`)

## Catalog

| File | Scenario | Expected kind |
|---|---|---|
| fallback_go.json | 无 artifact 时走 bootstrap 路径 | go |
| artifact_canary.json | Fitted artifact 驱动 canary | canary |
| budget_rollback.json | error_budget 耗尽 → rollback | rollback |
| critical_tier_downgrade_canary.json | critical-tier full → canary 降级 | canary |
| freeze_hold.json | freeze_window 强制 hold | hold |
| risk_warn_canary.json | Cox survival WARN → canary | canary |
| shadow_strategy_hold.json | shadow strategy → hold | hold |
| unknown_strategy_escalate.json | 未识别 strategy → escalate | escalate |
```

---

## 本轮**不做的事**

- 不引入新机制 / 新 stage
- 不改 `Decision` 对外字段
- 不改 `/v1/*` HTTP API 路径与 payload shape
- 不改 `trace["stages"]["*"]` 字段集（只改 `trace["artifacts"]` 的可选字段）
- 不引入新第三方依赖
- 不添加新的 `pragma: no cover`
