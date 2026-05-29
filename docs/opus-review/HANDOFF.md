# Opus 评审交接

日期: 2026-05-29
仓库: `D:\workspace\SRE-LLM\spacex`
分支: `spacex-session`
范围: 给 Opus 重新介入评审的首读 handoff, 按当前工作区 git 内容域梳理。

当前 HEAD 和 ahead 数不在本文里钉死到某个 SHA 或固定数字。Opus 介入时请以
`git status --short --branch`、`git log -1 --oneline` 和
`git log --reverse --oneline origin/spacex-session..HEAD` 为准。本文只按内容域梳理近期
提交序列, 不替代现场 git 输出。

本文只承担评审交接职责: 解释入口、提交分组、证据资产和复核命令。它不新增运行时语义,
也不把 synthetic scenario evidence 升级为线上安全结论。本仓库仍是公开材料研究复现,
不代表 SpaceX 官方实现。

## 当前权威锚点

Opus 先按当前 live ledger 判断状态, 再回看历史评审包。

1. `docs/codex-review/OPEN_RISKS.md`: 当前开放风险入口。现在仍保留的核心风险是 R1
   synthetic evidence boundary, 即新摘要和外部转述不能把场景内结果泛化。
2. `wiki/review-backlog.md`: 跨会话完成状态和证据索引, 用来判断历史 finding 是否已经被
   代码、测试或文档边界收敛。
3. `docs/opus-review/OPUS_REVIEW_PACKET.md`: Opus 当前工程包, 用于命令复跑和 finding
   对照, 但不能覆盖上面两个 live ledger。
4. `claude-review/docs/v2026-05-28/README.md` 和
   `claude-review/docs/v2026-05-26/README.md`: 外部历史评审上下文, 只作为复核输入。

这条顺序已由 `scripts.review_authority_lint` 约束, 并接入 `scripts.quality_gate_counts`。

## 当前基线

- 工作区: 以 `git status --short --branch` 为准; 本轮 handoff 更新时, 本地分支已包含
  Opus/Codex 评审入口硬化、SRE runtime 输入边界加固和质量门同步提交。
- 最新提交: 不在本文中写死具体 SHA; 用 `git log -1 --oneline` 现场确认。
- 当前文档同步目标中的 pytest 数量为 589; 规范输出行只在下方复核摘要中保留一次。
- 当前质量门已覆盖 review authority lint、浏览器证据 replay、包烟测、控制中心集成审计、
  三个 demo smoke 和 S10/S11/S12 证据链。
- 当前唯一 live 风险仍以 `docs/codex-review/OPEN_RISKS.md` 为准: 场景内证据不能被写成
  泛化结论或官方算法说明。

## Opus 首读顺序

1. `docs/opus-review/HANDOFF.md`: 这份交接, 先拿到范围、提交分组和复核命令。
2. `docs/opus-review/README.md`: Opus 包入口和首读表, 重点看 live ledger 是否排在历史包前。
3. `docs/codex-review/OPEN_RISKS.md`: 判断是否仍有 blocker 或只剩边界提醒。
4. `wiki/review-backlog.md`: 对照完成状态、证据索引和下一步候选。
5. `docs/opus-review/OPUS_REVIEW_PACKET.md`: 复核命令、证据资产和历史 finding 对照。
6. `docs/EVENT_EVIDENCE_MANIFEST.md` 与 `docs/STACK_DATA_CONTRACT.md`: 机器可验的证据和
   stack 边界。
7. `docs/CONTROL_CENTER_HANDOFF.md`: 控制中心浏览器证据、本地暴露边界和前端契约。
8. `claude-review/docs/v2026-05-28/README.md`: 上一轮外部评审上下文。

## 按内容域拆分的提交索引

以下按 `origin/spacex-session..HEAD` 的近期提交内容域整理。每行给出 Opus 建议优先看的复核点;
完整顺序和是否又有新增提交以 `git log --reverse --oneline origin/spacex-session..HEAD` 为准。

### A. 历史审计包和 Codex/Claude 台账基线

