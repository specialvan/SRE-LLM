# Opus Handoff

> 给 Opus 介入复审的首读交接。当前状态以源码、测试和已提交证据产物为准；旧评审包只作为历史上下文。

## 0. 当前状态

- 分支：`spacex-session`。
- 当前评审切片：Opus v2.1 反馈后的修复、证据链、控制中心安全面、质量门和评审文档整理。
- 当前 pytest 计数：`475`。该计数来自 `python -u -m scripts.quality_gate_counts`。
- 当前唯一开放风险：`docs/codex-review/OPEN_RISKS.md` 中的 `R1`，即 synthetic evidence boundary。所有对外总结仍必须说明这些是合成场景证据，不是生产证明，也不是 SpaceX 官方实现。
- 本文件所在提交只做交接和最新 gate 计数同步；前面的实现提交已按内容拆分。

## 1. 首读入口

建议 Opus 按以下顺序读，不要从旧 v1.0 文档反推当前状态：

1. `docs/opus-review/HANDOFF.md`：当前交接和审阅路线。
2. `docs/opus-review/README.md`：当前 Opus 入口和权威顺序。
3. `docs/opus-review/OPUS_REVIEW_PACKET.md`：复审命令、证据资产和历史 findings 对照。
4. `claude-review/docs/v2026-05-28/README.md`：Opus v2.1 原始反馈。
5. `docs/codex-review/OPEN_RISKS.md`：当前风险边界。
6. `wiki/review-backlog.md`：跨会话完成状态和证据索引。
7. `docs/EVENT_EVIDENCE_MANIFEST.md` 与 `docs/STACK_DATA_CONTRACT.md`：机器可验的证据/契约边界。
8. `docs/CONTROL_CENTER_HANDOFF.md`：控制中心浏览器证据和前端契约细节。

## 2. 提交分组

这轮为了方便 Opus 按内容审，已经拆成语义提交：

| Commit | 主题 | Opus 建议关注点 |
|---|---|---|
| `f679e6d` | `fix(sre)` 控制适配器边界与数值安全 | 非有限值、异常事件、EKF/稳定性/负载分配边界是否真正落到测试里 |
| `fa73ac0` | `feat(analysis)` 事件证据清单与 S10/S11/S12 回放 | manifest byte identity、strict JSON、回放 fixture 是否避免证据过度解释 |
| `64b8dd9` | `feat(control-center)` 控制中心契约和本地暴露边界 | loopback/Host 策略、hash share-state 白名单、DOM XSS 防护和浏览器 smoke 覆盖 |
| `d00dc8b` | `test(gates)` 包烟测和质量门编排 | gate 是否覆盖必须命令，`--check` 是否只读，缺失命令是否会失败 |
| `8fd9b84` | `docs(review)` Opus/Codex 台账同步 | 历史评审、当前风险和完成状态是否有冲突 |
| `b6ee79b` | `chore(evidence)` 刷新分析与浏览器证据产物 | 产物是否与生成脚本/manifest 一致 |
| `9b70909` | `fix(evidence)` 稳定 DOM 证据哈希 | Windows 行尾是否还会造成 manifest sha/bytes 漂移 |
| `3fb5464` | `fix(evidence)` 集成审计可复现 | `generated_at` 是否不再污染工作区，连续写出是否稳定 |
| `1da8e3f` | `chore(evidence)` S11 wrapper 图像刷新 | S11 图像是否与当前生成器输出一致 |

后续若出现本 handoff 提交，主要是文档入口和 `475` gate 计数同步，不应混入运行时逻辑。

## 3. 最小复核命令

从干净工作区复核时建议先跑这些命令：

```powershell
python -m pytest tests -q
python -u -m scripts.quality_gate_counts
python -m scripts.quality_gate_counts --check --skip-expensive
python -m analysis.evidence_manifest
python -m analysis.evidence_report
python -m scripts.control_center_browser_smoke --report-manifests --report-json analysis/artifacts/control-center-browser-evidence-report.json
python -m scripts.package_smoke
python -m scripts.control_center_integration_audit
```

当前关键输出应包含：

```text
quality gate pytest count: 475
artifact_check ok studies=3 files=8
manifest_replay=normal+backend_error+frontend_error
control-center integration audit ok
```

