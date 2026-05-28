# 02 — 证据链审计

## 审计对象

本轮重点审计以下证据链：

1. `analysis.evidence_manifest` / `analysis.evidence_report`
2. `analysis.run_all`
3. `scripts.control_center_browser_smoke`
4. `scripts.package_smoke`
5. `scripts.control_center_integration_audit`
6. `scripts.quality_gate_counts`
7. `docs/codex-review/QUALITY_GATES.md` 与 `docs/opus-review/OPUS_REVIEW_PACKET.md` 的质量门声明

## 结论

S10/S11/S12 event manifest 当前可通过：

```text
artifact_check ok studies=3 files=8
```

但这只覆盖 `event_evidence_manifest.json` 所引用的事件证据，不覆盖 control-center browser evidence 的当前性，也不证明 package smoke / integration audit / quality_gate_counts 当前可运行。

## 证据链断点

### 1. browser evidence stale 与断言契约漂移

`quality_gate_counts` 失败证明 saved browser manifest 与当前 `_assert_dumped_dom()` 已不一致：

```text
AssertionError: browser DOM dump missing: ['safety-budget-list', 'data-budget-focus']
```

这意味着：

- saved HTML/PNG/hash 是自洽的，不代表它仍满足当前 browser smoke 契约。
- package smoke replay saved manifest 的价值是 artifact integrity，不是 current frontend behavior。
- 如果 dashboard DOM 新增关键元素，必须重新运行 browser smoke 并更新 manifest/report。

### 2. browser source manifest path 不可移植

`analysis/artifacts/control-center-browser-evidence-report.json` 的 `manifest_paths` 是 repo-relative：

```json
"normal": "analysis/artifacts/control-center-browser-smoke-manifest.json"
```

但 source manifest 内 artifact records 是绝对路径：

```json
"path": "D:\\workspace\\SRE-LLM\\spacex\\analysis\\artifacts\\control-center-browser-smoke-desktop.html"
```

因此工程包对外移交后存在两层证据：

- report 层看起来可移植；
- source manifest 层绑定生成机路径。

建议统一为 repo-relative，且 verifier 对 `..` 和 absolute path fail。

### 3. JSON strictness 不足

`analysis/evidence_manifest.py:35-45` 与 browser/integration audit writers 未设置 `allow_nan=False`。本轮 F63 已实测 trace 可写出：

```json
{"x": [NaN], "signals": [{"residual": NaN}]}
```

严格证据链应满足：

- writer 不允许写出 NaN/Infinity；
- reader 不允许读取 NaN/Infinity；
- validator 报错信息明确指出字段路径。

否则 Python 内部自洽不等于跨工具可读。

### 4. `run_all(artifacts_dir=...)` 隔离语义破裂

`analysis/run_all.py` 接收 `artifacts_dir`，但 study 调用固定为 `mod.main()`。复现实测：

```text
custom_summary_exists= True
custom_trace_exists= False
default_trace_exists= True
custom_dir_files= ['SUMMARY.txt']
```

这会制造“SUMMARY 在隔离目录，artifact 仍在默认目录”的证据错配。正式审计包如果使用临时目录复跑，会误以为产物隔离完成。

### 5. 质量门命令集与文档不一致

`docs/codex-review/QUALITY_GATES.md` Required Commands 包含 browser smoke report 和 package smoke，但 `scripts/quality_gate_counts.py:49-54` 当前命令集不含两者。

这造成：

- `quality_gate_counts` 校验的“质量门命令漂移”范围小于文档声明。
- OPUS packet 缺少 browser smoke/package smoke 不会被判 drift。
- 文档可继续声称 Required Commands，而自动校验不真正覆盖它们。

## 建议的证据链分层

| 层级 | 目标 | 必须实时重跑 | 可 replay |
|---|---|---|---|
| Unit/integration tests | 当前代码行为 | pytest | 不适用 |
| S10/S11/S12 event evidence | 当前研究事件证据 | `analysis.evidence_manifest` 前置生成 | `analysis.evidence_report` |
| Browser normal path | 当前 frontend/backend 合同 | browser smoke normal | manifest hash integrity |
| Browser error paths | 当前错误渲染合同 | backend error + frontend error smoke | manifest hash integrity |
| Package smoke | wheel/import + saved evidence integrity | wheel build/import | saved manifest replay |
| Integration audit | 当前 backend hash + report summary | normal API snapshot | error manifests replay |

文档必须把“实时重跑”和“saved replay”分开写，不应统称为 current proof。

## 合格的最终质量门顺序

建议正式合入前按以下顺序执行并写入日志：

```bash
python -m pytest tests -q
python -m analysis.s10_failure_trace
python -m analysis.run_all
python -m analysis.evidence_manifest
python -m analysis.evidence_report
python -m scripts.control_center_browser_smoke --report-manifests --report-json analysis/artifacts/control-center-browser-evidence-report.json
python -m scripts.package_smoke
python -m scripts.control_center_integration_audit
python -m examples.demo_sre_loop
python -m examples.demo_powered_descent
python -m examples.demo_catch_phase
python -u -m scripts.quality_gate_counts
```

并要求：

- browser manifest 内 path repo-relative；
- all JSON writers `allow_nan=False`；
- `run_all` summary 指向的 artifact 与同一轮生成目录一致；
- `quality_gate_counts` 的 command presence 校验覆盖上面完整命令。