| Commit | 中文说明 | Opus 复核点 |
| --- | --- | --- |
| `72e960c` | 落地 Claude development audit 包, 增加审计证据、报告、计划和初始 schema/contract 测试。 | 历史审计材料是否被标成上下文, 不应覆盖当前 live ledger。 |
| `93e85ab` | 收尾审计包状态, 把完成/待办口径改成可交接版本。 | 状态词是否和实际代码、测试结果一致。 |
| `6000034` | 澄清历史事件计数, 避免旧统计被误读为当前生成结果。 | 旧数字是否被降级为历史记录。 |
| `2fc5b5e` | 对齐审计文档里的质量门计数。 | 计数是否由脚本同步, 而不是散落手写。 |
| `0785d9e` | 刷新审计后的 `analysis/artifacts/SUMMARY.txt`。 | SUMMARY 变化是否来自生成器当前输出。 |
| `0b2292f` | 同步最终分析证据, 修正 audit completion 报告引用。 | 文档引用是否指向存在的当前产物。 |
| `5664d73` | 增加 post-commit review pass 和对应 snapshot/report。 | post-commit 结论是否只作为当时快照。 |
| `c1dc48d` | 对齐 adapter exception taxonomy 相关文档。 | runtime 事件字段和文档术语是否一致。 |
| `32913d0` | 记录 version policy 后续项。 | 版本策略是否仍只是 release hygiene, 没有伪造发布流程。 |
| `66e55d7` | 收敛 Joseph form 文档漂移, 同步推导说明和控制中心 escaping 测试。 | EKF 文档、代码和测试是否仍一致。 |

### B. 基础质量门、包烟测、发布卫生和公开边界

| Commit | 中文说明 | Opus 复核点 |
| --- | --- | --- |
| `056fd12` | 新增 `scripts.quality_gate_counts`, 自动同步 pytest count 和 canonical V2 HTML 入口。 | count target 是否覆盖 PR/V2/Codex/wiki/Opus 当前入口。 |
| `982469e` | 增加 installed-wheel package smoke gate。 | wheel 安装后 import surface 是否真实验证。 |
| `e90125c` | 加固 package smoke 质量门, 缺失命令和失败输出更明确。 | 失败时是否能定位缺口, `--check` 是否只读。 |
| `0e82c1f` | 锁定 control-center 本地暴露边界。 | 默认 bind/Host 策略是否只允许本地回环。 |
| `0ae5740` | 拆分 adapter exception cause taxonomy。 | `adapter_exception` 是否能区分 stage、fault family、fallback action 和 fallback mode。 |
| `1b23897` | 增加 synthetic evidence boundary guard。 | 公开文档是否被 lint, 是否拒绝未限定的过界表述。 |
| `8d8e064` | 增加 release hygiene 测试。 | 未发布项目是否避免误导性的 release/spec 口径。 |

### C. Opus 历史评审输入

| Commit | 中文说明 | Opus 复核点 |
| --- | --- | --- |
| `4cc2032` | 沉淀 Opus v1.0 深度评审包。 | v1.0 只作为历史 finding 来源。 |
| `31e6ba9` | 补充 Opus v1.0 第二轮行级隐患和复现实证。 | 行级 finding 是否都能映射到当前测试或台账。 |
| `925f62c` | 增加 Opus v2.0 Codex 工程包评审产出。 | F50-F60/G1 是否已转入当前 backlog 的 resolved/live 状态。 |

### D. SRE 运行时边界和数值安全收敛

| Commit | 中文说明 | Opus 复核点 |
| --- | --- | --- |
| `f679e6d` | 按 Opus 反馈收敛 SRE 控制边界: non-finite 输入、EKF/Joseph、fallback、事件 schema、稳定性和负载分配等。 | `sre_control/`, `starship/ekf.py`, `starship/stability_monitor.py` 与 `tests/test_sre_control.py`、`tests/test_contracts.py`、`tests/test_ekf.py` 是否形成回归网。 |
| `553be48` | 拒绝非法控制周期 `dt`, 避免 stack tick 在非正或非有限时间步下继续推进。 | `SREControlStack.step()` 是否在入口失败并保持 trace 状态可解释。 |
| `9b51dd9` | 收敛 autoscaler 运行时输入边界。 | `PredictiveAutoscaler.step()` 是否拒绝非有限/负值 RPS 与非法副本数, 且不污染 warm-start trace。 |
| `cc197fe` | 收敛 topology 状态积分输入边界。 | `TopologyState.step()` 是否在 mutation 前拒绝非法 dt、速度和角速度。 |
| `6e8105b` / `ecfe511` | 加固流量切换计划输入并校验安全余量。 | `FastTrafficSwitcher` 是否拒绝非法 rate、deadline、share 和 margin, terminal share 是否仍受保护。 |
| `bb90ab7` | 收敛灰度调度输入边界。 | `CanaryScheduler` 构造、proposal、observation 三类输入是否都有测试覆盖。 |
| `102fbad` | 收敛连接池规划输入边界。 | `PoolCapacityPlanner` 是否拒绝非法容量/成本/预测数据, 并保持容量缺口事件语义。 |
| `d5fd942` / `03cfa4f` | 收敛 catch adapter 输入边界并补齐 API 合同。 | `CatchLoadAdapter` 是否在进入 bounded-LS 前拒绝非法需求和 placement target, 且不越过 `starship/` 与 `sre_control/` 依赖边界。 |
| `c1b4846` | 收敛 StabilityGuard 输入边界。 | `StabilityGuard` 是否在构造阶段拒绝非法 tolerance/window/k/label, 在 step 阶段拒绝非有限 state/time, 且 `sre_error_budget_V` 只接受有限 target 和正有限 scale。 |
| `48ae7fb` | 拒绝布尔型稳定守卫计数配置。 | `k_violations` 和 `window` 是否显式排除 `True/False`, 避免 Python bool-as-int 语义把布尔值当作窗口计数。 |

