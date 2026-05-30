# OPEN_RISKS.md 深度分析

**分析日期**: 2026-05-31  
**文档路径**: `docs/codex-review/OPEN_RISKS.md`  
**文档作用**: 跟踪当前开放风险和已解决问题

---

## 文档结构评估

### ✅ 优点

1. **风险分类清晰**
   - Current Risk Summary: 当前开放风险
   - Resolved Since Earlier Packets: 已解决风险
   - Numerical Risks: 数值风险
   - Modeling Risks: 建模风险
   - Suggested Next PR: 后续建议

2. **历史追溯完整**
   - 明确标注 F50-F60 来自 Opus v2.0 (2026-05-26)
   - 明确标注 F61-F81 来自 Opus v2.1 (2026-05-28)
   - 提供了历史评审文档的路径

3. **解决方案详细**
   - 每个已解决的风险都有具体的解决方案
   - 包含了代码位置、测试覆盖、验证方法
   - 长达 200+ 行的详细解决记录

4. **风险优先级明确**
   - 使用 P0/P1/P2 标注优先级
   - 当前只有 1 个 P2 风险开放

---

## Current Risk Summary 分析

### R1: Synthetic evidence boundary (P2)

**风险描述**:
```
Before/after studies are synthetic scenario evidence and can still be 
overgeneralized in new prose or external summaries.
```

**建议行动**:
```
Keep reports and summaries explicit that these are scenario-internal results; 
live review docs now have bilingual overclaim wording lint for English and 
Chinese review prose.
```

**评估**: ⭐⭐⭐⭐⭐

这是一个非常合理的开放风险：

1. **风险识别准确**: 合成证据确实容易被过度泛化
2. **优先级合理**: P2 表示重要但不阻塞
3. **缓解措施到位**: 
   - 双语 overclaim wording lint（英文 + 中文）
   - 明确的边界声明要求
   - `scripts.evidence_boundary_lint` 自动检查

4. **持续监控**: 这是一个需要长期关注的风险，不是一次性修复

**建议**: 
- 考虑在每次评审时都重新检查这个风险
- 可以添加一个检查清单，确保新文档都符合边界要求

---

## Resolved Since Earlier Packets 分析

### 解决项数量统计

文档列出了大量已解决的风险项：

| 类别 | 数量 | 示例 |
|------|------|------|
| 核心功能 | 8 | Per-sensor innovation gate, Allocator fallback, EKF Joseph form |
| 证据链 | 6 | Evidence manifest, Evidence report, Stack data contract |
| Opus v1.0 findings | 42 | F01-F42 |
| Opus v2.0 findings | 11 | F50-F60, G1 |
| Opus v2.1 findings | 21 | F61-F81 |

**总计**: 88+ 个已解决项

### 解决质量评估

随机抽查几个解决项的质量：

#### 示例 1: Opus F13 - Artifact directory monkey-patching

**原问题**:
```
Opus F13 is resolved in `analysis.evidence_manifest`: artifact directories are
now passed explicitly into the Section 10/11 generators instead of
monkey-patching `_common.ARTIFACTS` or `s10_failure_trace.ARTIFACTS`.
```

**评估**: ⭐⭐⭐⭐⭐
- 问题描述清晰
- 解决方案明确（显式传参 vs monkey-patching）
- 代码位置明确（`analysis.evidence_manifest`）

#### 示例 2: Opus F14 - JSON key order

**原问题**:
```
Opus F14 is resolved for Section 10 evidence artifacts: S10 full/sample JSONL
traces now use sorted JSON keys, and the failure-trace tests assert serialized
key order so manifest byte identity is not sensitive to dict construction
order.
```

**评估**: ⭐⭐⭐⭐⭐
- 问题识别准确（dict 顺序导致字节不一致）
- 解决方案合理（sorted keys）
- 有回归测试保护（failure-trace tests assert key order）

#### 示例 3: Opus F50 - PredictiveAutoscaler ZOH

**原问题**:
```
Opus v2.0 F50 is resolved in `PredictiveAutoscaler`: the continuous plant
input matrix is scaled by `1/dt`, so ZOH produces a one-step `Bd` matching
executor units (`u=1` means one replica per control step). The regression test
checks plant/executor one-step agreement.
```

**评估**: ⭐⭐⭐⭐⭐
- 技术细节准确（ZOH 离散化）
- 单位一致性明确（`u=1` = one replica per step）
- 有回归测试验证

#### 示例 4: Opus v2.1 F61-F81 综合解决

