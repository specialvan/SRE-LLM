# Implementation Plan v3 · D+A2 本轮

本文是 2026-07 轮唯一的可执行任务清单。每条任务都有唯一 task id，并引用
[`requirements.md`](requirements.md) 中的 R-XXX。

PR 依赖顺序：`PR-A` → `PR-B` → `PR-C / PR-D` → `PR-doc-03 / PR-ci-01 / PR-test-01 / PR-test-02 / PR-test-03`。
其中 PR-C、PR-D 与后续 hardening PR 互不依赖，可并行。

---

## PR-A · shared artifact compatibility helper

> 满足 requirements: **R-701 / R-702 / R-703 / R-704**

### T-701 · 定义 compatibility status 类型

- 文件: `gan_matchmaking/sre/artifacts/retention.py` 或新增 `gan_matchmaking/sre/artifacts/compatibility.py`
- 动作: 定义返回对象（dataclass 或 NamedTuple），字段至少包含：
  - `status`: `match` / `mismatch` / `unknown` / `absent`
  - `expected_version`
  - `actual_version`
  - `artifact_version`
- Requirement: R-701

### T-702 · 抽出 shared helper

- 文件: 同 T-701
- 动作: 新增 `validate_retention_scaling(retention: RetentionArtifact | None) -> ArtifactCompatibility`
  或等价函数；内部只依赖 `_rating_scaling_version()` 与 retention metadata。
- Requirement: R-701

### T-703 · runtime hydration 改用 helper

- 文件: `gan_matchmaking/sre/self_iteration.py`
- 动作: 用 T-702 helper 替换当前 inline comparison；保持现有 runtime 行为：
  - `match` hydrate retention
  - `unknown` legacy hydrate 并标 trace status unknown
  - `mismatch` warning + 不 hydrate
- Requirement: R-702

### T-704 · replay validation 改用 helper

- 文件: `gan_matchmaking/sre/replay.py`
- 符号: `validate_artifact_bundle` 或实际 artifact bundle validation 入口
- 动作: 加 retention scaling compatibility 检查；`mismatch` raise `DataError`，错误消息包含 expected / actual / artifact version / artifact directory。
- Requirement: R-703

### T-705 · legacy unknown 显式开关

- 文件: `gan_matchmaking/sre/replay.py`
- 动作: 给 validation 入口增加 `allow_legacy_unknown: bool = False` 或等价 fixture metadata 判断；默认不让 unknown 悄悄通过现代 fitted path。
- Requirement: R-704

### T-706 · replay mismatch 测试

- 文件: `tests/test_rating_scaling.py` 或 `tests/test_replay_export.py`
- 签名: `test_replay_validation_rejects_rating_scaling_mismatch`
- 断言: 构造 `rating_scaling_version="deadbeef0000"` 的 retention artifact，调用 validation 后抛 `DataError`，错误含 expected / actual。
- Requirement: R-703

### T-707 · replay match 测试

- 文件: 同 T-706
- 签名: `test_replay_validation_accepts_rating_scaling_match`
- 断言: 构造 metadata 使用 `_rating_scaling_version()` 的 artifact，validation 通过。
- Requirement: R-701 / R-703

### T-708 · runtime/replay helper 一致性测试

- 文件: 同 T-706
- 签名: `test_runtime_and_replay_use_same_scaling_helper`
- 断言: 同一个 artifact 在 runtime helper 与 replay validation path 中产生相同 compatibility status；优先行为断言，不做脆弱源码检查。
- Requirement: R-701

### T-709 · legacy unknown 显式测试

- 文件: 同 T-706
- 签名: `test_replay_validation_requires_explicit_legacy_unknown`
- 断言: 缺少 `rating_scaling_version` 的 retention artifact 默认被拒绝；传显式 flag 或 legacy metadata 后通过。
- Requirement: R-704

---

## PR-B · modern fitted replay metadata

> 满足 requirements: **R-711 / R-712 / R-713**

### T-711 · fixture writer 写 rating_scaling_version

- 文件: `tests/test_replay_corpus.py` 中 inline fitted fixture writer 或对应 helper
- 动作: 生成 retention metadata 时写入 `_rating_scaling_version()`。
- Requirement: R-711

### T-712 · golden expected trace 断言 match

- 文件: `tests/fixtures/replay/artifact_canary.json` 或 modern fitted fixture
- 动作: 在 expected trace values 中加入 `trace.artifacts.rating_scaling_status == "match"` 的断言形态。
- Requirement: R-712

### T-713 · legacy unknown 显式命名 / catalog

