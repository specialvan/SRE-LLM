# 证据制品 / Manifest / 报告 CLI 一致性审计

> Historical subreport from a prior Opus review packet; it is not the current handoff.
> Opus review should start from `docs/opus-review/HANDOFF.md`, then verify
> live status in `wiki/review-backlog.md`,
> `docs/codex-review/OPEN_RISKS.md`, and
> `docs/codex-review/QUALITY_GATES.md`.

> 评审 `analysis/evidence_manifest.py` + `analysis/evidence_report.py` +
> `analysis/artifacts/event_evidence_manifest.json` + `analysis/artifacts/
> sre_stack_data_contract.json` + `docs/EVENT_EVIDENCE_MANIFEST.md` + `docs/
> STACK_DATA_CONTRACT.md` + 相关测试的契约闭环是否成立。

---

## AUDIT VERIFIED（通过项）

1. **repo-relative artifact 路径**
   - `analysis/evidence_manifest.py:48-52` `_artifact_ref` 用 `REPO_ROOT`
     strip 前缀，全部输出 POSIX 风格相对路径。
   - JSON 内容人工检查：所有 `artifact_path` / metadata key 均为 `analysis/
     artifacts/...` 形式，无绝对 `D:\` 泄漏。
   - `evidence_report.py:522-534` `_nonportable_artifact_paths` 拒绝
     "absolute path or 上跳 (..)"。

2. **markdown 文档 vs JSON parity**
   - `docs/EVENT_EVIDENCE_MANIFEST.md:39-49` 列出 3 个 study + 1 个 contract，
     evidence label / required field / artifact key 与 `_manifest_shape_errors`
     枚举完全一致。
   - `tests/test_evidence_manifest.py` 的
     `test_event_evidence_manifest_doc_matches_generated_manifest` 解析
     markdown 表与 live manifest 做集合相等。

3. **manifest top-level shape / required fields / fixed values / range / 文件
   存在性 / parseability 全部由 reviewer 强校验**
   - `evidence_report.py:139-389` `_manifest_shape_errors` 强制
     `evidence_scope == "synthetic_sre_event_evidence"`；type / fixed value /
     range 全套校验。
   - missing manifest → `invalid_manifest missing_manifest`（:1527-1532）；
     malformed JSON → 提前拦截（:1534-1539）；
     文件存在性循环（:1566-1578）；
     按扩展名分类的 parse loop（`_invalid_artifact_errors` :1351-1395）。

4. **runtime event 合法性 + contract scope + stage route + count consistency**
   - `_schema_invalid_event_errors`（:1415-1449）把每条 trace 事件喂给
     `sre_control.events.validate_event`。
   - `_contract_event_errors`（:1469-1514）按 `event_stage_routes` 把 trace 事件
     路由到 stage，对照该 stage 的 `allowed_event_kinds`。
   - `_contract_consistency_errors`（:1194-1348）强制 stage ordering 恰为
     `observe → stability → plan → guard → allocate → execute`，
     `production_claim=False`，`orchestration_model` 固定，split-ready
     boundary 名称符合契约。
   - `_consistency_errors`（:1112-1191）核对 expected vs actual line 数、
     重新计算 weighted visibility fraction、S12 reconciler 等。

5. **Quality-gate 强制**
   - `scripts/quality_gate_counts.py:15-20` `CURRENT_QUALITY_GATE_COMMANDS`
     列入 `python -m analysis.evidence_manifest` 与 `python -m
     analysis.evidence_report` 两条命令。
   - `require_quality_gate_commands`（:67-71）会在 PR-REQUIREMENTS.md 或
     V2 HTML 知识库不再列出这两条命令时 raise。

6. **stack contract scope / production_claim / stage ordering**
   - `sre_stack_data_contract.json`：
     - `evidence_scope = research_stack_data_contract`
     - `production_claim = false`
     - `orchestration_model = single_process_research_loop`
     - stages 列表恰好 `observe / stability / plan / guard / allocate / execute`
   - `docs/STACK_DATA_CONTRACT.md:33-47` 与 JSON 字段一致。
   - reviewer `evidence_report.py:1204-1218` 与 :1259-1270 拒绝任何偏离。

7. **strict JSON — 无 Infinity / NaN**
   - 3 个 JSON 制品全文 grep 无 `Infinity` / `NaN` token。
   - `_recovery_diagnostics` / `_multi_signal_window_diagnostics` 都把未恢复
     窗口 map 到 `None`（:945-946、:1006-1008）。
   - `test_evidence_report_unrecovered_window_uses_strict_json_null` 与
     multi-signal 变体用 `json.dumps(..., allow_nan=False)` 复证。

8. **无 production-claim 误导文案**
   - `s12_sre_replay.py:3, 301` 显式标 `synthetic_replay_fixture` 与
     "synthetic replay fixture, not a production trace"。
   - `SUMMARY.txt` 无 "production" token。
   - reviewer 拒绝 `production_claim != False`（:1209-1213）。

9. **zero-baseline ratio 渲染**
   - `analysis/_common.py:66-71` 在 `abs(b) <= 1e-12` 时输出 `(ratio=
     undefined; zero baseline)`，不渲染 `inf`。
   - SUMMARY.txt 第 19/26/67/80/84-89 行实际可见此渲染。

---

## AUDIT GAP（需关注）

### G1 — `s11_catch_sre_wrapper.png` 在不同 reviewer 机器上易出现 SHA / size 漂移【P2】

**现象**：

- 当前 worktree 下，`analysis/artifacts/event_evidence_manifest.json` 中
  `s11_catch_sre_wrapper.png` 的 metadata 记录的 SHA 与 byte size 与磁盘
  PNG 在某次执行后会不一致；reviewer agent 在未先跑
  `analysis.evidence_manifest` 的情况下复跑 `analysis.evidence_report`，
  得到 `artifact_identity_mismatch ... artifact_check failed studies=3
  artifact_identity=1`。
- 在主线复跑流程 `manifest → report` 顺序下不会复现，但顺序敏感性本身是
  "process trap"。
- 根因：matplotlib 在不同机器 / Python / matplotlib 版本下 PNG 元数据
  （`tIME`、`pHYs`、`tEXt`）与压缩字节会变化。即便控制了 random seed，PNG
  字节不一定 byte-identical。

**影响**：

跨机器 / 跨贡献者评审时极易出现"我本地全过了，但 reviewer 报红"的假阴性。

**建议修复**：

1. （首选）`scripts/quality_gate_counts.py` 在校验前自愈合：内部串行执行
   `analysis.evidence_manifest` 再执行 `analysis.evidence_report`，
   避免 reviewer 漏跑顺序。或在 README / packet 的 "review commands"
   段落首位用粗体声明此顺序。
2. PNG 确定化：matplotlib 写出后用 `pypng` / `Pillow` 二次写入并 strip
   `tIME` / `pHYs` / `tEXt` / `iCCP` chunks，仅保留 `IHDR` / `IDAT` / `IEND`，
   让相同输入跨平台得到字节相同 PNG。
3. 在 CI / 提交 hook 中强制 `git diff --quiet analysis/artifacts/*.json
   analysis/artifacts/*.png` 等价于"manifest 与 PNG 同步提交"。

### G2 — `analysis/artifacts/event_evidence_manifest.json` 与 PNG 制品目前未被 git track【P3】

`git status --short` 显示 `analysis/artifacts/event_evidence_manifest.json`
长期处于 `??`（untracked）状态；同样多个 PNG / JSONL 也是 `M` 状态被多次
覆盖。后果：

- 跨分支评审者无法用 `git diff base...HEAD` 看到"manifest 变化"。
- 一旦本机生成与 PR 中提交的制品不一致，review 必须依赖各机器自行复跑。

**建议修复**：

二选一：

1. 把 canonical 一对（manifest + 配套 PNG / JSONL）track 进 git，PR 模板要求
   `manifest 与 trace 同步提交`。
2. 或在 `.gitignore` 显式 ignore 制品并在 CI 上构造它们；reviewer 不再
   读"提交版"制品而是统一 reproduce。

二者择一即可，避免现状的"既不 track 也不 ignore"灰区。

### G3 — `evidence_report.py` 一致性检查多处使用浮点 `!=` 直比【P3】

`analysis/evidence_report.py:1092`、:1101、:1104、:1107、:1128-1130 等：
```python
if float(diagnostics[field]) != expected_value: ...
```
今天能通过是因为两侧都是确定性 derive 自同一数据；一旦数值流程被 refactor
（如 `dt` 改为非二进制可表示数、或 weighted 平均换实现），会随机出错。
邻近 :1094 已经用 `abs(a - b) < eps` 形式，应当统一。

**建议修复**：把这些 `!=` 改为 `abs(a - b) > 1e-9` 类容差比较，配 epsilon 注释。

### G4 — `s10_failure_trace.py` `after`-dict 临时携带 `_kinds_per_tick` 等内部字段【P3】

`analysis/s10_failure_trace.py:263-279` 返回的 dict 含 `_`-prefixed key，被
`l.323-324` strip 后才给到 banner。安全今日成立，但若未来有调用方直接消费
`after` dict 会泄漏内部字段。建议把 metrics 与 internals 拆成两个返回值。

---

## SUGGESTIONS（与 AUDIT GAP 配套但不属 finding）

1. 在 OPUS_REVIEW_PACKET.md 第 5 节"Review Commands"开头加粗强调
   "`analysis.evidence_manifest` 必须先于 `analysis.evidence_report` 执行"。
2. 把"`scripts.quality_gate_counts`"也加到 packet 的 minimum review command set
   中，避免漏跑 gate 漂移检查。
3. 给 `analysis/evidence_report.py` 加一个 `--auto-rebuild-manifest` 旗标，
   reviewer 一条命令端到端复证。
4. 当 `production_claim == True` 时直接 raise（目前是 != False 即 raise，
   语义一致但表述更明确）。

---

## 小结

证据 / manifest 层契约整体健壮，可作为 reviewer 信赖的 frozen-in-time
快照。剩余 4 项 GAP 全是 process / 跨机器一致性 / 浮点比较类问题，不构成
blocker 但建议在合入前清掉 G1（顺序 trap）。
