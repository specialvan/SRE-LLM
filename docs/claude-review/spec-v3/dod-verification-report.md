# SPEC-V3 DoD 逐条验收报告

> 生成时间: 2026-05-14
> 分支: gan-session-fix-07
> 测试: 227 passed, 10 skipped

---

## DoD 1 · Runtime hydration 与 replay validation 使用同一个 helper

**要求**: Runtime hydration 与 replay validation 使用同一个 `rating-scaling compatibility helper`

**实现**:
- `gan_matchmaking/sre/artifacts/retention.py:98` 定义 `retention_scaling_compatibility()`
- `gan_matchmaking/sre/self_iteration.py:313` 调用 helper
- `gan_matchmaking/sre/replay.py:310` 调用 helper

**验证命令**:
```bash
grep -n "retention_scaling_compatibility" gan_matchmaking/sre/self_iteration.py gan_matchmaking/sre/replay.py
# self_iteration.py:313:     compatibility = retention_scaling_compatibility(retention)
# replay.py:310:     scaling = retention_scaling_compatibility(bundle.retention)
```

**状态**: ✅ 通过

---

## DoD 2 · Replay validation 拒绝 runtime 会 downgrade 的 mismatch

**要求**: Replay validation 在 rating scaling mismatch 时 raise DataError

**实现**:
- `gan_matchmaking/sre/replay.py:311-325` 处理 mismatch/unknown
- 抛出 `DataError("retention artifact rating-scaling version mismatch")`
- 错误 details 包含 expected_version, actual_version, artifact_version

**验证命令**:
```bash
python -m pytest tests/test_rating_scaling.py::test_replay_validation_rejects_rating_scaling_mismatch -v
```

**测试**:
- `tests/test_rating_scaling.py::test_replay_validation_rejects_rating_scaling_mismatch`
- `tests/test_rating_scaling.py::test_replay_validation_requires_explicit_legacy_unknown`

**状态**: ✅ 通过

---

## DoD 3 · Modern fitted fixture 至少一个断言 `rating_scaling_status == "match"`

**要求**: Modern fitted replay fixture 断言 `trace.artifacts.rating_scaling_status == "match"`

**实现**:
- `tests/fixtures/replay/artifact_canary.json` 包含 `expected.trace_values.artifacts.rating_scaling_status: match`
- `tests/test_replay_corpus.py:325-334` 测试 `test_modern_artifact_replay_reports_scaling_match`

**验证命令**:
```bash
python -m pytest tests/test_replay_corpus.py::test_modern_artifact_replay_reports_scaling_match -v
cat tests/fixtures/replay/artifact_canary.json | grep rating_scaling_status
```

**状态**: ✅ 通过

---

## DoD 4 · Legacy `unknown` retention scaling 行为显式命名/显式允许

**要求**: Legacy unknown 行为必须显式命名或显式允许

**实现**:
- `gan_matchmaking/sre/replay.py:312` 检查 `allow_legacy_unknown` 参数
- `tests/test_replay_corpus.py:352-362` 测试 `test_legacy_artifact_fixture_is_explicitly_named`
- Legacy fixtures 必须以 `legacy_` 开头

**验证命令**:
```bash
python -m pytest tests/test_replay_corpus.py::test_legacy_artifact_fixture_is_explicitly_named -v
python -m pytest tests/test_rating_scaling.py::test_replay_validation_requires_explicit_legacy_unknown -v
```

**状态**: ✅ 通过

---

## DoD 5 · 至少新增两个 artifact failure / guardrail short-circuit replay narratives

**要求**: 至少新增两个 artifact failure / guardrail short-circuit replay narratives

**实现 fixtures**:
1. `tests/fixtures/replay/artifact_validation_failure_go.json` - 无效 manifest
2. `tests/fixtures/replay/artifact_metadata_missing_go.json` - 缺失 metadata
3. `tests/fixtures/replay/artifact_scaling_mismatch_go.json` - scaling mismatch
4. `tests/fixtures/replay/breaker_open_escalate.json` - breaker short-circuit

**验证命令**:
```bash
ls tests/fixtures/replay/*.json | wc -l  # 18 个 fixtures
python -m pytest tests/test_replay_corpus.py -v -k "artifact or breaker"
```

**状态**: ✅ 通过 (4+ 个 artifact failure/narrative fixtures)

---

## DoD 6 · Lease readiness boundary 文档明确 `/healthz` 与 `/readyz` 分工

**要求**: 文档明确 `/healthz` 是 process health，`/readyz` 包含 lease health

**实现**:
- `docs/architecture/06-concurrency-and-leases.md:109-110` 明确分工
- `/healthz` 只表示进程健康，不含 lease 状态
- `/readyz` 包含 lease 健康，续租失败返回 503