### E. 事件证据链、S10/S11/S12 和分析报告

| Commit | 中文说明 | Opus 复核点 |
| --- | --- | --- |
| `fa73ac0` | 建立 S10/S11/S12 事件证据清单、manifest、report、fixed replay fixture 和 stack contract 校验。 | repo-relative path、SHA/bytes、strict JSON/JSONL/PNG parse、事件 schema 校验是否都在 report 中失败可见。 |
| `b6ee79b` | 刷新分析和浏览器审计产物。 | 产物是否由当前命令重放生成, manifest byte identity 是否匹配。 |
| `9b70909` | 稳定控制中心 DOM 证据哈希, 降低 Windows 行尾/HTML 大块漂移。 | manifest sha/bytes 是否不再因不必要 HTML snapshot 漂移。 |
| `3fb5464` | 让控制中心集成审计可复现, 避免 `generated_at` 污染。 | 连续运行 audit 是否保持稳定输出。 |
| `1da8e3f` | 刷新 S11 catch/SRE wrapper 图像。 | 图像是否和当前生成器输出一致。 |

### F. 控制中心前端契约和本地浏览器证据

| Commit | 中文说明 | Opus 复核点 |
| --- | --- | --- |
| `64b8dd9` | 加固 control-center 前端契约、本地服务暴露边界、浏览器 smoke 和 integration audit。 | share-state 白名单、动态文本 escaping、normal/backend_error/frontend_error 三类 manifest replay 是否都被测试和质量门覆盖。 |

### G. 质量门扩展和命令同步

| Commit | 中文说明 | Opus 复核点 |
| --- | --- | --- |
| `d00dc8b` | 扩展评审质量门和包烟测, 将 browser/package/integration 等命令纳入同步。 | 必跑命令是否同时出现在 PR/V2/Codex/Opus/wiki 文档。 |
| `3198d8e` | 让 Opus handoff 中的 pytest count 进入 `QUALITY_GATE_TARGETS`。 | 修改测试数后 handoff 是否会被同一脚本更新。 |
| `b5c950d` | 将 full pytest 和 collect-only 质量门 timeout 提高到 300 秒。 | Opus 复跑机器抖动是否有足够余量。 |
| `a8444fa` | 同步完整质量门 477 count。 | 旧 count 是否只通过脚本写入。 |
| `3e062d1` | 同步质量门 481 count。 | 新增 authority-order 测试后的 count 是否全入口一致。 |
| `934e650` | 同步质量门 483 count。 | 抽象 lint 后的 count 是否全入口一致。 |
| `014df0a` | 将 `scripts.review_authority_lint` 接入质量门命令集合。 | 当前 ledger 优先顺序是否成为必跑 gate。 |
| `896a333` | 同步质量门 485 count。 | gate 增量后所有文档 target 是否一致。 |
| `b6073c8` | 扩展 live 评审台账命令校验, 覆盖 handoff 和 wiki backlog。 | `QUALITY_GATE_COMMAND_DOCS` 是否包含 live ledger。 |
| `0a0252f` | 固化 Opus README 权威顺序, 支持 README 相对路径 alias。 | Opus README 的首读表是否和 live ledger 顺序一致。 |
| `dd3d2a7` / `71b2c0a` / `cdbe01c` / `0c8f624` / `a61c446` / `3c54105` / `94ddb83` / `20dbb59` | 伴随运行时输入边界加固持续同步质量门计数。 | 每次新增回归测试后, PR/V2/Codex/Opus/wiki 的 pytest count 是否由 `scripts.quality_gate_counts` 同步。 |
| 本轮质量门同步 | 将 StabilityGuard 新增测试后的质量门目标同步到 589。 | Opus 介入时应重新运行 `python -u -m scripts.quality_gate_counts` 和只读 `--check --skip-expensive`。 |

