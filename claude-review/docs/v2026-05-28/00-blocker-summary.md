# 00 — 阻断摘要与门禁判定

> Historical subreport from a prior Opus review packet; it is not the current handoff.
> Opus review should start from `docs/opus-review/HANDOFF.md`, then verify
> live status in `wiki/review-backlog.md`,
> `docs/codex-review/OPEN_RISKS.md`, and
> `docs/codex-review/QUALITY_GATES.md`.

## 门禁判定

**结论：Block。**

当前 `docs/opus-review/OPUS_REVIEW_PACKET.md` 与 `docs/codex-review/QUALITY_GATES.md` 的核心声明不能作为合入依据：

- 声称 `python -m pytest tests -q` 当前为 `437 passed`，但本轮实测失败 4 项。
- 声称 `python -u -m scripts.quality_gate_counts` 可更新/校验质量门，但本轮实测失败。
- `analysis.evidence_manifest && analysis.evidence_report` 通过，只能说明 S10/S11/S12 event manifest 当前自洽，不能覆盖 browser smoke stale DOM、package smoke、control-center integration 当前性。

## 本轮实测质量门

| 命令 | 实测结果 | 结论 |
|---|---|---|
| `python -m pytest tests -q` | `433 passed, 4 failed` | Block |
| `python -m analysis.evidence_manifest && python -m analysis.evidence_report` | `artifact_check ok studies=3 files=8` | Pass，但覆盖范围有限 |
| `python -u -m scripts.quality_gate_counts` | `AssertionError: browser DOM dump missing: ['safety-budget-list', 'data-budget-focus']` | Block |

### pytest 失败项

全部位于 `tests/test_control_center_browser_smoke.py`：

1. `test_system_browser_smoke_decodes_utf8_dom_dump`
2. `test_system_browser_smoke_gives_async_fetch_time`
3. `test_dom_assertion_ignores_error_literals_in_script_source`
4. `test_dom_assertion_rejects_rendered_error_message`

共同根因：`scripts/control_center_browser_smoke.py:797-810` 的 `_assert_dumped_dom()` 新增要求 DOM 中包含：

- `safety-budget-list`
- `data-budget-focus`

但测试 fixture 与已保存 browser manifest DOM dump 没有同步更新。`quality_gate_counts` 在 replay saved manifest 时也走到同一断言并失败。

## 阻断项清单

| ID | 严重度 | 区域 | 一句话结论 |
|---|---|---|---|
| F61 | P1 | 质量门 | 当前 pytest 失败，`437 passed` 声明失效 |
| F62 | P1 | 质量门 | `quality_gate_counts` replay browser evidence 失败，质量门自更新不可用 |
| F63 | P1 | 控制核心 | `SignalFusion.step()` 接受 NaN sensor reading，污染 EKF state 且 trace 写出 JSON NaN |
| F64 | P1 | 控制核心 | `SLOGuardrail.audit()` 修复 NaN，但 public `approve()` 仍返回 `[nan,nan,nan]` |
| F65 | P1 | 控制核心 | `CanaryScheduler` rejected warm-start 声称 shrink，实际 eta 连续 expand |
| F66 | P1 | 证据链 | evidence JSON/JSONL writer 未 `allow_nan=False`，严格 JSON 声明有洞 |
| F67 | P1 | 前端安全 | share hash 未白名单 + innerHTML 未统一 escape，存在 DOM XSS 面 |
| F68 | P2 | 证据链 | browser source manifest 写绝对路径，不可移植且 replay 绑定生成机 |
| F69 | P2 | 证据链 | `run_all(artifacts_dir=...)` 只迁移 SUMMARY，不迁移 study artifacts |
| F70 | P2 | 质量门 | `CURRENT_QUALITY_GATE_COMMANDS` 未纳入 browser smoke report / package smoke |
| F71 | P2 | 安全边界 | control-center server 可被调用方绑定非 loopback，Host header 不是网络边界 |
| F72 | P2 | 文档一致性 | package/integration audit 对 saved manifest replay 与 current proof 边界表述过强 |

## 建议修复顺序

1. **先恢复质量门**：修正 control-center browser smoke fixture/artifacts，重新生成 browser manifest/report，使 pytest 与 `quality_gate_counts` 先变绿。
2. **修 P1 控制核心**：F63、F64、F65 必须加回归测试后修复。
3. **修严格证据链**：所有 machine-readable evidence writer 统一 `allow_nan=False`，reader 递归拒绝非有限 float。
4. **修 browser evidence 可移植性**：manifest 内 artifact path 改 repo-relative，并加 containment 校验。
5. **修前端安全边界**：share hash 字段白名单化，动态 HTML 全部 escape 或改 `textContent`。
6. **最后同步文档**：`QUALITY_GATES.md`、`OPUS_REVIEW_PACKET.md`、`OPEN_RISKS.md` 必须区分实时重跑、saved replay、historical snapshot。
