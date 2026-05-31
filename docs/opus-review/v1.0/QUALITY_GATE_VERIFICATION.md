# 质量门复跑验证 · v1.0

> Historical subreport from a prior Opus review packet; it is not the current handoff.
> Opus review should start from `docs/opus-review/HANDOFF.md`, then verify
> live status in `wiki/review-backlog.md`,
> `docs/codex-review/OPEN_RISKS.md`, and
> `docs/codex-review/QUALITY_GATES.md`.

本文档记录 Opus 评审在本地 Windows 工作区对 codex 声明的全部质量门做的复跑，用于证明评审结论建立在可重现的事实之上而非纸面声明。

## 环境

| 项 | 值 |
|---|---|
| 工作目录 | `D:\workspace\SRE-LLM\spacex` |
| 分支 | `spacex-session` |
| HEAD | `8d8e064` |
| OS | Windows 11 Pro 22631 |
| Shell | bash (Git for Windows) |
| Python | 工作区默认解释器（同 codex） |

## 1. pytest 测试套件

```bash
$ python -m pytest tests --tb=no
...
249 passed in 133.15s (0:02:13)
```

**结果**：全绿。249 个测试与 codex 文档声明的 249 一致，无漂移。

## 2. analysis 套件

```bash
$ python -m analysis.run_all
...
All 12 studies finished in 3.45s. Artifacts in analysis/artifacts/.
```

**结果**：12 个研究全部完成，耗时 ~3.5s（与 PR-REQUIREMENTS 的"~3 s"一致）。

部分关键数字回顾（来自 `analysis/artifacts/SUMMARY.txt`）：

| 研究 | 关键 before/after |
|---|---|
| §1 Lossless | `pos_err 148.3 → 2.125e-06 (x1.43e-08)` |
| §4 Cone | `cone_violations 0.974 → 0` |
| §5 EKF | `vel_rmse 629.4 → 9.374`; `fiducial_updates=31`; `near_field_pos_rmse=2.52` |
| §8 Allocation | `saturation_violation_pct 33.75 → 0` |
| §9 SRE Stack | `slo_violation_pct 25 → 10` |
| §10 Failure Trace | `0 events → 16 events / 4 kinds`; `event_visible_fraction=1.0`; `background_event_fraction=0.0` |
| §11 Catch/SRE Wrapper | `capacity_violation_pct 66.67 → 0`; `event_visible_fraction=1.0` |
| §12 SRE Replay | `expected_event_visible_fraction=1.0`; `multi_signal_window_coverage=1.0`; 19 ticks |

## 3. 事件证据 manifest

```bash
$ python -m analysis.evidence_manifest
...
wrote D:\workspace\SRE-LLM\spacex\analysis\artifacts\event_evidence_manifest.json
```

**结果**：manifest 文件正常写入。

## 4. 事件证据 reporter

```bash
$ python -m analysis.evidence_report
evidence_scope synthetic_sre_event_evidence
s10_failure_trace section=10 events=16
s11_catch_sre_wrapper section=11 visible=1.0
s12_sre_replay section=12 events=11.0 ticks=19
artifact_check ok studies=3 files=8
```

**结果**：3 个 study + 1 个 contract，8 个 artifact 文件全部通过 shape / path / SHA-256 / size / parse / schema / count / scope / stage-route 验证。退出码 0。

## 5. 与 codex 自评对齐情况

| Codex 声明 | Opus 实测 | 一致 |
|---|---|---|
| pytest 249 passed | 249 passed | ✅ |
| 12 studies finish | 12 studies finished | ✅ |
| evidence_report studies=3 files=8 | studies=3 files=8 | ✅ |
| S10 event_visible_fraction=1.0 | 1.0 | ✅ |
| S10 replica_bound_active expected_kind_fraction=1.0 | 1.0 | ✅ |
| S11 capacity_violation_pct 66.67→0 | 一致 | ✅ |
| S11 event_visible_fraction=1.0 | 1.0 | ✅ |
| S12 expected_event_visible_fraction=1.0 | 1.0 | ✅ |
| S12 multi_signal_window_coverage=1.0 | 1.0 | ✅ |
| S12 ticks=19 | 19 | ✅ |

无漂移。

## 6. 复跑结论

- 全部质量门可以在 Windows 工作区一次性通过。
- 关键指标数字与 codex 文档无漂移。
- artifact 字节身份机制有效（manifest 重生成后 evidence_report 一次通过，说明 SHA-256/size 自洽）。

---

**Opus 4.7 / 2026-05-25**
