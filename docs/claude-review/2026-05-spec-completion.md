# 2026-05 Spec Completion · B+A2

Scope closed: **F-001, F-002, F-003** (+ bonus: F-004)

## Commits

| PR | Commit | Scope |
|---|---|---|
| PR-fix-01+02+03 | `704765d` | F-001 LeaseRefreshLoop 可见化 / F-002 Shadow metric & log 一致 / F-003 Trace config allowlist + ADR-0006 补充 |
| PR-fix-04 (bonus) | `6834ab3` | F-004 消除 `decide()` 对 `ctx.service` 的 `_deps` 隐式 mutation，显式化 `observe_release(dependencies=...)` 入口并接入 HTTP `/v1/observe` |

codex 把 PR-fix-01~03 合并为一个提交，但每条 finding 都有独立的 acceptance
criteria 与测试覆盖，可按 commit 内部文件维度单独回看。

## Requirement 覆盖矩阵

| Requirement | 来源 finding | 测试 |
|---|---|---|
| R-001 ~ R-005 | F-001 | `tests/test_leases.py::test_refresh_failure_*`, `test_healthy_app_returns_ready`, `test_loop_invokes_callback_on_refresh_failure` |
| R-101 ~ R-105 | F-002 | `tests/test_sre_self_iteration.py::test_shadow_mode_*`, `test_off_mode_unaffected_by_shadow_fix`, `test_advisory_mode_metric_uses_final_kind`, `test_shadow_rewrite_preserves_trace_fields` |
| R-201 ~ R-204 | F-003 | `tests/test_trace_privacy.py::test_trace_config_only_embeds_allowlisted_keys`, `test_trace_config_allowlist_snapshot` |

所有 14 条 R-XXX 均有至少一条测试断言；`# pragma: no cover - surfaced by error`
已按 R-005 从 `leases.py::_run` 移除。

## 数值结果

- `pytest -q`: **123 passed** (原 105 + 新增 18)
- `python -m bench.latency --quick`: **p99 = 1.03 ms** (预算 2.5 ms, 残留余量 1.47 ms)
- `grep -rn "pragma: no cover" gan_matchmaking/`: 只剩允许位点
  (`service/app.py` 的 HTTP catch-all, 三处 `__main__` 入口, `cli.py` 末尾的 last-resort)
- `findings.md`: F-001 / F-002 / F-003 / F-004 全部标为
  `resolved (commit <sha>, 2026-05-12)`
- `docs/adr/0006-runtime-artifact-versioning.md` 末尾追加
  "What must never enter trace" 隐私治理段（作为 F-003 的制度沉淀）

## 新增代码统计

| 路径 | 增删行数 |
|---|---|
| `gan_matchmaking/sre/leases.py` | +17 / -4 |
| `gan_matchmaking/service/app.py` | +50 / -0 |
| `gan_matchmaking/service/__main__.py` | +6 / -1 |
| `gan_matchmaking/core/config.py` | +45 / -0 |
| `gan_matchmaking/sre/self_iteration.py` | +51 / -12 |
| `docs/adr/0006-runtime-artifact-versioning.md` | +18 / -0 |
| `tests/test_leases.py` | +128 / -0 |
| `tests/test_sre_self_iteration.py` | +153 / -0 |
| `tests/test_trace_privacy.py` | +102 / -0 (新建) |
| **合计** | **+570 / -17** |

（F-004 的 `+60 / -7` 在 `6834ab3` 中，已单列）

## 未覆盖条目 · 延期下一轮

| finding | severity | 原因 |
|---|---|---|
| F-005 `_service_player` 硬编码常数 | P3 | 需要 artifact 稳定性专项；本轮范围外 |
| F-006 `sre/artifacts.py` 488 行 | P3 | 结构重构，单独 PR 跟进 |
| F-007 `cli._ctx_from_dict` 被跨模块 `_` 私有 import | P3 | 待提升为公共 API |
| F-008 SQLite migration v5 的"列已存在跳过" | P3 | 需要 migration 框架重审 |
| F-009 handoff 与 roadmap 30% 重叠 | P4 | 文档整理 |
| F-010 replay fixture 命名风格 | P4 | 批量 rename |

下一轮评审建议开 `docs/claude-review/2026-06-session-review.md`（新快照）+
`docs/V3_Knowledge/` 子目录；本轮的 `V2_Knowledge/` 冻结不动。

## 交接路标

- **codex 新成员**: 从 `docs/codex-handoff.md` 进入，本文件是其中 "本轮状态" 段
  的脚注。
- **评审者**: `findings.md` 已经把 F-001~F-004 翻到 `resolved`，继续从 F-005
  开始即可。
- **V2 知识库快照**: `docs/V2_Knowledge/knowledge-base.html` 反映的是本轮完成
  后的系统状态（shadow 语义、lease 可见化、allowlist 隐私面），可作为
  next-reviewer 的起点。

## 规则回顾（本轮遵守情况）

| 规则 | 状态 |
|---|---|
| 新增测试 deterministic，不依赖真实 `sleep` / 真实时钟 | ✅ `test_loop_invokes_callback_on_refresh_failure` 用 `loop._run(0.0)` 强制单次循环；`mark_lease_unhealthy` 用 `RuntimeError("boom")` 模拟异常 |
| 新增日志用 `JsonLineLogger`，禁 `print` / `logging.info` 直调 | ✅ 新增两个事件 `lease.refresh.failed` / `decide.shadow_rewritten` 均走 `self.pipeline.logger` / `self.logger` |
| 新增 metric 在 `__post_init__` 注册，基数受控 | ✅ `gan_lease_refresh_failures_total{reason=<class>}` 标签集合受 `type(exc).__name__` 约束 |
| 本轮不改 `trace["stages"]["*"]` 语义 | ✅ 只改 `trace["input"]["config"]` 的内容集合，stages 未动 |
| findings 只能标 `resolved` / `deferred`，不删 | ✅ 保留 F-001~F-010 历史，只改 status 字段 |

---

本轮 spec 在工程、测试、文档三层闭合。可以把分支 `gan-session` 合入 master，
或者保持 `gan-session` 作为下一轮评审的基线。
