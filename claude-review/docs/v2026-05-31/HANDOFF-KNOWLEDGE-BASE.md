# HANDOFF 深度梳理 - Agent 评审知识库

**文档版本**: 2026-05-30  
**梳理日期**: 2026-05-31  
**目标受众**: 后续介入评审的 AI Agent  
**用途**: 提供结构化的评审知识，降低 agent 上手成本

---

## 文档概览

### 核心定位
HANDOFF.md 是 Opus 评审的**第一入口文档**，提供：
- 当前工作区状态快照
- 评审流程 runbook
- 重点评审区域指引
- 具体评审问题清单

### 文档结构
```
HANDOFF.md (295 行)
├── Git Review Scope Snapshot (L21-58)
├── Current Baseline (L98-112)
├── Reviewer Runbook (L113-135)
├── Handoff Sanity Checklist (L137-155)
├── Evidence Report Split State (L157-205)
├── Review Focus (L207-240)
├── Questions For Opus (L242-259)
└── Recommended Re-Run Commands (L261-295)
```

---

## 关键概念解析

### 1. Git Review Scope

**概念**: 当前工作区的 git 状态，包括 modified 和 untracked 文件

**关键信息**:
- **分支**: `spacex-session...origin/spacex-session [ahead 91]`
- **Modified 文件**: 大量评审文档、质量门禁脚本、证据报告模块
- **Untracked 文件**: 36 个，包括：
  - 拆分的证据报告测试（20+ 个）
  - Superpowers 计划/规格（10+ 个）
  - 拆分的控制中心测试（5 个）

**重要提醒**:
```
For any merge or external packet export, do not omit untracked split files;
the synchronized quality gates and handoff claims depend on them.
```

**Agent 行动**:
1. 运行 `git status --short --branch --untracked-files=all`
2. 确认所有 untracked 文件都在预期清单中
3. 检查是否有意外的新文件

### 2. Current Baseline

**概念**: 当前工作区的验证基线，包括测试数量和关键命令输出

**关键指标**:
- **pytest count**: 871（⚠️ 文档不一致，实际为 874）
- **证据 studies**: 3 (S10, S11, S12)
- **证据 files**: 8

**验证命令输出**:
```text
python -m pytest tests -q
871 passed  ← 应为 874

python -m analysis.evidence_report
artifact_check ok studies=3 files=8

python -m scripts.quality_gate_counts
quality gate pytest count: 871  ← 应为 874
```

**Agent 行动**:
1. 运行所有验证命令
2. 对比实际输出与文档声明
3. 标记任何不一致

### 3. Reviewer Runbook

**概念**: 4 步评审流程，从快速检查到深度审查

**流程图**:
```
Step 1 (15 min)
├── git status 检查
├── 读 HANDOFF.md
├── 读 wiki/review-backlog.md
├── 读 OPEN_RISKS.md
└── 读 QUALITY_GATES.md

Step 2 (30 min)
├── 运行 analysis.evidence_manifest
├── 运行 analysis.evidence_report
└── 检查输出片段

Step 3 (45 min)
├── 检查证据报告拆分模块
├── 检查堆栈合同路由
├── 检查适配器异常负载
├── 检查控制中心浏览器证据
└── 检查质量门禁更新器

Step 4 (15 min)
└── 评估 OPEN_RISKS.md 是否有阻塞项
```

**Agent 行动**:
1. 严格按照 4 步流程执行
2. 记录每步的发现
3. 在 Step 4 做出 PASS/BLOCK 决策

### 4. Evidence Report Split State

**概念**: 证据报告从单体拆分为 4 个职责明确的模块

**拆分架构**:
```
analysis.evidence_report (thin orchestrator)
├── analysis.evidence_artifacts
│   ├── 职责: artifact paths, missing files, byte identity
│   ├── 职责: JSON/JSONL/PNG parseability
│   └── 职责: trace and runtime-event schema checks
│
├── analysis.evidence_manifest_checks
│   ├── 职责: manifest top-level shape
│   ├── 职责: study/contract/artifact key/extension
│   └── 职责: metadata and SHA-256 shape checks
│
├── analysis.evidence_consistency
│   └── 职责: S10/S11/S12 study-level consistency checks
│
└── analysis.evidence_contracts
    ├── 职责: stack-contract artifact consistency
    └── 职责: trace-route contract-event checks
```