**原问题**:
```
Opus v2.1 F61-F81 are resolved in the current workspace. The main closures are:
refreshed browser evidence manifests and replay report; non-finite guards for
`SignalFusion`, `SLOGuardrail.approve()/audit()`, and `WeightedLoadBalancer`;
rejected Canary warm-start trust-region shrink behavior; strict JSON writers
with `allow_nan=False`; repo-relative browser manifest artifact paths; proper
`analysis.run_all(artifacts_dir=...)` forwarding; control-center share-state
whitelisting and dynamic text escaping; loopback-only bind enforcement;
browser/package/integration gates in `scripts.quality_gate_counts`; a read-only
`python -m scripts.quality_gate_counts --check` mode; and manifest replay error
messages that include manifest, viewport, DOM path, and regeneration command.
```

**评估**: ⭐⭐⭐⭐⭐
- 21 个问题的综合解决方案
- 涵盖了安全、正确性、可用性多个维度
- 特别好的改进：
  - `allow_nan=False` 防止非标准 JSON
  - loopback-only bind 安全加固
  - 详细的错误消息（包含重现命令）

### 解决项组织评估

**评估**: ⭐⭐⭐⭐

解决项按时间顺序组织，每个都包含：
1. 问题标识符（如 Opus F13）
2. 解决位置（代码模块）
3. 解决方案描述
4. 验证方法（测试）

**建议**: 
- 考虑添加一个表格索引，方便快速查找
- 可以按类别（而非时间）重新组织，便于主题阅读

---

## Numerical Risks 分析

**当前状态**:
```
当前无开放数值风险记录。v1.0 与 v2.0 已知数值 findings 已迁入 resolved ledger，
并绑定回归测试。新数值断言仍需保持 scenario-specific，不得升级为 production proof。
```

**评估**: ⭐⭐⭐⭐⭐

这个声明非常好：
1. **明确了当前状态**: 无开放数值风险
2. **强调了保护机制**: 回归测试绑定
3. **设定了边界**: scenario-specific，不是 production proof

**建议**: 
- 考虑列出已解决的数值风险清单（如 F50 ZOH 问题）
- 可以添加一个"数值风险检查清单"，用于未来的代码审查

---

## Modeling Risks 分析

### 4 个建模风险

#### 1. SRE analogy overreach

**风险**:
```
Convexification, MPC, and EKF are migrated abstractions, not proof that rocket 
controllers directly map to production systems.
```

**影响**:
```
Docs must avoid implying official SpaceX implementation or production equivalence.
```

**评估**: ⭐⭐⭐⭐⭐
- 风险识别准确
- 边界清晰
- 缓解措施明确（文档声明）

#### 2. Single-stack orchestration

**风险**:
```
`SREControlStack` still chains adapters in one process, but its stage 
inputs/outputs, direct event kinds, and runtime-stage routes are now exported 
as a non-production data contract.
```

**影响**:
```
Future work can split along the exported boundaries if this becomes more than 
a research stack.
```

**评估**: ⭐⭐⭐⭐⭐
- 承认了当前的限制（单进程）
- 提供了未来扩展路径（数据合同边界）
- 不过度承诺

#### 3. Event-kind evolution

**风险**:
```
`adapter_exception` now carries stage-family, fault-family, and fallback-action 
fields, and the stack data contract binds stage event kinds plus observed trace 
events to the shared runtime registry. Future additions should keep this as a 
stable payload extension rather than minting new event kinds for every adapter 
failure.
```

**影响**:
```
Future review may need finer remediation playbooks, but the event payload is 
now routeable by adapter family and contract drift is report-checked.
```

**评估**: ⭐⭐⭐⭐⭐
- 设计原则清晰（payload extension vs new event kinds）
- 当前实现合理（adapter_family, fault_family, fallback_action）
- 未来演进路径明确

#### 4. Action magnitude contract

**风险**:
```
`SREControlStack.step()` treats `safe_action` as a guardrail direction vector 
whose L2 norm is scalar RPS demand; `zone_target` is the separate placement 
distribution.
```

**影响**:
```
Future work that changes `safe_action` semantics must update the stack contract, 
Section 10 evidence expectations, and allocator tests together instead of 
switching to component sums locally.
```

**评估**: ⭐⭐⭐⭐⭐
- 语义合同明确（L2 norm = RPS demand）
- 变更影响范围清晰（contract + evidence + tests）
- 防止了局部修改导致的不一致

### 建模风险总体评估

**评分**: ⭐⭐⭐⭐⭐

这 4 个建模风险的管理非常出色：
1. **识别准确**: 都是真实存在的架构限制
2. **影响明确**: 每个都说明了具体影响
3. **缓解到位**: 都有相应的保护机制
4. **演进路径清晰**: 都说明了未来如何改进

---

## Suggested Next PR 分析

