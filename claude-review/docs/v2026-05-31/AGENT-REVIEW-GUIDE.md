# Agent 评审指南 - 快速上手手册

**目标受众**: 后续介入评审的 AI Agent  
**预计阅读时间**: 10 分钟  
**前置阅读**: HANDOFF-KNOWLEDGE-BASE.md（可选，深度参考）

---

## 快速开始

### 你的任务
对 spacex-session 分支进行深度评审，判断是否可以合并到主分支。

### 评审标准
- ✅ **PASS**: 所有质量门禁通过，无阻塞问题
- ⚠️ **PASS with Fixes**: 有轻微问题，修复后可合并
- ❌ **BLOCK**: 有严重问题，必须修复后才能合并

### 预期时间
- 快速评审: 30 分钟
- 完整评审: 2 小时

---

## 评审流程（4 步）

### Step 1: 环境检查 (5 分钟)

```bash
# 1.1 检查分支状态
git status --short --branch --untracked-files=all

# 预期输出:
# ## spacex-session...origin/spacex-session [ahead 91]
# M  (大量 modified 文件)
# ?? (36 个 untracked 文件)

# 1.2 检查测试数量
python -m pytest --collect-only -q tests 2>&1 | tail -1

# 预期输出:
# 874 tests collected
```

**检查点**:
- [ ] 分支是 spacex-session
- [ ] ahead 91 commits
- [ ] 874 个测试
- [ ] 36 个 untracked 文件

### Step 2: 文档阅读 (15 分钟)

按顺序阅读以下文档：

1. **docs/opus-review/HANDOFF.md** (必读)
   - 评审流程
   - 重点区域
   - 评审问题

2. **docs/codex-review/OPEN_RISKS.md** (必读)
   - 当前开放风险
   - 已解决问题

3. **docs/codex-review/QUALITY_GATES.md** (必读)
   - 质量门禁命令
   - 预期输出

4. **wiki/review-backlog.md** (可选)
   - 完成项证据

**检查点**:
- [ ] 理解了 4 步评审流程
- [ ] 知道了 6 个重点区域
- [ ] 了解了当前开放风险（应该只有 1 个 P2）

### Step 3: 命令验证 (30 分钟)

运行以下命令并验证输出：

```bash
# 3.1 证据验证（必须按顺序）
python -m analysis.evidence_manifest
python -m analysis.evidence_report
# 预期: artifact_check ok studies=3 files=8

# 3.2 质量门禁
python -m scripts.review_authority_lint
# 预期: review authority order ok

python -m scripts.evidence_boundary_lint
# 预期: evidence boundary lint ok

python -u -m scripts.quality_gate_counts
# 预期: quality gate pytest count: 874

# 3.3 完整测试（可选，耗时较长）
python -m pytest tests
# 预期: 874 passed
```

**检查点**:
- [ ] 证据报告通过
- [ ] review authority 通过
- [ ] evidence boundary 通过
- [ ] quality gate count 正确（874）

### Step 4: 重点检查 (45 分钟)

检查 6 个重点区域：

#### 区域 1: Review authority order
```bash
python -m scripts.review_authority_lint
```
- [ ] 输出 `review authority order ok`

#### 区域 2: Evidence boundary wording
```bash
python -m scripts.evidence_boundary_lint
```
- [ ] 输出 `evidence boundary lint ok`
- [ ] 确认双语 lint（英文 + 中文）

#### 区域 3: Evidence report modularization
- [ ] 确认 4 个拆分模块存在：
  - `analysis/evidence_artifacts.py`
  - `analysis/evidence_manifest_checks.py`
  - `analysis/evidence_consistency.py`
  - `analysis/evidence_contracts.py`
- [ ] 确认 20+ 个拆分测试存在

#### 区域 4: Stack contract and adapter exception routing
- [ ] 检查 `analysis/artifacts/sre_stack_data_contract.json` 存在
- [ ] 确认包含 `production_claim: false`
- [ ] 确认包含 stage event kinds

#### 区域 5: Control-center browser evidence
```bash
python -m scripts.control_center_browser_smoke --report-manifests \
  --report-json analysis/artifacts/control-center-browser-evidence-report.json
```
- [ ] 确认输出包含 `manifest_replay=normal+backend_error+frontend_error`