- 文件: `tests/fixtures/replay/README.md` 和相关 fixture
- 动作: 若保留 unknown path fixture，在文件名或 catalog 描述里明确 `legacy_unknown`；否则删除 unknown path 对 modern fixture 的依赖。
- Requirement: R-713

### T-714 · modern metadata 测试

- 文件: `tests/test_replay_corpus.py`
- 签名: `test_modern_artifact_fixture_has_scaling_version`
- Requirement: R-711

### T-715 · modern replay trace match 测试

- 文件: `tests/test_replay_corpus.py`
- 签名: `test_modern_artifact_replay_reports_scaling_match`
- Requirement: R-712

### T-716 · legacy fixture 显式测试

- 文件: `tests/test_replay_corpus.py`
- 签名: `test_legacy_artifact_fixture_is_explicitly_named`
- Requirement: R-713

---

## PR-C · replay artifact failure narratives

> 满足 requirements: **R-721 / R-722**

### T-721 · 新增至少两个 replay fixtures

- 文件: `tests/fixtures/replay/*.json`
- 动作: 从以下类别至少选择两类新增 fixture：rating-scaling mismatch、invalid artifact metadata shape、breaker open short-circuit、shadow/advisory transition、lease-loss drain behavior。
- Requirement: R-721

### T-722 · fixture expected trace values 非平凡

- 文件: 同 T-721
- 动作: 每个新增 fixture 的 `expected.trace_values` 必须包含 artifact / guardrail marker，不只断言 final kind。
- Requirement: R-722

### T-723 · replay corpus README catalog 更新

- 文件: `tests/fixtures/replay/README.md`
- 动作: 为新增 fixtures 加 catalog 行，说明 scenario、expected kind、trace marker。
- Requirement: R-721 / R-722

---

## PR-D · lease readiness boundary docs

> 满足 requirements: **R-731 / R-732**

### T-731 · Codex summary 链接 readiness boundary

- 文件: `docs/codex-review/2026-06-codex-summary.md` 或 linked operational doc
- 动作: 明确 `/healthz` process-only、`/readyz` 包含 lease health、lease loss 只触发 not-ready，traffic drain 由 orchestrator 负责。
- Requirement: R-731

### T-732 · FileLease 非分布式锁说明

- 文件: 同 T-731 或 ADR-0007 linked section
- 动作: 明确 `FileLease` 是 local-filesystem coordination，不提供 multi-writer distributed lease 语义。
- Requirement: R-732

---

## PR-doc-03 · supersede historical trackers

> 满足 requirements: **R-801 / R-802**

### T-801 · action-items 顶部加 superseded banner

- 文件: `docs/claude-review/action-items.md`
- 动作: 在标题后、旧正文前加入 blockquote banner：
  - 说明该文件是 2026-05/06 历史 tracker
  - 当前 F-001 ~ F-010 已 resolved
  - 当前可执行入口是 `spec-v3/README.md`
  - 历史闭环见 `2026-06-spec-completion.md` 与 `2026-06-codex-package-review.md`
- Requirement: R-801

### T-802 · test-coverage-gaps 顶部加 superseded banner

- 文件: `docs/claude-review/test-coverage-gaps.md`
- 动作: 同 T-801；额外说明“现有 105 个测试”是历史基线，不是当前测试数。
- Requirement: R-801

### T-803 · README 当前轮入口切到 spec-v3

- 文件: `docs/claude-review/README.md`
- 动作:
  1. 新增“当前轮（2026-07 D+A2，准备中）”章节，链接 `spec-v3/README.md`。
  2. 将现有“当前轮（2026-06 C+A2，已完成）”改名为“上一轮”。
  3. 在跨轮参考中把 `action-items.md` / `test-coverage-gaps.md` 标为历史 tracker。
- Requirement: R-802

### T-804 · codex-review README 链接到 spec-v3

- 文件: `docs/codex-review/README.md`
- 动作: 在 Claude Review Result 下补“follow-up spec: `../claude-review/spec-v3/README.md`”。
- Requirement: R-802

---

## PR-ci-01 · enforce latency budget

> 满足 requirements: **R-811 / R-812**

### T-811 · bench.latency quick 模式支持 budget assert

- 文件: `bench/latency.py`
- 动作: 修改退出逻辑，使 `--quick --p99-ms <budget>` 也会在 p99 超预算时返回 1。
- 约束: 不改变默认 `python -m bench.latency --quick` 的 smoke 行为；只有显式传入
  `--p99-ms` 时 quick 才 enforce。
- Requirement: R-811

### T-812 · 增加 benchmark 单元测试

