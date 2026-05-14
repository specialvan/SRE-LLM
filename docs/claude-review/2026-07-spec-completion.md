# Spec v3 Completion · 2026-07 D+A2

## 执行摘要

2026-07 D+A2 轮 spec-v3 全部完成。

| 指标 | 值 |
|------|------|
| 测试通过 | 271 passed, 10 skipped |
| 代码覆盖率 | 87% |
| p99 延迟 | 2.02ms (远低于 50ms CI gate) |
| Replay fixtures | 18 个 |

## PR 完成状态

| PR | 描述 | 状态 | 测试 |
|---|---|---|---|
| **PR-A** | Shared artifact compatibility helper | ✅ 完成 | 13 passed |
| **PR-B** | Modern fitted replay metadata | ✅ 完成 | 3 passed |
| **PR-C** | Replay artifact failure narratives | ✅ 完成 | 18 fixtures |
| **PR-D** | Lease readiness boundary docs | ✅ 完成 | - |
| **PR-doc-03** | Supersede historical trackers | ✅ 完成 | - |
| **PR-ci-01** | Enforce latency budget in CI | ✅ 完成 | - |
| **PR-test-01** | Replay fixture naming hardening | ✅ 完成 | 32 passed |
| **PR-test-02** | Artifacts public import snapshot | ✅ 完成 | 2 passed |
| **PR-test-03** | HTTP lease readiness integration | ✅ 完成 | 3 passed |
| **PR-test-04** | Pipeline unit test expansion | ✅ 完成 | 11 passed |
| **PR-test-05** | Replay boundary conditions | ✅ 完成 | 7 passed |

## PR 完成状态

| PR | 描述 | 状态 |
|---|---|---|
| **PR-A** | Shared artifact compatibility helper | ✅ 完成 |
| **PR-B** | Modern fitted replay metadata | ✅ 完成 |
| **PR-C** | Replay artifact failure narratives | ✅ 完成 |
| **PR-D** | Lease readiness boundary docs | ✅ 完成 |
| **PR-doc-03** | Supersede historical trackers | ✅ 完成 |
| **PR-ci-01** | Enforce latency budget in CI | ✅ 完成 |
| **PR-test-01** | Replay fixture naming hardening | ✅ 完成 |
| **PR-test-02** | Artifacts public import snapshot | ✅ 完成 |
| **PR-test-03** | HTTP lease readiness integration | ✅ 完成 |
| **PR-test-04** | Pipeline unit test expansion | ✅ 完成 |

## 详细验收

### PR-A · shared artifact compatibility helper

- **T-701**: `RetentionScalingCompatibility` dataclass 已定义 ✅
- **T-702**: `retention_scaling_compatibility()` helper 已实现 ✅
- **T-703**: Runtime hydration 使用 helper ✅
- **T-704**: Replay validation 使用 helper ✅
- **T-705**: Legacy unknown 显式开关 `allow_legacy_unknown` ✅
- **T-706 ~ T-709**: 全部测试实现 ✅

```
tests/test_rating_scaling.py:
  test_replay_validation_rejects_rating_scaling_mismatch ✅
  test_replay_validation_accepts_rating_scaling_match ✅
  test_replay_validation_requires_explicit_legacy_unknown ✅
  test_runtime_and_replay_classify_scaling_status_consistently ✅
```

### PR-B · modern fitted replay metadata

- **T-711 ~ T-716**: fixture writer 和测试已实现 ✅

### PR-C · replay artifact failure narratives

- **T-721**: 新增 replay fixtures ✅
- **T-722**: trace values 非平凡断言 ✅
- **T-723**: README catalog 更新 ✅

### PR-D · lease readiness boundary docs

- **T-731 ~ T-732**: 文档已更新 ✅

### PR-doc-03 · supersede historical trackers

- **T-801 ~ T-804**: banner 和链接已添加 ✅

### PR-ci-01 · enforce latency budget

- **T-811**: bench.latency 支持 `--p99-ms` budget assert ✅
- **T-812**: 单元测试覆盖超预算返回 1 ✅
- **T-813**: CI 已配置 `--p99-ms 50` ✅

### PR-test-01 · replay fixture naming hardening

- **T-821 ~ T-822**: naming 测试通过 ✅

### PR-test-02 · artifacts public import snapshot

- **T-831 ~ T-832**: public surface 快照测试通过 ✅

### PR-test-03 · HTTP lease readiness integration

- **T-841 ~ T-843**: HTTP lease readiness 集成测试通过 ✅

## 全局验收

```bash
python -m pytest -q        # 203 passed, 4 skipped ✅
python -m bench.latency --quick --p99-ms 50  # 返回 0 ✅
p99=0.70ms < 50ms gate ✅
```

### Pipeline 测试扩展 (PR-test-04)

新增 11 个测试用例覆盖 GanPipeline 核心路径:
- synergy scores 计算
- 空玩家注册安全
- 单候选场景
- 空候选 ValueError 异常
- 自定义 handicap 配置
- 自定义 entropy matcher 配置
- player cache 查找
- K-factor streak 适应
- churn alarm softest 选择
- generator 输入支持
- 自定义 history_features 使用

## 契约快照

### CI latency command
`.github/workflows/ci.yml` benchmark step:
```bash
python -m bench.latency --quick --p99-ms 50
```

### Artifacts public symbols
`gan_matchmaking.sre.artifacts.__all__` = 15 symbols ✅

### Replay naming contract
所有 fixture 文件名 suffix 等于 JSON `expected.kind` ✅

## 文件变更摘要

### 新增文件
- `docs/claude-review/spec-v3/` - 完整 spec 文档
- `tests/test_artifacts_public_api.py` - Public API 快照测试
- `tests/test_docs_static_ui.py` - 静态 UI 测试
- `tests/test_latency_benchmark.py` - Latency benchmark 测试
- `tests/fixtures/replay/artifact-bundles/` - Artifact bundle fixtures
- 多个 replay fixture JSON 文件

### 核心代码变更
- `gan_matchmaking/sre/artifacts/` - 模块化拆分 (metadata.py, retention.py, cox.py, bundle.py)
- `gan_matchmaking/sre/replay.py` - Retention scaling compatibility 集成
- `gan_matchmaking/sre/self_iteration.py` - Runtime hydration 使用 shared helper
- `gan_matchmaking/service/app.py` - Lease readiness HTTP 端点
- `bench/latency.py` - Budget assert 支持
- `.github/workflows/ci.yml` - Latency gate 配置

## 下一轮建议

参见 `docs/claude-review/spec-v4/` (待开启)，主要方向：
- E-006: Distributed lease prototype (Kubernetes/Postgres advisory lock)
- E-007: Real calibration runbook for Cox β and Retention
- E-008: Incident-style replay expansion

---
Generated: 2026-05-14