#### 区域 6: Quality-gate updater coverage
```bash
python -m scripts.quality_gate_counts --check --skip-expensive
```
- [ ] 输出 `quality gate docs check passed`

---

## 评审问题清单

回答以下 6 个问题：

### Q1: OPEN_RISKS.md 是否有阻塞项？

**如何回答**:
1. 读 `docs/codex-review/OPEN_RISKS.md`
2. 查看 "Current Risk Summary" 部分
3. 检查是否有 P0 或 P1 风险

**预期答案**: 
- 只有 1 个 P2 风险（R1: Synthetic evidence boundary）
- 无 P0/P1 阻塞项

### Q2: 证据报告拆分是否保持 CLI 行为一致？

**如何回答**:
1. 运行 `python -m analysis.evidence_report`
2. 检查输出是否包含 `artifact_check ok`
3. 对比 HANDOFF.md 中的预期输出

**预期答案**: 
- CLI 行为一致
- 输出格式未变

### Q3: 堆栈数据合同是否提供足够的路由能力？

**如何回答**:
1. 读 `analysis/artifacts/sre_stack_data_contract.json`
2. 检查是否包含 stage event kinds
3. 检查是否包含 runtime-stage routes

**预期答案**: 
- 包含完整的 stage 边界
- 包含事件路由前缀
- 明确标注 `production_claim: false`

### Q4: 控制中心浏览器证据是否覆盖 3 种错误路径？

**如何回答**:
1. 运行 control_center_browser_smoke
2. 检查输出是否包含 `manifest_replay=normal+backend_error+frontend_error`

**预期答案**: 
- 覆盖 normal 路径
- 覆盖 backend_error 路径
- 覆盖 frontend_error 路径

### Q5: dirty/untracked 文件是否都在评审范围内？

**如何回答**:
1. 运行 `git status --short --branch --untracked-files=all`
2. 对比 HANDOFF.md 中的 untracked 文件清单
3. 检查是否有意外的新文件

**预期答案**: 
- 36 个 untracked 文件
- 都在 HANDOFF.md 的清单中
- 无意外文件

### Q6: evidence_boundary_lint 是否 fail-closed？

**如何回答**:
1. 检查 `scripts/evidence_boundary_lint.py`
2. 确认 `PUBLIC_EVIDENCE_BOUNDARY_DOCS` 定义了公开文档表面
3. 确认新文档必须纳入检查

**预期答案**: 
- fail-closed 策略正确
- 新文档自动纳入检查
- 双语 lint 覆盖

---

## 常见问题 FAQ

### Q: pytest count 为什么不一致？

**A**: 这是已知的文档同步问题（M1）。

- **文档声明**: 871 或 873
- **实际值**: 874
- **原因**: 最近新增了测试，文档更新滞后
- **影响**: 不影响功能，仅文档不一致
- **建议**: 统一更新为 874

### Q: 为什么必须先运行 evidence_manifest 再运行 evidence_report？

**A**: 因为 manifest 生成 SHA-256，report 验证 SHA-256。

- **正确顺序**: manifest → report
- **错误顺序**: report → manifest（会导致字节身份检查失败）
- **原因**: manifest 存储 artifact 的 SHA-256 和字节大小

### Q: untracked 文件是否应该提交？

**A**: 是的，所有 36 个 untracked 文件都应该提交。

- **原因**: 这些是拆分的测试和证据文件
- **后果**: 如果遗漏，质量门禁会失败
- **检查**: 使用 `git ls-files --others --exclude-standard`

### Q: 如何判断是 PASS 还是 BLOCK？

**A**: 使用以下决策树：

```
有 P0 问题？
├── 是 → BLOCK
└── 否 → 有 P1 问题？
    ├── 是 → BLOCK
    └── 否 → 有 P2 问题？
        ├── 是 → PASS with Fixes
        └── 否 → PASS
```

### Q: 历史评审包（v1.0/v2.0/v2.1）还需要看吗？

**A**: 不需要，它们是历史记录。

