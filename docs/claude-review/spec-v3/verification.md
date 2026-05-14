# Verification v3 · D+A2 本轮

本文列出 2026-07 spec-v3 的验证命令、快照断言和收尾检查。

---

## 1. 按 PR 验证

### PR-doc-03 · historical trackers superseded

```powershell
# R-801
Select-String -Path docs\claude-review\action-items.md,docs\claude-review\test-coverage-gaps.md `
  -Pattern "Superseded|2026-06-spec-completion|2026-06-codex-package-review|spec-v3"

# R-802
Select-String -Path docs\claude-review\README.md -Pattern "2026-07|spec-v3|历史 tracker"
Select-String -Path docs\codex-review\README.md -Pattern "spec-v3"
```

期望：两个历史 tracker 都有 banner；README 明确当前可执行入口为 spec-v3。

### PR-ci-01 · latency budget gate

```powershell
# R-811
python -m pytest tests/test_latency_benchmark.py -v

# R-812
Select-String -Path .github\workflows\ci.yml -Pattern "bench.latency --quick --p99-ms 50"

# smoke + gate
python -m bench.latency --quick
python -m bench.latency --quick --p99-ms 50
```

期望：
- smoke 模式仍只报告结果并返回 0。
- 显式 budget 模式在当前机器上返回 0。
- 单元测试覆盖超预算返回 1。

### PR-test-01 · replay fixture naming hardening

```powershell
# R-821 / R-822
python -m pytest tests/test_replay_corpus.py -v -k fixture
```

期望：每个 fixture 文件名 suffix 等于 JSON `expected.kind`；若有 `name` 字段，必须等于文件 stem。

### PR-test-02 · artifacts public import snapshot

```powershell
# R-831
python -m pytest tests/test_artifacts_public_api.py -v

# 手工 import smoke
python -c "from gan_matchmaking.sre.artifacts import RuntimeArtifactBundle, load_runtime_artifacts, ArtifactMetadata; print('ok')"
```

期望：`__all__` 与 frozen expected symbol set 完全一致。

### PR-test-03 · HTTP lease readiness integration

```powershell
# R-841 / R-842
python -m pytest tests/test_http_service.py -v -k "readyz or healthz"
```

期望：lease unhealthy 后真实 HTTP `/readyz` 返回 503，`/healthz` 仍返回 200。

---

## 2. 全局验收命令

合并所有 PR 后运行：

```powershell
python -m pytest -q
python -m bench.latency --quick --p99-ms 50
```

期望：
- pytest 全绿。
- latency gate 返回 0。

---

## 3. 契约快照

### CI latency command

`.github/workflows/ci.yml` 的 benchmark step 必须使用：

```bash
python -m bench.latency --quick --p99-ms 50
```

50ms 是共享 runner 的宽松 gate；本地和 release gate 可用更严格阈值。

### Replay naming contract

每个 `tests/fixtures/replay/*.json` 必须满足：

```text
path.stem.endswith("_" + raw["expected"]["kind"])
raw.get("name", path.stem) == path.stem
```

### Artifacts public symbols

`gan_matchmaking.sre.artifacts.__all__` 必须等于：

```text
ArtifactMetadata
build_metadata
EOMM_FEATURE_NAMES
RetentionArtifact
RetentionScalingCompatibility
_rating_scaling_version
build_history_vector
build_match_config
load_retention_artifact
retention_scaling_compatibility
save_retention_artifact
validate_retention_artifact
CoxArtifact
load_cox_artifact
save_cox_artifact
validate_cox_artifact
RuntimeArtifactBundle
load_runtime_artifacts
```

---

## 4. 收尾归档

PR 全部合入后：

1. 新建 `docs/claude-review/2026-07-spec-completion.md`。
2. 在 `docs/claude-review/README.md` 中把 2026-07 D+A2 标为已完成。
3. 如果后续继续扩展，开 `docs/claude-review/spec-v4/`，不要回改 spec-v3 的已完成内容。
4. 若 latency gate 后续收紧阈值，记录在 completion 文档中，而不是覆盖本 spec 的 50ms CI baseline。