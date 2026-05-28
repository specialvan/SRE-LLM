# Opus v2.1 继续深挖评审报告（2026-05-28）

> 本目录是对 codex 当前工作树的继续深挖 review，评审对象为 `docs/opus-review/OPUS_REVIEW_PACKET.md` 声称的 F50–F60 修复包、control-center browser evidence、manifest/report 证据链与质量门。用户要求“颗粒度不够，继续深挖”，因此本轮报告按最小复现输入、实际输出、行级根因、影响链路和验收标准展开。

## 文档清单

| 文件 | 用途 |
|---|---|
| `00-blocker-summary.md` | 合并门禁结论、质量门实测失败、阻断项总览 |
| `01-line-level-findings.md` | F61–F72 行级 findings，含复现脚本/输出/修复验收 |
| `02-evidence-chain-audit.md` | evidence manifest、browser smoke、package smoke、run_all 的证据链审计 |
| `03-security-and-doc-consistency.md` | control-center DOM、localhost、manifest path、文档风险台账一致性审计 |
| `04-deeper-dive-addendum.md` | 第二轮继续深挖追加：F73–F81、测试绿但 saved evidence replay 红、drift tests 缺口 |
| `evidence/rerun-log-2026-05-28.md` | 本轮实测命令与最小复现输出 |

## 总结论

**Block，不建议按当前工程包声明合入。**

主要原因：

1. `docs/codex-review/QUALITY_GATES.md` 声称 `437 passed` / 当前质量门全绿，但质量门同步入口 `python -u -m scripts.quality_gate_counts` 仍实测失败。
2. 最新复跑显示 `tests/test_control_center_browser_smoke.py` 单独已通过，说明测试 fixture 已同步；但 saved browser manifest replay 仍缺 `capacity-budget-list` / `data-capacity-focus`，问题已收敛为“mock 测试绿、真实证据制品红”。
3. F50–F60 中多数主问题已修复，但继续深挖发现新的 P1/P2 缺陷：SignalFusion 可接受 NaN 读数并污染 EKF，SLOGuardrail public `approve()` 仍返回 NaN 安全动作，CanaryScheduler 拒绝 warm-start 后事件声称 shrink 但 trust region 反而 expand。
4. 证据链存在 stale / non-portable / non-strict JSON 风险：browser manifest 写绝对路径，JSON writer 未 `allow_nan=False`，`analysis.run_all(artifacts_dir=...)` 只把 SUMMARY 写到目标目录而不转发 artifacts_dir 给 studies。
5. control-center HTML 的 share hash 状态未白名单化，且部分动态文本进入 `innerHTML` 未统一 `esc()`，存在 DOM XSS 风险。

## 严重度统计

| 严重度 | 数量 | IDs |
|---|---:|---|
| P0 | 0 | - |
| P1 | 11 | F61, F62, F63, F64, F65, F66, F67, F73, F75, F76 |
| P2 | 11 | F68, F69, F70, F71, F72, F74, F77, F78, F79, F80, F81 |

## 与 2026-05-26 v2.0 评审关系

- F50、F51、F53、F55、F56、F57、F58、F59、F60 的主修复路径基本属实。
- F52 主问题“warm-start 幻影斜率”已修，但 rejected warm-start 的 trust-region 行为产生新问题 F63。
- F54 的 `audit()` 路径已修，但同一 public 类 API `approve()` 未修，形成新问题 F62。
- 2026-05-26 的质量门基线 `276 passed` 已不是当前状态；当前工程包声称 `437 passed`，但本轮实测失败。
