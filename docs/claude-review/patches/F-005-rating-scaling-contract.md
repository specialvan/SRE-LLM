# Patch · F-005 Rating Scaling Contract

## 当前代码锚点

### `gan_matchmaking/sre/artifacts.py`（PR-fix-06 后改为 `artifacts/retention.py`）

**当前 `_service_player` / `_candidate_player`（L210-225）**:

```python
def _service_player(service: Service) -> Player:
    mu = 25.0 + 18.0 * (service.mu - 0.5) + 1.5 * float(service.win_streak) - 1.0 * float(service.loss_streak)
    sigma = max(1.0, 5.0 + 10.0 * float(service.sigma) + 0.5 * float(service.loss_streak))
    return Player(
        mu=mu,
        sigma=sigma,
        ...
    )


def _candidate_player(candidate: ReleaseCandidate) -> Player:
    mu = 25.0 + 18.0 * (candidate.expected_success - 0.5) - 14.0 * candidate.canary_fraction
    sigma = max(1.0, 4.0 + 20.0 * candidate.canary_fraction + 0.5 * (1.0 - candidate.expected_success))
    return Player(
        mu=mu,
        sigma=sigma,
        ...
    )
```

11 个魔法数字散布，任何改动都会使历史 artifact 与 runtime 对不上，
但目前没有 contract test 能拦。

## 目标代码

### 常量区（新增，放在两个函数定义之前）

```python
import hashlib
import json

# ---------------------------------------------------------------------------
# Rating scaling constants (EOMM feature construction, see ADR-0008)
#
# IMPORTANT: any change here invalidates previously saved retention
# artifacts. ``_rating_scaling_version`` below will automatically bump;
# ``SelfIterationPipeline._hydrate_runtime_artifacts`` will refuse to
# load mismatched artifacts and fall back to bootstrap.
# ---------------------------------------------------------------------------
_RATING_MU_BASE = 25.0                      # Elo scale pivot
_RATING_MU_SLOPE = 18.0                     # service.mu → Player.mu gain
_RATING_MU_WIN_GAIN = 1.5                   # bonus per consecutive win
_RATING_MU_LOSS_GAIN = -1.0                 # penalty per consecutive loss

_RATING_SIGMA_FLOOR = 1.0                   # minimum sigma after scaling
_RATING_SIGMA_SVC_BASE = 5.0
_RATING_SIGMA_SVC_SIGMA_GAIN = 10.0         # service.sigma → Player.sigma gain
_RATING_SIGMA_SVC_LOSS_STREAK_GAIN = 0.5

_RATING_CANDIDATE_CANARY_PENALTY = -14.0    # canary fraction penalty on mu
_RATING_SIGMA_CAND_BASE = 4.0
_RATING_SIGMA_CAND_CANARY_GAIN = 20.0       # canary fraction uncertainty gain
_RATING_SIGMA_CAND_SUCCESS_GAIN = 0.5       # (1 - expected_success) → sigma gain


def _rating_scaling_version() -> str:
    """Stable 12-char hash of rating scaling constants.

    Changes whenever any ``_RATING_*`` constant changes, enabling
    saved artifacts to refuse mismatched runtime code via
    ``ArtifactMetadata.extra['rating_scaling_version']``.
    """
    payload = {
        "mu_base": _RATING_MU_BASE,
        "mu_slope": _RATING_MU_SLOPE,
        "mu_win_gain": _RATING_MU_WIN_GAIN,
        "mu_loss_gain": _RATING_MU_LOSS_GAIN,
        "sigma_floor": _RATING_SIGMA_FLOOR,
        "sigma_svc_base": _RATING_SIGMA_SVC_BASE,
        "sigma_svc_sigma_gain": _RATING_SIGMA_SVC_SIGMA_GAIN,
        "sigma_svc_loss_streak_gain": _RATING_SIGMA_SVC_LOSS_STREAK_GAIN,
        "candidate_canary_penalty": _RATING_CANDIDATE_CANARY_PENALTY,
        "sigma_cand_base": _RATING_SIGMA_CAND_BASE,
        "sigma_cand_canary_gain": _RATING_SIGMA_CAND_CANARY_GAIN,
        "sigma_cand_success_gain": _RATING_SIGMA_CAND_SUCCESS_GAIN,
    }
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:12]
```

### 替换后的 player 函数

```python
def _service_player(service: Service) -> Player:
    mu = (
        _RATING_MU_BASE
        + _RATING_MU_SLOPE * (service.mu - 0.5)
        + _RATING_MU_WIN_GAIN * float(service.win_streak)
        + _RATING_MU_LOSS_GAIN * float(service.loss_streak)
    )
    sigma = max(
        _RATING_SIGMA_FLOOR,
        _RATING_SIGMA_SVC_BASE
        + _RATING_SIGMA_SVC_SIGMA_GAIN * float(service.sigma)
        + _RATING_SIGMA_SVC_LOSS_STREAK_GAIN * float(service.loss_streak),
    )
    return Player(mu=mu, sigma=sigma, ...)


def _candidate_player(candidate: ReleaseCandidate) -> Player:
    mu = (
        _RATING_MU_BASE
        + _RATING_MU_SLOPE * (candidate.expected_success - 0.5)
        + _RATING_CANDIDATE_CANARY_PENALTY * candidate.canary_fraction
    )
    sigma = max(
        _RATING_SIGMA_FLOOR,
        _RATING_SIGMA_CAND_BASE
        + _RATING_SIGMA_CAND_CANARY_GAIN * candidate.canary_fraction
        + _RATING_SIGMA_CAND_SUCCESS_GAIN * (1.0 - candidate.expected_success),
    )
    return Player(mu=mu, sigma=sigma, ...)
```

**数值不变**（验证：`pytest tests/test_sre_artifacts.py` 零修改全绿）。