**测试覆盖**:
```
直接测试 (4 个)
├── tests/test_evidence_artifacts.py
├── tests/test_evidence_manifest_checks.py
├── tests/test_evidence_consistency.py
└── tests/test_evidence_contracts.py

报告路径测试 (16 个)
├── tests/test_evidence_manifest.py (smoke + byte-identity)
├── tests/test_evidence_report_manifest_shape.py (top-level rejection)
├── tests/test_evidence_report_study_shape.py (study-entry rejection)
├── tests/test_evidence_report_contract_shape.py (contract-entry rejection)
├── tests/test_evidence_report_artifact_paths.py (path/key/extension rejection)
├── tests/test_evidence_contract_report.py (stack-contract scope/route/stage)
├── tests/test_evidence_contract_fallback_report.py (fallback field/map)
├── tests/test_evidence_contract_trace_report.py (trace-route fallback/family/cause)
├── tests/test_evidence_contract_boundary_report.py (split-boundary/routing)
├── tests/test_evidence_trace_report.py (S10 trace consistency/time/schema)
├── tests/test_evidence_wrapper_report.py (S11 wrapper PNG/diagnostics)
├── tests/test_evidence_replay_report.py (S12 replay diagnostics fields)
├── tests/test_evidence_replay_consistency_report.py (S12 replay consistency)
├── tests/test_evidence_replay_artifacts_report.py (S12 replay trace/fixture/schema)
├── tests/test_evidence_manifest_generation.py (manifest generation/docs sync)
└── tests/test_evidence_contracts.py (direct contract validator)
```

**Agent 行动**:
1. 理解拆分动机（职责分离、测试覆盖）
2. 验证拆分后的 CLI 行为与拆分前一致
3. 检查每个模块的测试覆盖

### 5. Review Focus

**概念**: 6 个重点评审区域，每个都有具体的文件和测试清单

**区域 1: Review authority order**
- **目标**: 确保文档权威性顺序正确
- **检查**: `scripts.review_authority_lint`
- **文档**: `wiki/review-backlog.md`, `OPEN_RISKS.md`, `QUALITY_GATES.md`, `OPUS_REVIEW_PACKET.md`

**区域 2: Evidence boundary wording**
- **目标**: 防止合成证据被过度泛化
- **检查**: `scripts/evidence_boundary_lint.py`, `tests/test_synthetic_evidence_boundaries.py`
- **关键**: 双语 lint（英文 + 中文），动态公开文档覆盖

**区域 3: Evidence report modularization**
- **目标**: 验证拆分保持 CLI 行为一致性
- **检查**: 拆分模块和测试文件
- **关键**: 4 个模块 + 20 个测试

**区域 4: Stack contract and adapter exception routing**
- **目标**: 验证数据合同和异常路由
- **检查**: `sre_control/stack.py`, `sre_control/events.py`, `sre_control/stack_contract.py`
- **测试**: `tests/test_contracts.py`, `tests/test_evidence_contract_*.py`

**区域 5: Control-center browser evidence**
- **目标**: 验证前端证据完整性（3 种错误路径）
- **检查**: `scripts.control_center_browser_smoke`
- **测试**: `tests/test_control_center_browser_*.py`
- **关键**: normal + backend_error + frontend_error

**区域 6: Quality-gate updater coverage**
- **目标**: 验证自愈合机制
- **检查**: `scripts/quality_gate_counts.py`
- **测试**: `tests/test_quality_gate_counts.py`
- **关键**: 同步计数更新、命令覆盖、Opus 权威顺序

**Agent 行动**:
1. 按顺序检查 6 个区域
2. 运行每个区域的检查命令
3. 验证每个区域的测试通过

### 6. Questions For Opus

**概念**: 6 个具体的评审问题，都是可验证的

**问题清单**:
```
Q1: OPEN_RISKS.md 是否有阻塞项？
    验证方法: 读 OPEN_RISKS.md，检查 P0/P1 风险

Q2: 证据报告拆分是否保持 CLI 行为一致？
    验证方法: 运行 analysis.evidence_report，对比输出

Q3: 堆栈数据合同是否提供足够的路由能力？
    验证方法: 检查 sre_stack_data_contract.json，验证事件路由

Q4: 控制中心浏览器证据是否覆盖 3 种错误路径？
    验证方法: 检查 manifest_replay=normal+backend_error+frontend_error

Q5: dirty/untracked 文件是否都在评审范围内？
    验证方法: git status，对比 HANDOFF.md 的清单

Q6: evidence_boundary_lint 是否 fail-closed？
    验证方法: 检查新文档是否自动纳入检查
```

**Agent 行动**:
1. 逐个回答 6 个问题
2. 提供验证证据
3. 标记任何无法回答的问题

---

## 依赖关系图

