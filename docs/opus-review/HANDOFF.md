# Opus 评审交接

日期：2026-05-29
仓库：`D:\workspace\SRE-LLM\spacex`
分支：`spacex-session`
近期关键基线：日志中应包含 `bf63c43 docs(opus): 增加复审交接并同步质量门计数`；实际 HEAD 以 `git log -1 --oneline` 为准。

本文是给 Opus 重新介入评审的首读入口。当前事实以源代码、测试输出和已提交证据产物为准；旧版 Opus v1.0 包和 Claude review 只作为历史上下文。

## 当前基线

当前 HEAD 已包含本轮评审入口、质量门计数、知识库快照和证据产物同步。不要把这些改动理解为新的生产安全声明；Opus 复核时应以当前源码和复核命令输出为准。

按内容分组：

| 分组 | 文件 | 评审重点 |
| --- | --- | --- |
| Opus 入口 | `docs/opus-review/HANDOFF.md`, `docs/opus-review/README.md`, `docs/opus-review/OPUS_REVIEW_PACKET.md` | Opus 首读顺序、权威来源和 475-test gate 计数是否一致 |
| Codex 评审包 | `docs/codex-review/*.md`, `wiki/*.md`, `PR-REQUIREMENTS.md` | 当前质量门、开放风险和证据边界是否同步 |
| 知识库快照 | `docs/V2_Knowledge/knowledge-base.html` | 只应反映当前证据与入口，不应新增 runtime 语义 |
| 分析产物 | `analysis/artifacts/SUMMARY.txt`, `analysis/artifacts/s11_catch_sre_wrapper.png` | 是否由现有分析命令重放生成，差异是否只是当前产物刷新 |

## 建议首读顺序

1. `docs/opus-review/HANDOFF.md`：本交接入口。
2. `docs/opus-review/README.md`：当前 Opus 包入口和权威顺序。
3. `docs/opus-review/OPUS_REVIEW_PACKET.md`：复审命令、证据资产和历史 finding 对照。
4. `docs/codex-review/OPEN_RISKS.md`：当前唯一开放风险边界。
5. `wiki/review-backlog.md`：跨会话完成状态和证据索引。
6. `docs/EVENT_EVIDENCE_MANIFEST.md` 与 `docs/STACK_DATA_CONTRACT.md`：机器可验的证据/契约边界。
7. `docs/CONTROL_CENTER_HANDOFF.md`：控制中心浏览器证据和前端契约细节。
8. `claude-review/docs/v2026-05-28/README.md`：上一轮外部评审上下文。

## 已拆分的近期提交

| Commit | 主题 | Opus 建议关注点 |
| --- | --- | --- |
| `f679e6d` | SRE 控制适配器边界与数值安全 | 非有限值、异常事件、EKF/稳定性/负载分配边界是否都有测试覆盖 |
| `fa73ac0` | S10/S11/S12 事件证据清单与回放 | manifest byte identity、strict JSON、fixture 是否避免过度解释 |
| `64b8dd9` | 控制中心契约与本地暴露边界 | loopback/Host 策略、share-state 白名单、DOM XSS 防护和浏览器 smoke 覆盖 |
| `d00dc8b` | 包烟测和质量门编排 | `--check` 是否只读，缺失命令是否失败，质量门是否覆盖必须命令 |
| `8fd9b84` | Opus/Codex 台账同步 | 历史评审、当前风险和完成状态是否冲突 |
| `b6ee79b` | 分析与浏览器审计产物刷新 | 产物是否与生成脚本/manifest 一致 |
| `9b70909` | 稳定 DOM 证据哈希 | Windows 行尾是否还会造成 manifest sha/bytes 漂移 |
| `3fb5464` | 控制中心集成审计可复现 | `generated_at` 是否不再污染工作区，连续写出是否稳定 |
| `1da8e3f` | S11 wrapper 图像刷新 | S11 图像是否与当前生成器输出一致 |
| `bf63c43` | Opus handoff 与 475 gate 计数同步 | 本交接入口、Opus/Codex/wiki 计数和证据资产是否一致 |
| `7a99411` | 中文化 Opus 复审交接入口 | 首读顺序、边界说明和提交分组是否便于 Opus 直接复审 |
| `77540c3` | 隔离 Section 11 测试产物写入 | 全量 pytest 后是否不再把 canonical S11 证据图污染成测试图 |
| `9b0c88d` | Opus 交接入口纳入证据边界 lint | `HANDOFF.md` / Opus README 是否被 R1 synthetic evidence boundary 防线覆盖 |
| `3198d8e` | Opus handoff 测试计数同步 | `quality_gate_counts` 是否会同步 `HANDOFF.md` 里的 pytest count |
| `b5c950d` | pytest 质量门超时余量 | 当前 full-suite 复跑是否有足够 timeout headroom，避免复审机器抖动误超时 |