### `training/retention.py` — artifact 保存时写入 version

```python
from gan_matchmaking.sre.artifacts.retention import _rating_scaling_version

# ...构造 ArtifactMetadata 的位置
metadata = ArtifactMetadata(
    ...existing fields...,
    extra={
        ...existing extras...,
        "rating_scaling_version": _rating_scaling_version(),
    },
)
```

### `sre/self_iteration.py` — hydration 不匹配时降级

```python
def _hydrate_runtime_artifacts(self) -> None:
    # ...existing load...
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
            return
        self.artifacts = self.artifacts._with_scaling_status("match")
    # ...
```

### `sre/artifacts/bundle.py` — Bundle 增加 status 字段

```python
@dataclass(frozen=True)
class RuntimeArtifactBundle:
    ...
    rating_scaling_status: str = "unknown"

    def _with_scaling_status(self, status: str) -> "RuntimeArtifactBundle":
        return replace(self, rating_scaling_status=status)

    def as_trace(self) -> dict[str, Any]:
        return {
            ...existing...,
            "rating_scaling_status": self.rating_scaling_status,
        }
```

## 预计 LOC

| 路径 | +/- |
|---|---|
| `sre/artifacts/retention.py` | +50 / -4 |
| `sre/artifacts/bundle.py` | +8 / -0 |
| `sre/self_iteration.py` | +12 / -2 |
| `training/retention.py` | +2 / -0 |
| `tests/test_sre_artifacts.py` | +120 / -0 |
| `docs/adr/0008-artifact-rating-scaling-compatibility.md` | +60 / -0（新建）|
| **合计** | **+252 / -6** |

## 测试骨架

```python
# tests/test_sre_artifacts.py (新增)

def test_rating_scaling_version_is_stable():
    v1 = _rating_scaling_version()
    v2 = _rating_scaling_version()
    assert v1 == v2
    assert len(v1) == 12
    assert v1 == v1.lower()
    assert all(c in "0123456789abcdef" for c in v1)


def test_rating_scaling_version_changes_with_constant(monkeypatch):
    from gan_matchmaking.sre.artifacts import retention
    v_before = retention._rating_scaling_version()
    monkeypatch.setattr(retention, "_RATING_MU_SLOPE",
                         retention._RATING_MU_SLOPE + 1.0)
    v_after = retention._rating_scaling_version()
    assert v_before != v_after


def test_artifact_version_mismatch_downgrades_to_bootstrap(tmp_path):
    # 1. 保存一个带 stale scaling_version 的 retention artifact
    #    （用 np.savez / json.dump 手工构造，绕过 training 流程）
    # 2. 启动 SelfIterationPipeline(artifacts_dir=tmp_path)
    # 3. assert pipeline.artifacts.rating_scaling_status == "mismatch"
    # 4. assert pipeline.artifacts.retention_weights is None
    # 5. 捕获日志中存在 artifacts.retention.scaling_mismatch
    ...


def test_rating_scaling_contract_snapshot():
    svc = Service(id="s", mu=0.95, sigma=0.03,
                  win_streak=2, loss_streak=0, tier="standard")
    cand = ReleaseCandidate(
        id="c", service_id="s", strategy="canary",
        canary_fraction=0.1, rollback_budget_seconds=180,
        expected_success=0.99,
    )
    p_svc = _service_player(svc)
    # 25 + 18*0.45 + 1.5*2 - 1.0*0 = 25 + 8.1 + 3 = 36.1
    assert p_svc.mu == pytest.approx(36.1, rel=1e-9)
    # max(1, 5 + 10*0.03 + 0.5*0) = 5.3
    assert p_svc.sigma == pytest.approx(5.3, rel=1e-9)

    p_cand = _candidate_player(cand)
    # 25 + 18*0.49 - 14*0.1 = 25 + 8.82 - 1.4 = 32.42
    assert p_cand.mu == pytest.approx(32.42, rel=1e-9)
    # max(1, 4 + 20*0.1 + 0.5*0.01) = 6.005
    assert p_cand.sigma == pytest.approx(6.005, rel=1e-9)
```

## ADR-0008 骨架

```markdown
# ADR-0008 · Artifact rating scaling compatibility

## Context

`_service_player` / `_candidate_player` 使用一组硬编码常数把
SRE 业务状态（mu / sigma / win_streak / loss_streak / canary_fraction /
expected_success）映射到 Elo-style Player rating，然后进入 EOMM feature
构造。一旦这些常数被修改，所有历史 fitted retention artifact 的
feature 空间就和 runtime 对不上，但决策会静默漂移。

## Decision

1. 所有 rating 相关魔法数字抽成 `_RATING_*` 模块级常量
2. `_rating_scaling_version()` 是纯函数，基于常数集合的 SHA-256 前 12 位
3. artifact 保存时写入 `metadata.extra["rating_scaling_version"]`
4. runtime hydration 若不匹配：
   - 发 WARNING 日志 `artifacts.retention.scaling_mismatch`
   - 设 `RuntimeArtifactBundle.rating_scaling_status = "mismatch"`
   - 不加载 retention weights，走 bootstrap 决策路径
5. 修改 `_RATING_*` 常数的人工流程：
   - Commit 消息标题必须含 `[rating-scaling-break]`
   - PR 描述必须包含重训 artifact 的计划
   - 合入后，下一个 deploy 前必须在 staging 验证 mismatch 路径

## Consequences

- 所有生产中保存的 artifact 在下次 deploy 后仍能安全共存：
  match 的 artifact 正常加载，mismatch 的自动降级为 bootstrap。
- 需要在 runbook 中加入 "rating scaling mismatch" 场景的处置流程
  （观察日志 → 触发 retrain → 重新 deploy）。
```