### H. Opus 交接、live ledger 和 authority-order 硬化

| Commit | 中文说明 | Opus 复核点 |
| --- | --- | --- |
| `8fd9b84` | 同步 Opus/Codex 评审包和证据边界台账, 新增 `OPUS_REVIEW_PACKET.md`。 | 当前风险、历史 finding 和证据资产是否没有互相冲突。 |
| `bf63c43` | 增加 Opus 复审 handoff 并同步质量门计数。 | handoff 是否列出复核命令、证据资产和边界。 |
| `7a99411` | 中文化 Opus 复审交接入口。 | 中文入口是否方便 Opus 直接阅读。 |
| `77540c3` | 隔离 Section 11 测试产物写入到 pytest `tmp_path`。 | 全量 pytest 后 canonical S11 图像是否不被测试污染。 |
| `9b0c88d` | 将 Opus handoff/README 纳入 evidence-boundary lint。 | 新交接文案是否会被过界表述测试拦截。 |
| `52b629a` | 补齐 handoff 中的 review hardening 提交。 | handoff 是否覆盖 S11 隔离、lint/count sync、timeout 余量。 |
| `9b050e5` | 在 wiki backlog 记录 Opus 入口硬化台账。 | 长期 ledger 是否能追踪这轮入口加固。 |
| `50ac77b` | 强化复审首读交接入口和 Opus README。 | 首读顺序、边界和命令入口是否明确。 |
| `fd39d89` | 扩展中文 evidence-boundary lint。 | 中文评审文案里的 synthetic evidence 过界是否可被测试发现。 |
| `41dcc01` | 固化 Opus handoff 的当前 ledger 优先顺序。 | `OPEN_RISKS` 和 `review-backlog` 是否排在历史 packet 前。 |
| `cc2008a` | 固化 wiki 推荐入口的当前 ledger 优先顺序。 | wiki 当前入口是否不会先导向历史包。 |
| `f992531` | 抽象 review authority lint, 统一入口顺序检查。 | 新增评审入口时是否只需扩展一个 lint 配置。 |
| `987a280` | 梳理当前评审交接稿。 | handoff 是否按内容域说明 git 进展, 而不是只列命令。 |
| `a2722de` / `38cc4fe` | 覆盖 Codex 和 Opus 评审入口权威顺序。 | README、packet、handoff 的 current ledger 优先级是否被测试固定。 |

## 按内容域复核路径

1. **入口/台账一致性**: 对照 `docs/opus-review/README.md`、本文件、
   `docs/codex-review/OPEN_RISKS.md`、`wiki/review-backlog.md` 和
   `scripts/review_authority_lint.py`。重点确认当前 ledger 先于历史 packet。
2. **质量门可复跑性**: 从 `scripts/quality_gate_counts.py` 的
   `CURRENT_QUALITY_GATE_COMMANDS`、`QUALITY_GATE_COMMAND_DOCS`、`QUALITY_GATE_TARGETS` 开始,
   核对 `tests/test_quality_gate_counts.py` 对命令存在性、manifest-report 顺序、只读 `--check`、
   Opus handoff count sync 的覆盖。
3. **证据边界与文案 lint**: 从 `scripts/evidence_boundary_lint.py` 和
   `tests/test_synthetic_evidence_boundaries.py` 开始, 核对 README、PR、wiki、V2、Codex、Opus
   review 入口是否都在 lint 面内。
4. **机器证据链**: 从 `analysis.evidence_manifest`、`analysis.evidence_report`、
   `docs/EVENT_EVIDENCE_MANIFEST.md`、`docs/STACK_DATA_CONTRACT.md` 开始, 核对 repo-relative
   path、SHA-256/bytes、strict JSON/JSONL/PNG parse、runtime event schema 和 stack contract。