**验证命令**:
```bash
grep -A2 "healthz.*readyz" docs/architecture/06-concurrency-and-leases.md
```

**状态**: ✅ 通过

---

## DoD 7 · 历史 tracker 顶部都有 superseded banner

**要求**: 历史 tracker 顶部有 banner，指向 completion 和 spec-v3

**实现**:
- `docs/claude-review/action-items.md` 顶部 banner
- `docs/claude-review/test-coverage-gaps.md` 顶部 banner
- 两个文件都指向 `2026-06-spec-completion.md`, `2026-06-codex-package-review.md`, `spec-v3`

**验证命令**:
```bash
grep -i "superseded" docs/claude-review/action-items.md docs/claude-review/test-coverage-gaps.md
```

**状态**: ✅ 通过

---

## DoD 8 · CI latency benchmark 在 p99 超过预算时返回非零

**要求**: `bench.latency --quick --p99-ms <budget>` 在超预算时返回 1

**实现**:
- `bench/latency.py:100-105` 实现 budget enforce
- `.github/workflows/ci.yml:45` 配置 `--p99-ms 50`

**验证命令**:
```bash
grep "bench.latency --quick --p99-ms" .github/workflows/ci.yml
python -m bench.latency --quick --p99-ms 1  # 应该返回 1 (若 p99 > 1ms)
python -m pytest tests/test_latency_benchmark.py -v
```

**状态**: ✅ 通过

---

## DoD 9 · Replay fixture naming 测试断言 suffix 等于 JSON `expected.kind`

**要求**: fixture 文件名 suffix 等于 JSON `expected.kind`

**实现**:
- `tests/test_replay_corpus.py:196-211` 测试 `test_fixture_naming_matches_convention`
- 断言 `path.stem.endswith(f"_{expected_kind}")`
- 断言 `raw["name"] == path.stem`

**验证命令**:
```bash
python -m pytest tests/test_replay_corpus.py::test_fixture_naming_matches_convention -v
```

**状态**: ✅ 通过

---

## DoD 10 · Artifacts public import surface 由显式 expected symbol set 保护

**要求**: `gan_matchmaking.sre.artifacts` 的 `__all__` 等于 frozen expected symbol set

**实现**:
- `gan_matchmaking/sre/artifacts/__init__.py:36-55` 定义 `__all__` (17 symbols)
- `tests/test_artifacts_public_api.py` 测试 public surface stability

**验证命令**:
```bash
python -m pytest tests/test_artifacts_public_api.py -v
python -c "from gan_matchmaking.sre.artifacts import *; print('ok')"
```

**状态**: ✅ 通过

---

## DoD 11 · HTTP-level `/readyz` lease-unhealthy 路径有测试覆盖，`/healthz` 仍保持 200

**要求**: HTTP `/readyz` 返回 503 当 lease unhealthy，`/healthz` 仍 200

**实现**:
- `tests/test_http_service.py:112-126` 测试 `test_readyz_http_reflects_lease_failure`

**验证命令**:
```bash
python -m pytest tests/test_http_service.py::test_readyz_http_reflects_lease_failure tests/test_http_service.py::test_healthz -v
```

**状态**: ✅ 通过

---

## DoD 12 · `python -m pytest -q` 全绿

**要求**: 全量测试通过

**验证命令**:
```bash
python -m pytest -q
```

**结果**: `227 passed, 10 skipped in 9.95s`

**状态**: ✅ 通过

---

## DoD 13 · `python -m bench.latency --quick --p99-ms 50` 返回 0

**要求**: Latency gate 返回 0

**验证命令**:
```bash
python -m bench.latency --quick --p99-ms 50; echo "exit code: $?"
```

**结果**: `p99_ms: 2.34ms < 50ms`，返回 0

**状态**: ✅ 通过

---

## 汇总

| DoD | 描述 | 状态 |
|---|---|---|
| 1 | Shared helper | ✅ |
| 2 | Replay validation 拒绝 mismatch | ✅ |
| 3 | Modern fixture 断言 match | ✅ |
| 4 | Legacy unknown 显式命名 | ✅ |
| 5 | 至少 2 个 artifact failure narratives | ✅ (4+) |
| 6 | Lease readiness boundary docs | ✅ |
| 7 | History tracker superseded banner | ✅ |
| 8 | CI latency gate | ✅ |
| 9 | Fixture naming contract | ✅ |
| 10 | Public API snapshot | ✅ |
| 11 | HTTP readiness integration | ✅ |
| 12 | pytest 全绿 | ✅ |
| 13 | Latency gate returns 0 | ✅ |

**总计**: 13/13 通过