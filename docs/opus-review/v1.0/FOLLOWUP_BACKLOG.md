# 后续 Backlog 建议 · v1.0

> Historical subreport from a prior Opus review packet; it is not the current handoff.
> Opus review should start from `docs/opus-review/HANDOFF.md`, then verify
> live status in `wiki/review-backlog.md`,
> `docs/codex-review/OPEN_RISKS.md`, and
> `docs/codex-review/QUALITY_GATES.md`.

Opus 评审给出的下一轮 codex 处理建议，按优先级排序。每条都包含：动机、变更面、验证方式、风险。

## P1 · 必做（阻止后续可维护性塌方）

### B1 · 拆分 `analysis/evidence_report.py`

- **动机**：1662 行单文件，13 类函数职责，未来新增研究即不可控。
- **变更面**：见 v1.0 DEEP_REVIEW §6.1 建议结构（7-8 个子模块）。
- **验证**：全套测试 (`python -m pytest tests`) 与 `python -m analysis.evidence_report` 全绿。
- **风险**：纯 refactor，单测可逐步迁移；先确保 main smoke 测试存在。
- **预计工时**：~1.5 天。

### B2 · 拆分 `tests/test_evidence_manifest.py`

- **动机**：90 KB 单文件，难以快速定位 + 难以批量调整。
- **变更面**：拆为 6 个子文件（manifest_shape / s10 / s11 / s12 / contract / artifact_identity）。
- **验证**：`pytest -q` 计数仍 249（或按拆分后细分计数）；CI 时间不上升。
- **风险**：纯组织调整；fixture 可放 `tests/conftest.py`。
- **预计工时**：~半天。

## P2 · 建议（提升健壮性 + 一致性）

### B3 · `WeightedLoadBalancer.allocate` 包装 solver 异常

- **动机**：`scipy.optimize.lsq_linear` 在病态输入下可能抛 `ValueError`/`RuntimeError`，未被 stack 的 `except RecoverableControlError` 捕获。
- **变更面**：`sre_control/weighted_balancer.py` 在 `allocate` 内 try/except 包装为 `RecoverableControlError`；可同时在 `tests/test_sre_control.py` 加一个病态输入用例。
- **验证**：新增测试触发 + 通过 stack 的 fallback 路径。
- **风险**：行为变更，但属于"补完降级路径"，与 I-5 不变式一致。
- **预计工时**：~2 小时。

### B4 · `adapter_exception` 字段语义整理

- **动机**：`cause_type` 与 `fault_family` 在当前 `_adapter_exception_event` 实现下永远相等，未来扩展时语义会混淆。
- **变更面**：
  - 选项 A：删除 `fault_family`，只保留 `adapter_family` + `cause_type`。
  - 选项 B：保留三者但写清各自语义（stage 家族 vs 故障类别 vs 异常根因二分），并更新 `docs/EVENT_SCHEMA.md`。
- **验证**：`tests/test_event_schema.py` 与 `tests/test_contracts.py` 全绿。
- **风险**：选项 A 是破坏性的（trace artifact 字段集变化），需要清理 manifest test 期望；选项 B 仅文档变更。
- **预计工时**：选项 A ~半天；选项 B ~1 小时。

### B5 · `quality_gate_counts.py` 模板化

- **动机**：硬编码 `replace_once` 调用，任一文档措辞变化即 `RuntimeError`。
- **变更面**：把 (path, regex, replacement template) 抽到一份 JSON/YAML 配置，运行时遍历执行；`RuntimeError` 报错带 file path。
- **验证**：`tests/test_quality_gate_counts.py` 全绿；手工 sanity 跑一次更新看 7 个文档都被正确同步。
- **风险**：低 — 工具内部 refactor。
- **预计工时**：~半天。

### B6 · EKF 默认协方差地板

- **动机**：`covariance_eigenvalue_floor` 默认为 0 易被遗忘 → 长跑后 P 塌缩 → 沉默失败。
- **变更面**：`starship/ekf.py` 默认改为 `1e-12`，并在 `tests/test_ekf.py` 加一个"长跑低噪声 1000 次更新"用例。
- **验证**：新测试通过；既有 EKF 测试不退化（因为 1e-12 远小于现有 Q）。
- **风险**：现有用户若依赖"P 自由下降到机器精度"的特定行为会被影响，需在 CHANGELOG 标注。
- **预计工时**：~2 小时。

## P3 · 可选（长期纪律 + 边缘风险）

### B7 · 复合事件 fixture 工厂

- **动机**：当前 `analysis/fixtures/sre_replay.jsonl` 是冻结的 19 行 JSONL，新增 incident 类型需要并行改 fixture + 测试，硬编码风险高。
- **变更面**：保留 fixture 文件作为冻结 baseline；新增 `analysis/fixtures/build_replay.py` 把 incident 描述（dataclass list）渲染为 JSONL。
- **验证**：`build_replay.py` 产出对当前 fixture 字节相同（diff 为空）。
- **风险**：低；纯辅助工具。
- **预计工时**：~半天。

### B8 · `LLM-WIKI/` 归属确认

- **动机**：当前 untracked，归属不清。
- **变更面**：
  - 若是项目知识库 → 加入 git + 写 README + 加入 `tests/test_synthetic_evidence_boundaries.py` lint 集合；
  - 若是工作区 → 加入 `.gitignore`。
- **验证**：`git status` 不再显示 untracked。
- **风险**：信息缺失 → 需要先与项目方确认归属。
- **预计工时**：~10 分钟（确认后）。

### B9 · 发布管线（仅当开始发布版本制品时）

- **动机**：codex 自评已识别为下一步候选；目前 `__version__` 与 spec 版本已被 `test_release_hygiene.py` 守护。
- **变更面**：建议 GitHub Actions / 本地 release script：
  - 在 tag 推送时自动 build wheel + run quality gates + 上传 artifact；
  - 更新 CHANGELOG（基于 conventional commits）。
- **验证**：tag 后 release 流水线绿。
- **风险**：仅当真的需要分发时再做，否则属过度工程。
- **预计工时**：~1-2 天。

## 持续纪律项

### D1 · 评审包按版本叠加
- `docs/codex-review/` 保留为历史；
- `docs/opus-review/v1.0/` 为本轮；
- 后续 codex 新一轮交付后，新一轮评审落 `docs/opus-review/v1.1/` 或 `v2.0/`；
- 不覆盖、不删除历史评审，保留迭代轨迹。

### D2 · `wiki/review-backlog.md` 与 `OPEN_RISKS.md` 仍为权威
- 本评审包是 historical advisory；
- 任何"已完成 vs 未完成"的状态以 wiki 与 OPEN_RISKS 为准；
- 本评审包提到的建议项若被采纳，应同步反映在 `wiki/review-backlog.md` 的 "Active Research Landing Candidates"。

### D3 · 评审完触发动作
- 中文 commit；
- push 到 `spacex-session`；
- 在 PR 描述里链接 `docs/opus-review/v1.0/DEEP_REVIEW_REPORT.md`。

---

**Opus 4.7 / 2026-05-25**