5. **控制中心浏览器证据**: 从 `scripts.control_center_browser_smoke`、
   `analysis/artifacts/control-center-browser-evidence-report.json`、`docs/CONTROL_CENTER_HANDOFF.md`
   开始, 核对 normal/backend_error/frontend_error 三类 replay 和 DOM/contract 错误信息。
6. **运行时 hardening 抽查**: 从 `sre_control/`、`starship/ekf.py`、
   `starship/stability_monitor.py`、`tests/test_sre_control.py`、`tests/test_contracts.py`、
   `tests/test_ekf.py` 开始, 抽查 F50-F81 与 v1.0 P0/P1 finding 的回归测试是否还在。

## 复核命令

建议 Opus 从干净工作区或清晰暂存范围运行。下面命令同时也是当前质量门文档必须保留的命令集合。

```powershell
python -m pytest tests -q
python -u -m scripts.quality_gate_counts
python -m scripts.quality_gate_counts --check --skip-expensive
python -m analysis.s10_failure_trace
python -m analysis.run_all
python -m analysis.evidence_manifest
python -m analysis.evidence_report
python -m scripts.control_center_browser_smoke --report-manifests --report-json analysis/artifacts/control-center-browser-evidence-report.json
python -m scripts.package_smoke
python -m scripts.control_center_integration_audit
python -m scripts.review_authority_lint
python -m examples.demo_sre_loop
python -m examples.demo_powered_descent
python -m examples.demo_catch_phase
```

当前文档同步目标中的关键输出摘要应包含:

```text
quality gate pytest count: 594
artifact_check ok studies=3 files=8
manifest_replay=normal+backend_error+frontend_error
control-center integration audit ok
review authority order ok
```

浏览器证据命令的摘要还应包含 normal desktop+mobile、backend contract error、frontend contract
error 三类 replay。若 DOM hash 或 bytes 变化, 先判断是否是当前生成器输出差异, 不要直接当成
源码回归。

## 证据资产

机器可读重点:

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

视觉和 HTML 重点:

- `analysis/artifacts/s10_event_density.png`
- `analysis/artifacts/s11_catch_sre_wrapper.png`
- `analysis/artifacts/s09_sre_stack.png`
- `docs/V2_Knowledge/knowledge-base.html`

## 建议审查问题

1. SRE runtime guard 是否在入口拒绝 non-finite 值, 而不是依赖下游偶然失败。
2. `adapter_exception`、`bounded_ls_residual`、`stability_violation` 等事件 payload 是否满足
   `sre_control.events.EVENT_FIELD_SCHEMA`。
3. `analysis.evidence_report` 是否严格校验 repo-relative path、bytes、sha256、JSON/JSONL/PNG
   可解析性和 stack contract 边界。
4. control-center 前端是否只通过白名单恢复 share-state, 动态文本是否走 text/escape 路径,
   错误路径是否不能注入 DOM。
5. 浏览器 smoke 的 manifest replay 错误信息是否给出 manifest、viewport、DOM path 和 regeneration
   command。
6. `scripts.quality_gate_counts` 是否真正保持 PR、V2 HTML、Codex quality gates、Opus packet、
   Opus handoff、wiki ledger 中的命令和计数同步。
7. `scripts.review_authority_lint` 是否覆盖所有当前评审入口, 且当前 ledger 永远先于历史 packet。

## 边界

- 当前开放风险以 `docs/codex-review/OPEN_RISKS.md` 为准。场景内 synthetic evidence 不能被写成
  泛化结论。
- 本仓库是公开材料研究复现, 不代表 SpaceX 官方实现。
- `analysis.run_all`、`scripts.quality_gate_counts` 和 evidence manifest 命令可能刷新产物时间、
  图像或摘要。复跑后先判断差异是否来自当前生成器输出。
- `docs/opus-review/v1.0/`、`claude-review/docs/v2026-05-26/`、
  `claude-review/docs/v2026-05-28/` 是历史输入, 不是当前 open-risk ledger。
- 浏览器 smoke 的三类生成模式不要并行运行; 系统浏览器可能共享临时 profile。

## 交付判定

本轮 handoff 的目标是让 Opus 快速复审当前工作区, 不是合并到主干。Opus 应能做到:

- 按内容域定位代码、测试、证据和文档。
- 用固定命令重放证据链。
- 从当前风险台账判断是否仍有 blocker。
- 把历史 finding 与当前代码、测试、产物对应起来。
- 发现新问题时, 优先写成可复现 finding, 再进入下一轮小步修复。
