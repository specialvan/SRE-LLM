# 重跑命令实测输出 — 2026-05-26

> 本文件记录 Opus v2.0 评审在本机重跑 `OPUS_REVIEW_PACKET.md` 第 1 / 5 节
> 所列命令的实测输出，与文档声明逐条比对。

---

## 环境

- 主机平台：Windows 11 Pro，git bash
- Python：项目自带 venv
- 工作目录：`D:\workspace\SRE-LLM\spacex`
- 分支：`spacex-session`
- 日期：2026-05-26

---

## 命令实测

### 1) `python -m pytest tests -q`

```text
........................................................................ [ 26%]
........................................................................ [ 52%]
........................................................................ [ 78%]
............................................................             [100%]
276 passed in 152.50s (0:02:32)
```

**比对**：packet 声明 `276 passed`，完全一致。✅

---

### 2) `python -m analysis.run_all`

末尾输出节选：

```text
=== §12 SRE replay fixture ===
  background_event_fraction  before=0  after=0  (ratio=undefined; zero baseline)
  event_count_total         before=0  after=11  (ratio=undefined; zero baseline)
  expected_event_visible_fraction  before=0  after=1  (ratio=undefined; zero baseline)
  max_incident_window_ticks  before=0  after=3  (ratio=undefined; zero baseline)
  max_recovery_ticks        before=0  after=1  (ratio=undefined; zero baseline)
  multi_signal_window_coverage  before=0  after=1  (ratio=undefined; zero baseline)
    (elapsed 0.03s)

All 12 studies finished in 4.02s. Artifacts in analysis/artifacts/.
```

**比对**：packet 声明 "12 studies finished"，符合。✅

`ratio=undefined; zero baseline` 渲染与 v1.0 修复一致（来自
`analysis/_common.py:66-71`）。

---

### 3) `python -m analysis.evidence_manifest`

输出末行：

```text
wrote D:\workspace\SRE-LLM\spacex\analysis\artifacts\event_evidence_manifest.json
```

**比对**：packet 声明 "wrote event_evidence_manifest.json"，符合。✅

---

### 4) `python -m analysis.evidence_report`

```text
evidence_scope synthetic_sre_event_evidence
s10_failure_trace section=10 events=16
s11_catch_sre_wrapper section=11 visible=1.0
s12_sre_replay section=12 events=11.0 ticks=19
artifact_check ok studies=3 files=8
```

**比对**：packet 第 5 节"Manifest sanity outputs to expect"完全匹配。✅

**注意**：本命令必须紧随第 3) 步运行；如果在第 3) 步与本步之间执行了
`run_all` 重新渲染 PNG / JSONL，会触发 `artifact_identity_mismatch`。
详见本评审 `04-evidence-manifest-audit.md` G1。

---

### 5) `python -u -m scripts.quality_gate_counts`

```text
quality gate pytest count: 276
```

**比对**：packet 第 1 节声明 `quality gate pytest count: 276`，完全一致。✅

---

## 完整命令链复跑顺序

为避免 G1 process-trap，下述顺序是 reviewer 应当使用的标准复证序列：

```bash
# A) 重生制品（如果 analysis/* 文件被改动）
python -m analysis.run_all

# B) 重生 manifest，让 SHA-256 / 字节大小与 A) 产出对齐
python -m analysis.evidence_manifest

# C) 运行报告 CLI，验证 manifest + 制品对齐
python -m analysis.evidence_report

# D) 校验 gate 文档没有漂移
python -u -m scripts.quality_gate_counts

# E) 测试 reg
python -m pytest tests -q
```

期望所有命令 exit 0，且 C) 输出末行恰为
`artifact_check ok studies=3 files=8`。

---

## 评审小贴士（避免常见复跑陷阱）

1. 不要在 B) 与 C) 之间再次跑 A)（会让 PNG 重写但 manifest 没更新）。
2. matplotlib 后端 / 版本变化会让 PNG byte-level 漂移；如果你在 reviewer
   机器上跑出 SHA mismatch，先在本地重新跑 A) → B) → C)，再 commit。
3. 不要单独跑 `analysis.evidence_report` 期望它能"自愈合"manifest；当前
   实现就是要求 manifest 与制品一致才放行。

---

## 与 packet 声明输出的差异

无。所有命令输出与 packet 声明在字面上一致或与其语义等价。