### 文档依赖
```
HANDOFF.md (入口)
├── wiki/review-backlog.md (完成项证据)
├── OPEN_RISKS.md (当前风险)
├── QUALITY_GATES.md (质量门禁)
└── OPUS_REVIEW_PACKET.md (评审包)
    ├── EVENT_EVIDENCE_MANIFEST.md (证据合同)
    ├── STACK_DATA_CONTRACT.md (堆栈合同)
    └── CONTROL_CENTER_HANDOFF.md (控制中心交接)
```

### 命令依赖
```
analysis.evidence_manifest (必须先运行)
└── analysis.evidence_report (依赖 manifest 的 SHA-256)

scripts.quality_gate_counts (自愈合)
├── 运行 analysis.evidence_manifest
└── 运行 analysis.evidence_report
```

### 模块依赖
```
analysis.evidence_report (orchestrator)
├── analysis.evidence_artifacts
├── analysis.evidence_manifest_checks
├── analysis.evidence_consistency
└── analysis.evidence_contracts
```

---

## 常见陷阱与注意事项

### 陷阱 1: pytest count 不一致
**现象**: 文档中的 pytest count 与实际不符
**位置**: HANDOFF.md L102 (871), L141 (874), L280 (871)
**实际值**: 874
**影响**: 评审人员困惑，自动化工具失败
**解决**: 统一更新为 874

### 陷阱 2: 命令顺序错误
**现象**: 先运行 `analysis.evidence_report`，后运行 `analysis.evidence_manifest`
**后果**: 字节身份检查失败（SHA-256 不匹配）
**正确顺序**: manifest → report
**原因**: manifest 生成 SHA-256，report 验证 SHA-256

### 陷阱 3: 忽略 untracked 文件
**现象**: 合并时只包含 modified 文件，遗漏 untracked 文件
**后果**: 质量门禁失败，测试缺失
**解决**: 使用 `git ls-files --others --exclude-standard` 检查

### 陷阱 4: 历史包混淆
**现象**: 将 v1.0/v2.0/v2.1 的发现当作当前开放项
**后果**: 重复评审已解决的问题
**解决**: 始终从 live ledgers 开始（wiki/review-backlog.md, OPEN_RISKS.md）

### 陷阱 5: 证据边界过度泛化
**现象**: 将合成证据描述为生产证明
**后果**: 违反边界声明，误导读者
**解决**: 运行 `scripts.evidence_boundary_lint`，检查 overclaim wording

### 陷阱 6: 控制中心证据不完整
**现象**: 只检查 normal 路径，忽略 backend_error 和 frontend_error
**后果**: 错误处理路径未验证
**解决**: 确认 `manifest_replay=normal+backend_error+frontend_error`

---

## Agent 评审检查清单

### Phase 1: 环境准备 (5 分钟)
- [ ] 切换到 `spacex-session` 分支
- [ ] 运行 `git status --short --branch --untracked-files=all`
- [ ] 确认 ahead 91 commits
- [ ] 确认 36 个 untracked 文件

### Phase 2: 文档阅读 (15 分钟)
- [ ] 读 HANDOFF.md（本文档）
- [ ] 读 wiki/review-backlog.md
- [ ] 读 OPEN_RISKS.md
- [ ] 读 QUALITY_GATES.md

### Phase 3: 命令验证 (30 分钟)
- [ ] 运行 `python -m pytest --collect-only -q tests`
- [ ] 确认 874 tests collected
- [ ] 运行 `python -m analysis.evidence_manifest`
- [ ] 运行 `python -m analysis.evidence_report`
- [ ] 确认 `artifact_check ok studies=3 files=8`
- [ ] 运行 `python -m scripts.review_authority_lint`
- [ ] 确认 `review authority order ok`
- [ ] 运行 `python -m scripts.evidence_boundary_lint`
- [ ] 确认 `evidence boundary lint ok`
- [ ] 运行 `python -u -m scripts.quality_gate_counts`
- [ ] 确认 `quality gate pytest count: 874`

### Phase 4: 重点区域检查 (45 分钟)
- [ ] 检查证据报告拆分（4 个模块 + 20 个测试）
- [ ] 检查堆栈数据合同（sre_stack_data_contract.json）
- [ ] 检查控制中心浏览器证据（3 种错误路径）
- [ ] 检查质量门禁更新器（自愈合机制）

