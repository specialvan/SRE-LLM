# Requirements v3 · D+A2 本轮

EARS-A2 句式：`WHEN <trigger> THE SYSTEM SHALL <observable behavior>`。

---

## A-001 · Runtime / replay artifact compatibility 对齐

### R-701 · Shared rating-scaling compatibility helper

**WHEN** runtime hydration 或 replay validation 需要判断 retention artifact 是否兼容当前 rating-scaling constants,
**THE SYSTEM SHALL** 调用同一个 artifact-layer helper,
**AND** helper 返回 machine-readable status: `match` / `mismatch` / `unknown` / `absent`,
**AND** 返回 expected version、actual version、artifact metadata version。

- 来源: `docs/codex-review/CLAUDE_REFINED_SPEC.md` PR-A
- 验证: `test_runtime_and_replay_use_same_scaling_helper`
- 反例: `self_iteration.py` 和 `replay.py` 各自复制 compatibility 判断，未来漂移

### R-702 · Runtime mismatch behavior preserved

**WHEN** runtime hydration 遇到 `mismatch` retention artifact,
**THE SYSTEM SHALL** 记录 `artifacts.retention.scaling_mismatch` warning,
**AND** 在 trace / bundle 中标记 `rating_scaling_status="mismatch"`,
**AND** 不 hydrate retention artifact。

- 来源: F-005 既有行为，v3 只抽共享 helper
- 验证: 既有 `tests/test_rating_scaling.py` + helper status 测试

### R-703 · Replay validation rejects mismatch

**WHEN** `validate_artifact_bundle(artifact_dir, expected_version)` 遇到 retention scaling `mismatch`,
**THE SYSTEM SHALL** raise `DataError`,
**AND** error details 包含 expected rating-scaling version、actual rating-scaling version、artifact metadata version、artifact directory。

- 来源: `CLAUDE_REFINED_SPEC.md` PR-A
- 验证: `test_replay_validation_rejects_rating_scaling_mismatch`
- 反例: replay export 接受 runtime 会降级的 bundle

### R-704 · Legacy unknown must be explicit in replay validation

**WHEN** replay validation 遇到缺少 `rating_scaling_version` 的 legacy retention artifact,
**THE SYSTEM SHALL** 默认拒绝或要求显式 `allow_legacy_unknown=True`,
**AND** fixture / doc 必须说明这是 legacy unknown path。

- 来源: `CLAUDE_REFINED_SPEC.md` PR-A
- 验证: `test_replay_validation_requires_explicit_legacy_unknown`

---

## B-001 · Modern fitted replay metadata

### R-711 · Modern fitted fixtures carry rating_scaling_version

**WHEN** 测试或导出器生成 modern fitted replay fixture,
**THE SYSTEM SHALL** 在 retention artifact metadata 中写入当前 `_rating_scaling_version()`,
**AND** fixture 不应落入 legacy `unknown` compatibility path。

- 来源: `CLAUDE_REFINED_SPEC.md` PR-B
- 验证: `test_modern_artifact_fixture_has_scaling_version`

### R-712 · Modern fitted replay asserts scaling match

**WHEN** modern fitted-artifact replay 被 golden corpus 回放,
**THE SYSTEM SHALL** 在 expected trace values 中断言 `trace.artifacts.rating_scaling_status == "match"`。

- 来源: `CLAUDE_REFINED_SPEC.md` PR-B
- 验证: `test_modern_artifact_replay_reports_scaling_match`

### R-713 · Legacy unknown fixture explicitly named

**WHEN** 保留 legacy unknown fitted replay fixture,
**THE SYSTEM SHALL** 在文件名、README catalog 或 fixture metadata 中明确标记 legacy unknown,
**AND** 不让 legacy unknown 与 modern fitted fixture 混淆。

- 来源: `CLAUDE_REFINED_SPEC.md` PR-B
- 验证: `test_legacy_artifact_fixture_is_explicitly_named`

---

## C-001 · Artifact failure / guardrail replay narratives

### R-721 · Add artifact or guardrail narrative fixtures

**WHEN** 本轮扩展 replay corpus,
**THE SYSTEM SHALL** 新增至少两个 fixtures，覆盖以下类别中的至少两类：retention rating-scaling mismatch、invalid artifact metadata shape、breaker open short-circuit、shadow/advisory transition、lease-loss drain behavior。

- 来源: `CLAUDE_REFINED_SPEC.md` PR-C
- 验证: `tests/test_replay_corpus.py` 参数化 corpus

### R-722 · New narratives carry non-trivial trace assertions

**WHEN** 新 replay fixture 描述 artifact failure 或 guardrail short-circuit,
**THE SYSTEM SHALL** 在 `expected.trace_values` 中包含对应 artifact / guardrail marker,
**AND** context 必须能被 `ReleaseContext.from_dict` 接受,
**AND** 文件名 suffix 必须等于 expected decision kind。

- 来源: `CLAUDE_REFINED_SPEC.md` PR-C
- 验证: replay corpus 测试 + R-821 naming 测试

---

## D-001 · Lease readiness boundary documentation

### R-731 · Health and readiness boundary is explicit

**WHEN** operator 阅读 Codex review summary 或链接的 operational doc,
**THE SYSTEM SHALL** 明确说明 `/healthz` 是 process health only,
**AND** `/readyz` 包含 lease health,
**AND** lease loss 只让 pod not-ready，流量 drain 委托给 orchestrator。

- 来源: `CLAUDE_REFINED_SPEC.md` PR-D
- 验证: 文档 grep / 人工审阅