浏览器证据命令的正常摘要应包含：

```text
contract=control-center.v1 @ /api/control-center
normal=desktop:1440x960:dom148125, mobile:390x844:dom148125
error=desktop:1440x960:dom107235
frontend_error=desktop:1440x960:dom107217
manifest_records=normal:2727:e6b85543218d backend_error:680:7e7a2d1bd95b frontend_error:707:884f54d7a3e3
```

## 4. 证据资产

重点机器可读资产：

- `analysis/artifacts/event_evidence_manifest.json`：S10/S11/S12 事件证据索引，包含 artifact metadata。
- `analysis/artifacts/s10_trace_full.jsonl` 与 `analysis/artifacts/s10_trace_sample.jsonl`：Section 10 runtime event trace。
- `analysis/artifacts/s11_catch_sre_wrapper_diagnostics.json`：Catch/SRE wrapper 三类 regime 诊断。
- `analysis/artifacts/s12_replay_trace.jsonl` 与 `analysis/artifacts/s12_replay_diagnostics.json`：固定 replay fixture 输出。
- `analysis/artifacts/sre_stack_data_contract.json`：研究型 SRE stack data contract。
- `analysis/artifacts/control-center-browser-*-manifest.json`：正常、backend contract error、frontend contract error 三类浏览器证据 manifest。
- `analysis/artifacts/control-center-browser-evidence-report.json`：浏览器 manifest replay 汇总。
- `analysis/artifacts/control-center-integration-audit.json`：控制中心 API payload、浏览器证据和 package smoke 的整合审计。

重点视觉资产：

- `analysis/artifacts/s10_event_density.png`
- `analysis/artifacts/s11_catch_sre_wrapper.png`
- `analysis/artifacts/s09_sre_stack.png`
- `docs/V2_Knowledge/knowledge-base.html`

## 5. 建议 Opus 深挖点

1. SRE runtime guard 是否真正拒绝非有限值，而不是下游数值库偶然失败。
2. `adapter_exception`、`bounded_ls_residual`、`stability_violation` 等 event payload 是否满足 `sre_control.events.EVENT_FIELD_SCHEMA`。
3. `analysis.evidence_report` 是否足够严格：路径必须 repo-relative、artifact bytes/sha256 必须一致、JSON/JSONL/PNG 必须可解析、stack contract 不得声称 production。
4. 控制中心前端是否只通过白名单恢复 share-state，动态文本是否走 text/escape 路径，错误路径是否不会注入 DOM。
5. `scripts.control_center_browser_smoke` 的 manifest replay 错误信息是否给出 manifest、viewport、DOM path 和 regeneration command，方便复现。
6. `scripts.quality_gate_counts` 是否真的把 PR、V2 HTML、Codex quality gates、Opus packet 中的命令/计数保持同步。

## 6. 注意事项

- 浏览器 smoke 的三类“生成”模式不要并行跑。系统浏览器会共用临时 profile，并行可能导致浏览器进程级失败；manifest replay/report 可以单独跑。
- `analysis.run_all` 和 `scripts.quality_gate_counts` 会刷新 `analysis/artifacts/SUMMARY.txt` 的 elapsed 时间，复跑后可能出现仅时间字段变化的产物 diff。
- `analysis.evidence_manifest` 会重生 Section 11 图像和 manifest metadata。若复跑后出现产物差异，先看是否来自生成器当前输出，不要当成源码回归。
- 旧 `docs/opus-review/v1.0/` 和 `claude-review/docs/v2026-05-26/` 是历史输入，不是当前 open-risk ledger。
- 本仓库是公开材料研究复现；任何“生产可用”“官方 SpaceX 实现”“真实生产证明”表述都应被视为过界。

## 7. 交付判定

本轮交付目标不是合并到主干，而是让 Opus 能快速复审：

- 按提交分组定位代码和证据改动。
- 用固定命令复跑当前证据链。
- 从当前风险台账判断是否还有 blocker。
- 将历史 findings 与当前代码/测试/产物对应起来。

若 Opus 只想先做 blocker pass，建议优先审：`f679e6d`、`fa73ac0`、`64b8dd9`、`9b70909`、`3fb5464`，再看文档和生成产物提交。