### Phase 5: 问题回答 (15 分钟)
- [ ] Q1: OPEN_RISKS.md 是否有阻塞项？
- [ ] Q2: 证据报告拆分是否保持 CLI 行为一致？
- [ ] Q3: 堆栈数据合同是否提供足够的路由能力？
- [ ] Q4: 控制中心浏览器证据是否覆盖 3 种错误路径？
- [ ] Q5: dirty/untracked 文件是否都在评审范围内？
- [ ] Q6: evidence_boundary_lint 是否 fail-closed？

### Phase 6: 决策 (10 分钟)
- [ ] 汇总发现的问题
- [ ] 评估问题优先级（P0/P1/P2）
- [ ] 做出 PASS/BLOCK 决策
- [ ] 生成评审报告

---

## 快速参考

### 关键文件路径
```
docs/opus-review/HANDOFF.md                    # 本文档
wiki/review-backlog.md                         # 完成项证据
docs/codex-review/OPEN_RISKS.md                # 当前风险
docs/codex-review/QUALITY_GATES.md             # 质量门禁
docs/opus-review/OPUS_REVIEW_PACKET.md         # 评审包
docs/EVENT_EVIDENCE_MANIFEST.md                # 证据合同
docs/STACK_DATA_CONTRACT.md                    # 堆栈合同
docs/CONTROL_CENTER_HANDOFF.md                 # 控制中心交接
```

### 关键命令
```bash
# 环境检查
git status --short --branch --untracked-files=all
git log --oneline --decorate -5

# 测试验证
python -m pytest --collect-only -q tests
python -m pytest tests

# 证据验证
python -m analysis.evidence_manifest
python -m analysis.evidence_report

# 质量门禁
python -m scripts.review_authority_lint
python -m scripts.evidence_boundary_lint
python -u -m scripts.quality_gate_counts
python -m scripts.quality_gate_counts --check --skip-expensive
```

### 预期输出
```text
874 tests collected
artifact_check ok studies=3 files=8
review authority order ok
evidence boundary lint ok
quality gate pytest count: 874
manifest_replay=normal+backend_error+frontend_error
```

---

## Agent 自动化脚本

### 脚本 1: 快速验证
```bash
#!/bin/bash
# quick_verify.sh - 快速验证当前工作区状态

echo "=== Git Status ==="
git status --short --branch --untracked-files=all | head -10

echo -e "\n=== Pytest Count ==="
python -m pytest --collect-only -q tests 2>&1 | tail -1

echo -e "\n=== Evidence Report ==="
python -m analysis.evidence_report 2>&1 | grep "artifact_check"

echo -e "\n=== Quality Gate Count ==="
python -u -m scripts.quality_gate_counts 2>&1 | grep "quality gate pytest count"

echo -e "\n=== Review Authority ==="
python -m scripts.review_authority_lint 2>&1

echo -e "\n=== Evidence Boundary ==="
python -m scripts.evidence_boundary_lint 2>&1
```

### 脚本 2: 完整评审
```bash
#!/bin/bash
# full_review.sh - 运行完整评审流程

set -e

echo "Phase 1: Environment Check"
git status --short --branch --untracked-files=all

echo -e "\nPhase 2: Test Collection"
python -m pytest --collect-only -q tests

echo -e "\nPhase 3: Evidence Validation"
python -m analysis.evidence_manifest
python -m analysis.evidence_report

echo -e "\nPhase 4: Quality Gates"
python -m scripts.review_authority_lint
python -m scripts.evidence_boundary_lint
python -u -m scripts.quality_gate_counts

echo -e "\nPhase 5: All Tests"
python -m pytest tests

echo -e "\n✅ Full review completed successfully"
```

---

## 总结

### HANDOFF.md 的核心价值
1. **评审入口**: 第一个应该阅读的文档
2. **状态快照**: 提供当前工作区的完整状态
3. **流程指引**: 4 步评审流程，从快速到深度
4. **重点聚焦**: 6 个重点区域，避免迷失
5. **问题驱动**: 6 个具体问题，可验证

### Agent 使用建议
1. **严格按流程**: 不要跳过任何步骤
2. **验证优先**: 运行命令验证声明，不要盲目相信文档
3. **记录发现**: 记录每个阶段的发现和问题
4. **避免陷阱**: 参考"常见陷阱"部分
5. **使用检查清单**: 确保不遗漏任何检查项

### 后续 Agent 介入点
1. **评审执行**: 使用本文档作为评审指南
2. **问题诊断**: 参考"常见陷阱"部分
3. **自动化**: 使用提供的自动化脚本
4. **报告生成**: 基于检查清单生成评审报告

---

**文档维护**: 当 HANDOFF.md 更新时，同步更新本文档  
**反馈渠道**: 如发现本文档有误或需要补充，请更新此文档