**建议**:
```
Prefer one of these research-landing slices：

1. Add release-pipeline automation only if this repository starts publishing
   versioned artifacts.
2. Continue review-ledger hygiene when new packets are added, keeping old
   packets labeled as historical when their findings are already resolved.
```

**评估**: ⭐⭐⭐⭐⭐

这两个建议非常合理：

1. **Release pipeline**: 
   - 条件明确（"only if"）
   - 避免过早优化

2. **Review-ledger hygiene**: 
   - 强调了持续维护的重要性
   - 防止历史包被误认为当前状态

**建议**: 
- 可以添加第 3 个建议：考虑将单进程堆栈拆分为分布式架构
- 可以添加第 4 个建议：增强数值稳定性测试（如 fuzz testing）

---

## 与其他文档的一致性

### vs HANDOFF.md

| 项目 | OPEN_RISKS.md | HANDOFF.md | 一致性 |
|------|---------------|------------|--------|
| v2.0 findings | F50-F60 已解决 | 同左 | ✅ 一致 |
| v2.1 findings | F61-F81 已解决 | 同左 | ✅ 一致 |
| 开放风险数 | 1 (R1 P2) | 未明确提及 | ⚠️ HANDOFF 应补充 |

### vs QUALITY_GATES.md

| 项目 | OPEN_RISKS.md | QUALITY_GATES.md | 一致性 |
|------|---------------|------------------|--------|
| 证据边界 | R1 强调边界声明 | 详细说明边界 lint | ✅ 一致 |
| 数值风险 | 无开放项 | 测试覆盖完整 | ✅ 一致 |

### vs OPUS_REVIEW_PACKET.md

| 项目 | OPEN_RISKS.md | OPUS_REVIEW_PACKET.md | 一致性 |
|------|---------------|----------------------|--------|
| v1.0 findings | 42 个已解决 | 同左 | ✅ 一致 |
| v2.0 findings | F50-F60 已解决 | 同左 | ✅ 一致 |
| 当前权威 | 本文档 | 指向本文档 | ✅ 一致 |

---

## 改进建议

### 立即改进（阻塞合并）

**无** - 文档质量已达到合并标准

### 短期改进（下一个 PR）

1. **添加索引表格**
   ```markdown
   ## Quick Index
   
   | Finding ID | Status | Category | Priority |
   |------------|--------|----------|----------|
   | R1 | Open | Evidence boundary | P2 |
   | F50-F60 | Resolved | Numerical | - |
   | F61-F81 | Resolved | Mixed | - |
   ```

2. **添加解决时间线**
   ```markdown
   ## Resolution Timeline
   
   - 2026-05-26: Opus v2.0 review (F50-F60)
   - 2026-05-28: Opus v2.1 review (F61-F81)
   - 2026-05-31: Current review (R1 monitoring)
   ```

3. **添加风险趋势图**
   - 展示开放风险数量随时间的变化
   - 可以使用 ASCII art 或 mermaid

### 长期改进（研究方向）

1. **风险管理自动化**
   ```python
   # scripts/risk_tracker.py
   def check_open_risks():
       """自动检查 OPEN_RISKS.md 与代码的一致性"""
       pass
   ```

2. **风险影响分析**
   - 为每个风险添加影响评分（1-10）
   - 基于影响和概率计算风险优先级

3. **风险关联图**
   - 展示风险之间的依赖关系
   - 识别关键路径风险

---

## 总体评价

**评分**: ⭐⭐⭐⭐⭐ (5.0/5)

**优点**:
- 风险分类清晰完整
- 解决方案详细可验证
- 历史追溯完整
- 建模风险管理出色
- 后续建议合理

**无明显缺点**

**结论**: 
OPEN_RISKS.md 是一份卓越的风险管理文档，达到了工业级标准。特别是：
1. 88+ 个已解决项的详细记录
2. 4 个建模风险的清晰管理
3. 唯一开放风险（R1）的合理定位

这份文档可以作为软件工程风险管理的最佳实践参考。

---

## 特别亮点

### 1. 双语边界 lint

```
live review docs now have bilingual overclaim wording lint for English and 
Chinese review prose
```

这是一个非常好的实践，考虑到了国际化场景。

### 2. Fail-closed 设计

```
scripts.evidence_boundary_lint.PUBLIC_EVIDENCE_BOUNDARY_DOCS now defines the
public/review document surface linted by
tests/test_synthetic_evidence_boundaries.py
```

新文档必须纳入检查，防止遗漏。

### 3. 详细的错误消息

```
manifest replay error messages that include manifest, viewport, DOM path, and 
regeneration command
```

错误消息包含重现命令，大大提高了可调试性。

---

**分析完成时间**: 2026-05-31  
**下一步**: 分析 OPUS_REVIEW_PACKET.md