- **当前权威**: wiki/review-backlog.md, OPEN_RISKS.md, QUALITY_GATES.md
- **历史包用途**: 追溯问题来源，了解演进历史
- **建议**: 从 live ledgers 开始，历史包作为参考

### Q: 如果某个命令失败了怎么办？

**A**: 按以下步骤处理：

1. **记录失败信息**: 完整的错误消息
2. **检查是否已知问题**: 查看 OPEN_RISKS.md
3. **评估严重程度**: P0/P1/P2
4. **决定是否阻塞**: P0/P1 阻塞，P2 不阻塞
5. **记录到评审报告**: 包含重现步骤

---

## 评审报告模板

使用以下模板生成评审报告：

```markdown
# Agent 评审报告 - vYYYY-MM-DD

**评审人**: [Agent Name]  
**评审日期**: YYYY-MM-DD  
**分支**: spacex-session  
**Commit**: [git rev-parse HEAD]

---

## 评审结论

- [ ] ✅ PASS
- [ ] ⚠️ PASS with Fixes
- [ ] ❌ BLOCK

**理由**: [简短说明]

---

## 验证结果

| 检查项 | 状态 | 输出 |
|--------|------|------|
| pytest count | ✅/❌ | 874 tests collected |
| evidence_report | ✅/❌ | artifact_check ok studies=3 files=8 |
| review_authority_lint | ✅/❌ | review authority order ok |
| evidence_boundary_lint | ✅/❌ | evidence boundary lint ok |
| quality_gate_counts | ✅/❌ | quality gate pytest count: 874 |

---

## 发现的问题

| ID | 优先级 | 类别 | 描述 | 建议 |
|----|--------|------|------|------|
| M1 | P2 | 文档同步 | pytest count 不一致 | 统一更新为 874 |
| ... | ... | ... | ... | ... |

---

## 评审问题回答

### Q1: OPEN_RISKS.md 是否有阻塞项？
**答**: [是/否]  
**证据**: [说明]

### Q2: 证据报告拆分是否保持 CLI 行为一致？
**答**: [是/否]  
**证据**: [说明]

### Q3: 堆栈数据合同是否提供足够的路由能力？
**答**: [是/否]  
**证据**: [说明]

### Q4: 控制中心浏览器证据是否覆盖 3 种错误路径？
**答**: [是/否]  
**证据**: [说明]

### Q5: dirty/untracked 文件是否都在评审范围内？
**答**: [是/否]  
**证据**: [说明]

### Q6: evidence_boundary_lint 是否 fail-closed？
**答**: [是/否]  
**证据**: [说明]

---

## 建议的后续行动

### 立即行动（合并前）
- [ ] [行动项 1]
- [ ] [行动项 2]

### 短期改进（下一个 PR）
- [ ] [改进项 1]
- [ ] [改进项 2]

---

**评审完成时间**: YYYY-MM-DD HH:MM  
**评审耗时**: [X 小时]
```

---

## 自动化脚本

### 脚本 1: 一键评审

将以下脚本保存为 `quick_review.sh`：

```bash
#!/bin/bash
# quick_review.sh - 一键运行所有评审检查

set -e

echo "=========================================="
echo "Agent 快速评审脚本"
echo "=========================================="

echo -e "\n[1/6] 检查 Git 状态..."
git status --short --branch --untracked-files=all | head -5
echo "✅ Git 状态检查完成"

echo -e "\n[2/6] 检查测试数量..."
TEST_COUNT=$(python -m pytest --collect-only -q tests 2>&1 | tail -1)
echo "$TEST_COUNT"
if [[ "$TEST_COUNT" == *"874"* ]]; then
    echo "✅ 测试数量正确"
else
    echo "❌ 测试数量不正确，预期 874"
fi

echo -e "\n[3/6] 运行证据验证..."
python -m analysis.evidence_manifest > /dev/null 2>&1
EVIDENCE_RESULT=$(python -m analysis.evidence_report 2>&1 | grep "artifact_check")
echo "$EVIDENCE_RESULT"
if [[ "$EVIDENCE_RESULT" == *"ok"* ]]; then
    echo "✅ 证据验证通过"
else
    echo "❌ 证据验证失败"
fi

echo -e "\n[4/6] 检查 review authority..."
AUTHORITY_RESULT=$(python -m scripts.review_authority_lint 2>&1)
echo "$AUTHORITY_RESULT"
if [[ "$AUTHORITY_RESULT" == *"ok"* ]]; then
    echo "✅ Review authority 通过"
else
    echo "❌ Review authority 失败"
fi

echo -e "\n[5/6] 检查 evidence boundary..."
BOUNDARY_RESULT=$(python -m scripts.evidence_boundary_lint 2>&1)
echo "$BOUNDARY_RESULT"
if [[ "$BOUNDARY_RESULT" == *"ok"* ]]; then
    echo "✅ Evidence boundary 通过"
else
    echo "❌ Evidence boundary 失败"
fi

echo -e "\n[6/6] 检查 quality gate count..."
GATE_COUNT=$(python -u -m scripts.quality_gate_counts 2>&1 | grep "quality gate pytest count")
echo "$GATE_COUNT"
if [[ "$GATE_COUNT" == *"874"* ]]; then
    echo "✅ Quality gate count 正确"
else
    echo "❌ Quality gate count 不正确"
fi

echo -e "\n=========================================="
echo "快速评审完成！"
echo "=========================================="
```