### R-732 · FileLease is not distributed lock

**WHEN** 文档描述 `FileLease`,
**THE SYSTEM SHALL** 明确说明它只做 local-filesystem coordination,
**AND** 不得暗示它能提供 multi-writer distributed lease 语义。

- 来源: `CLAUDE_REFINED_SPEC.md` PR-D / ADR-0007
- 验证: 文档 grep / 人工审阅

---

## E-001 · 历史 tracker 状态收敛

### R-801 · Superseded banner

**WHEN** 读者打开 `docs/claude-review/action-items.md` 或
`docs/claude-review/test-coverage-gaps.md`,
**THE SYSTEM SHALL** 在正文前显示明确的 superseded banner,
**AND** banner 必须指向 `2026-06-spec-completion.md`、
`2026-06-codex-package-review.md` 与本 spec-v3,
**AND** banner 必须说明旧文档不是当前 blocker / work queue。

- 来源: `2026-06-codex-package-review.md` P3 historical trackers
- 验证: 文档 grep + 人工审阅
- 反例: 读者看到“合入前必做”后误以为 F-001 ~ F-010 仍 open

### R-802 · README 入口分层

**WHEN** 读者从 `docs/claude-review/README.md` 进入评审资料,
**THE SYSTEM SHALL** 把 2026-07 spec-v3 标为当前可执行入口,
**AND** 把 2026-06 spec-v2 标为已完成归档,
**AND** 把 `action-items.md` / `test-coverage-gaps.md` 标为历史 tracker。

- 来源: 文档一致性评审
- 验证: README 链接和描述检查

---

## E-002 · Latency gate

### R-811 · Quick benchmark 可选择强制预算

**WHEN** 执行 `python -m bench.latency --quick --p99-ms <budget>`,
**THE SYSTEM SHALL** 在 quick 模式下仍计算 p99,
**AND** 当 `p99_ms > budget` 时返回非零退出码,
**AND** stderr 输出 `PERF REGRESSION`。

- 来源: `2026-06-codex-package-review.md` P3 quick benchmark smoke-only
- 验证: `test_latency_benchmark_quick_can_enforce_budget`
- 反例: CI 只打印 p99，不失败

### R-812 · CI 使用显式 latency budget

**WHEN** GitHub Actions benchmark job 运行,
**THE SYSTEM SHALL** 调用带 `--p99-ms` 的 benchmark 命令,
**AND** 该命令在预算失败时让 job fail,
**AND** 阈值必须足够宽松以降低共享 runner 抖动。

- 来源: production readiness review
- 验证: `.github/workflows/ci.yml` 命令包含 `--quick --p99-ms 50`

---

## E-003 · Replay naming contract hardening

### R-821 · Filename suffix 等于 expected.kind

**WHEN** `tests/fixtures/replay/*.json` 下新增或修改 fixture,
**THE SYSTEM SHALL** 断言文件名 stem 以 `_{expected.kind}` 结尾,
**AND** `expected.kind` 必须来自 fixture JSON,
**AND** suffix 只属于 `go / canary / hold / rollback / escalate`。

- 来源: Codex package review P3 replay suffix test gap
- 验证: `test_fixture_naming_matches_expected_kind`
- 反例: `budget_go.json` 内部 expected.kind 是 `rollback` 仍通过

### R-822 · Fixture internal name 与文件名一致

**WHEN** fixture JSON 包含 `name` 字段,
**THE SYSTEM SHALL** 断言 `raw["name"] == path.stem`,
**AND** 防止文件名与内部 catalog 名称漂移。

- 来源: replay corpus 可维护性
- 验证: 同 R-821 测试

---

## E-004 · Artifacts import compatibility snapshot

### R-831 · Public surface 快照

**WHEN** `gan_matchmaking.sre.artifacts` package 被 import,
**THE SYSTEM SHALL** 暴露 frozen expected symbol set,
**AND** 每个 expected symbol 都在模块属性和 `__all__` 中,
**AND** 删除或改名 public symbol 会触发测试失败。

- 来源: Codex package review P3 artifacts package import compatibility
- 验证: `test_artifacts_public_surface_is_stable`
- 反例: 未来 cleanup 从 `__all__` 删除低频 symbol 而测试不报错

---

## E-005 · Lease readiness HTTP boundary

### R-841 · HTTP readyz reflects lease unhealthy

**WHEN** HTTP service 已启动且调用 `DecisionApp.mark_lease_unhealthy(error)`,
**THE SYSTEM SHALL** 让真实 HTTP `GET /readyz` 返回 503,
**AND** response JSON 包含 `status="not_ready"` 与 `reason="lease_unhealthy"`。

- 来源: Codex package review P2 handler-level-only readiness evidence
- 验证: `test_readyz_http_reflects_lease_failure`

### R-842 · HTTP healthz remains process health

**WHEN** lease unhealthy 已标记,
**THE SYSTEM SHALL** 让真实 HTTP `GET /healthz` 仍返回 200,
**AND** response JSON 保持 process health 语义，不混入 writer lease 状态。

- 来源: ADR-0007 / F-001 readiness split
- 验证: 同 R-841 测试

---

## 共同契约

- 本轮不改已 resolved 的 F-001 ~ F-010 结论；只有新 failing test / 可复现回归才可重开。
- 不改变 `/v1/*` API 路径。
- 不改变 `Decision` 对外字段。
- 不改变 trace schema，除非测试只读取既有字段。
- 新测试必须 deterministic，不依赖真实 sleep。