- 文件: 新建或追加 `tests/test_latency_benchmark.py`
- 动作:
  - monkeypatch `_run` 返回固定 samples
  - 调 `latency.main(["--quick", "--p99-ms", "1.0"])`
  - 断言返回 1 且 stderr 包含 `PERF REGRESSION`
  - 再测 `latency.main(["--quick"])` 对同一 samples 返回 0
- Requirement: R-811

### T-813 · CI benchmark 加显式预算

- 文件: `.github/workflows/ci.yml`
- 动作: `python -m bench.latency --quick` 改为
  `python -m bench.latency --quick --p99-ms 50`
- Requirement: R-812

---

## PR-test-01 · replay fixture naming hardening

> 满足 requirements: **R-821 / R-822**

### T-821 · naming 测试读取 expected.kind

- 文件: `tests/test_replay_corpus.py`
- 符号: `test_fixture_naming_matches_convention` 或新函数
- 动作:
  - 遍历 `tests/fixtures/replay/*.json`
  - `json.loads(path.read_text(...))`
  - 读取 `expected_kind = raw["expected"]["kind"]`
  - 断言 `path.stem.endswith(f"_{expected_kind}")`
  - 保留 allowed suffix 检查
- Requirement: R-821

### T-822 · name 字段与文件名一致

- 文件: `tests/test_replay_corpus.py`
- 动作: 若 fixture 中存在 `name` 字段，断言 `raw["name"] == path.stem`。
- Requirement: R-822

---

## PR-test-02 · artifacts public import snapshot

> 满足 requirement: **R-831**

### T-831 · public surface expected set

- 文件: 新建或追加 `tests/test_artifacts_public_api.py`
- 动作: 定义 frozen expected symbols：
  - `ArtifactMetadata`
  - `build_metadata`
  - `EOMM_FEATURE_NAMES`
  - `RetentionArtifact`
  - `RetentionScalingCompatibility`
  - `_rating_scaling_version`
  - `build_history_vector`
  - `build_match_config`
  - `load_retention_artifact`
  - `retention_scaling_compatibility`
  - `save_retention_artifact`
  - `validate_retention_artifact`
  - `CoxArtifact`
  - `load_cox_artifact`
  - `save_cox_artifact`
  - `validate_cox_artifact`
  - `RuntimeArtifactBundle`
  - `load_runtime_artifacts`
- Requirement: R-831

### T-832 · assert module attrs and __all__

- 文件: `tests/test_artifacts_public_api.py`
- 动作:
  - `import gan_matchmaking.sre.artifacts as artifacts`
  - `assert set(artifacts.__all__) == EXPECTED_PUBLIC_SYMBOLS`
  - 对每个 symbol 断言 `hasattr(artifacts, symbol)`
- Requirement: R-831

---

## PR-test-03 · HTTP lease readiness integration

> 满足 requirements: **R-841 / R-842**

### T-841 · 复用 HTTP server fixture

- 文件: `tests/test_http_service.py`
- 动作: 复用现有 test server fixture；若 fixture 没暴露 app，则轻微扩展 fixture
  返回 `(base_url, app)` 或等价结构。
- Requirement: R-841

### T-842 · readyz HTTP reflects lease failure

- 文件: `tests/test_http_service.py`
- 签名: `def test_readyz_http_reflects_lease_failure(...): ...`
- 动作:
  - 启动 test server
  - 调 `app.mark_lease_unhealthy(RuntimeError("boom"))`
  - HTTP GET `/readyz`
  - 断言 status code 503，JSON `status == "not_ready"`，`reason == "lease_unhealthy"`
- Requirement: R-841

### T-843 · healthz HTTP remains process health

- 文件: `tests/test_http_service.py`
- 动作: 同一测试或独立测试中 GET `/healthz`，断言 status code 200，JSON
  `status == "ok"`。
- Requirement: R-842

---

## 任务依赖矩阵

```
PR-doc-03
  T-801 / T-802 / T-803 / T-804 可并行

PR-ci-01
  T-811 → T-812 → T-813

PR-test-01
  T-821 → T-822

PR-test-02
  T-831 → T-832

PR-test-03
  T-841 → T-842/T-843
```

---

## Requirement → Task 反查

| Requirement | Task(s) |
|---|---|
| R-801 | T-801, T-802 |
| R-802 | T-803, T-804 |
| R-811 | T-811, T-812 |
| R-812 | T-813 |
| R-821 | T-821 |
| R-822 | T-822 |
| R-831 | T-831, T-832 |
| R-841 | T-841, T-842 |
| R-842 | T-843 |