**使用方法**:
```bash
chmod +x quick_review.sh
./quick_review.sh
```

### 脚本 2: 生成评审报告

将以下脚本保存为 `generate_report.py`：

```python
#!/usr/bin/env python3
"""生成 Agent 评审报告"""

import subprocess
import datetime

def run_command(cmd):
    """运行命令并返回输出"""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout.strip()

def main():
    print("生成评审报告...")
    
    # 获取基本信息
    commit = run_command("git rev-parse HEAD")
    date = datetime.datetime.now().strftime("%Y-%m-%d")
    
    # 运行检查
    test_count = run_command("python -m pytest --collect-only -q tests 2>&1 | tail -1")
    evidence = run_command("python -m analysis.evidence_report 2>&1 | grep artifact_check")
    authority = run_command("python -m scripts.review_authority_lint 2>&1")
    boundary = run_command("python -m scripts.evidence_boundary_lint 2>&1")
    gate_count = run_command("python -u -m scripts.quality_gate_counts 2>&1 | grep 'quality gate pytest count'")
    
    # 生成报告
    report = f"""# Agent 评审报告 - v{date}

**评审人**: Auto Agent  
**评审日期**: {date}  
**分支**: spacex-session  
**Commit**: {commit[:8]}

---

## 验证结果

| 检查项 | 状态 | 输出 |
|--------|------|------|
| pytest count | {'✅' if '874' in test_count else '❌'} | {test_count} |
| evidence_report | {'✅' if 'ok' in evidence else '❌'} | {evidence} |
| review_authority_lint | {'✅' if 'ok' in authority else '❌'} | {authority} |
| evidence_boundary_lint | {'✅' if 'ok' in boundary else '❌'} | {boundary} |
| quality_gate_counts | {'✅' if '874' in gate_count else '❌'} | {gate_count} |

---

**生成时间**: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""
    
    # 保存报告
    filename = f"agent-review-{date}.md"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"✅ 报告已生成: {filename}")

if __name__ == "__main__":
    main()
```

**使用方法**:
```bash
chmod +x generate_report.py
python generate_report.py
```

---

## 总结

### 关键要点
1. **4 步流程**: 环境检查 → 文档阅读 → 命令验证 → 重点检查
2. **6 个问题**: 必须全部回答
3. **决策标准**: P0/P1 阻塞，P2 不阻塞
4. **常见陷阱**: pytest count 不一致、命令顺序错误、忽略 untracked 文件

### 快速决策
- 所有检查通过 + 无 P0/P1 问题 = ✅ PASS
- 有 P2 问题 = ⚠️ PASS with Fixes
- 有 P0/P1 问题 = ❌ BLOCK

### 下一步
1. 运行 `quick_review.sh` 快速验证
2. 回答 6 个评审问题
3. 使用模板生成评审报告
4. 做出 PASS/BLOCK 决策

---

**文档维护**: 与 HANDOFF.md 保持同步  
**反馈渠道**: 如有问题或建议，请更新此文档