后续 handoff 修订应只包含评审入口和计数同步，不应混入运行时代码。

## 复核命令

建议 Opus 从干净工作区或清晰暂存范围运行：

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

当前文档同步目标中的关键输出：

```text
quality gate pytest count: 475
artifact_check ok studies=3 files=8
manifest_replay=normal+backend_error+frontend_error
control-center integration audit ok
```

浏览器证据命令的期望摘要仍应包含三类 manifest replay：normal、backend contract error、frontend contract error。若 DOM hash 或 bytes 变化，优先检查是否是生成器当前输出变化，不要直接当作源代码回归。

## 证据资产

机器可读重点：

- `analysis/artifacts/event_evidence_manifest.json`
- `analysis/artifacts/s10_trace_full.jsonl`
- `analysis/artifacts/s10_trace_sample.jsonl`
- `analysis/artifacts/s11_catch_sre_wrapper_diagnostics.json`
- `analysis/artifacts/s12_replay_trace.jsonl`
- `analysis/artifacts/s12_replay_diagnostics.json`
- `analysis/artifacts/sre_stack_data_contract.json`
- `analysis/artifacts/control-center-browser-*-manifest.json`
- `analysis/artifacts/control-center-browser-evidence-report.json`
- `analysis/artifacts/control-center-integration-audit.json`

视觉重点：

- `analysis/artifacts/s10_event_density.png`
- `analysis/artifacts/s11_catch_sre_wrapper.png`
- `analysis/artifacts/s09_sre_stack.png`
- `docs/V2_Knowledge/knowledge-base.html`

## 建议审查问题

1. SRE runtime guard 是否在入口拒绝非有限值，而不是依赖下游偶然失败。
2. `adapter_exception`、`bounded_ls_residual`、`stability_violation` 等事件 payload 是否满足 `sre_control.events.EVENT_FIELD_SCHEMA`。
3. `analysis.evidence_report` 是否严格校验 repo-relative path、bytes、sha256、JSON/JSONL/PNG 可解析性和 stack contract 非生产声明。
4. 控制中心前端是否只通过白名单恢复 share-state，动态文本是否走 text/escape 路径，错误路径是否不能注入 DOM。
5. 浏览器 smoke 的 manifest replay 错误信息是否给出 manifest、viewport、DOM path 和 regeneration command。
6. `scripts.quality_gate_counts` 是否真正保持 PR、V2 HTML、Codex quality gates、Opus packet 中的命令/计数同步。

## 边界

- 当前开放风险仍以 `docs/codex-review/OPEN_RISKS.md` 为准：synthetic evidence boundary 不能被写成生产证明。
- 本仓库是公开材料研究复现，不代表 SpaceX 官方实现。
- `analysis.run_all`、`scripts.quality_gate_counts` 和 evidence manifest 命令可能刷新产物时间或图像；复跑后先判断是否是生成器输出差异。
- 旧 `docs/opus-review/v1.0/` 和 `claude-review/docs/v2026-05-26/` 是历史输入，不是当前 open-risk ledger。
- 浏览器 smoke 的三类生成模式不要并行运行；系统浏览器可能共享临时 profile。

## 交付判定

本轮交付目标是让 Opus 能快速复审，而不是合并到主干。复审应能做到：按提交分组定位代码和证据、用固定命令重放证据链、从当前风险台账判断是否仍有 blocker、把历史 findings 与当前代码/测试/产物对应起来。
