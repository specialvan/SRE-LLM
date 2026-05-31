> Historical Opus v2026-05-31 returned review artifact; it is not the current handoff.
> For live status, read `docs/opus-review/HANDOFF.md`, `wiki/review-backlog.md`,
> `docs/codex-review/OPEN_RISKS.md`, and `docs/codex-review/QUALITY_GATES.md`.
> Packet-time pytest-count findings such as 871/873 are historical observations;
> verify current counts with fresh quality-gate output.
# QUALITY_GATES.md 深度分析

**分析日期**: 2026-05-31  
**文档路径**: `docs/codex-review/QUALITY_GATES.md`  
**文档作用**: 可重现的质量门禁命令和预期输出

---

## 文档结构评估

### ✅ 优点

1. **命令列表规范化**
   - 明确标注为 "canonical command list"
   - 所有命令都是可直接复制执行的
   - 包含了完整的参数（如 `--report-manifests`, `--skip-expensive`）

2. **实际输出记录**
   - 提供了本地运行的真实输出
   - 使用代码块格式，易于对比
   - 包含了关键的输出片段（如 `artifact_check ok`）

3. **门禁家族分类清晰**
   - 用表格形式列出了 21 个测试家族
   - 每个家族都有明确的覆盖范围说明
   - 便于理解测试的组织结构

4. **分析证据边界说明详细**
   - 列出了 Section 10/11/12 的关键指标
   - 明确了合成证据的边界
   - 强调了不能作为生产证明

### ⚠️ 发现的问题

#### 问题 1: pytest count 不一致

**位置**: 第 76 行

```text
python -u -m scripts.quality_gate_counts
quality gate pytest count: 873
```

**分析**:
- 文档声明 873
- 实际运行输出 874
- 与 HANDOFF.md 的 871/874 都不一致

**影响**: 
- 评审人员可能认为测试数量回退了
- 自动化检查可能失败

**建议**: 
- 更新为 874
- 添加注释说明这个数字会随着测试增加而变化

#### 问题 2: 观察输出与实际不符

**位置**: 第 36 行

```text
python -m pytest tests -q
873 passed
```

**分析**:
- 使用了 `-q` 参数（quiet mode）
- 但实际收集到 874 个测试
- 文档说明了这只是为了保持输出紧凑，不是规范形式

**影响**: 
- 轻微，因为文档已经说明了 `-q` 不是规范形式
- 但数字仍然不准确

---

## 必需命令分析

### 命令完整性检查

对比 HANDOFF.md 和 QUALITY_GATES.md 的命令列表：

| 命令 | HANDOFF.md | QUALITY_GATES.md | 一致性 |
|------|------------|------------------|--------|
| `pytest tests` | ✅ | ✅ | ✅ |
| `analysis.s10_failure_trace` | ✅ | ✅ | ✅ |
| `analysis.run_all` | ✅ | ✅ | ✅ |
| `analysis.evidence_manifest` | ✅ | ✅ | ✅ |
| `analysis.evidence_report` | ✅ | ✅ | ✅ |
| `control_center_browser_smoke` | ✅ | ✅ | ✅ |
| `package_smoke` | ✅ | ✅ | ✅ |
| `control_center_integration_audit` | ✅ | ✅ | ✅ |
| `review_authority_lint` | ✅ | ✅ | ✅ |
| `evidence_boundary_lint` | ✅ | ✅ | ✅ |
| `demo_sre_loop` | ✅ | ✅ | ✅ |
| `demo_powered_descent` | ✅ | ✅ | ✅ |
| `demo_catch_phase` | ✅ | ✅ | ✅ |
| `quality_gate_counts` | ✅ | ✅ | ✅ |
| `quality_gate_counts --check` | ✅ | ✅ | ✅ |

**结论**: 命令列表完全一致 ✅

### 命令输出分析

#### 核心输出片段

```text
quality gate pytest count: 874  ← 实际值
artifact_check ok studies=3 files=8  ← 正确
```

**验证结果**:
- `artifact_check ok`: ✅ 通过
- `studies=3`: ✅ 正确（S10, S11, S12）
- `files=8`: ✅ 正确（trace, diagnostics, PNG 等）

#### control-center 输出

文档第 52 行的描述非常详细：

```text
writes control-center-browser-evidence-report.json from saved browser manifests, 
including normal, backend error, frontend_error evidence, manifest_paths, 
manifest_records, and contract_depth metadata
```

**评估**: ⭐⭐⭐⭐⭐
- 明确说明了 3 种错误路径（normal, backend_error, frontend_error）
- 列出了关键的元数据字段
- 说明了 CI 日志中的 provenance lines

#### package_smoke 输出

文档第 55 行的描述同样详细：

```text
package smoke ok; control-center evidence report validates normal, backend error, 
frontend_error browser paths, manifest_paths, non-stale manifest_records, 
positive contract_depth counts, and replays the three source manifests
```

**评估**: ⭐⭐⭐⭐⭐
- 明确了 3 种 manifest 重放路径
- 说明了非陈旧性检查
- 强调了 contract_depth 必须为正数

---

## Targeted Gate Families 分析

### 表格结构评估

**评估**: ⭐⭐⭐⭐⭐

21 个测试家族的分类非常清晰：

1. **事件和合同类** (5 个)
   - `test_event_schema.py`: 运行时事件注册表
   - `test_contracts.py`: 运行时降级/状态/事件合同
   - `test_evidence_contracts.py`: 堆栈合同验证器
   - `test_evidence_contract_*.py`: 4 个合同报告路径测试

2. **证据类** (13 个)
   - `test_evidence_artifacts.py`: 直接 artifact 验证
   - `test_evidence_manifest_*.py`: manifest 形态和生成
   - `test_evidence_report_*.py`: 7 个报告路径测试
   - `test_evidence_trace_report.py`: S10 trace 报告
   - `test_evidence_wrapper_report.py`: S11 wrapper 报告
   - `test_evidence_replay_*.py`: 3 个 S12 replay 报告

3. **控制中心类** (6 个)
   - `test_control_center_browser_*.py`: 5 个浏览器测试
   - `test_control_center.py`: localhost 策略测试

4. **核心功能类** (4 个)
   - `test_sre_control.py`: SRE 适配器和堆栈
   - `test_ekf.py`: EKF Joseph 协方差更新
   - `test_import_graph.py`: 依赖方向
   - `test_package_smoke.py`: 安装包烟雾测试

5. **元测试类** (2 个)
   - `test_quality_gate_counts.py`: 质量门禁计数
   - `test_release_hygiene.py`: 发布卫生
   - `test_synthetic_evidence_boundaries.py`: 合成证据边界
   - `test_failure_trace.py`: Section 10 堆栈历史

### 覆盖范围评估

**评估**: ⭐⭐⭐⭐⭐

测试覆盖非常全面：

1. **单元测试**: EKF, SRE adapters, contracts
2. **集成测试**: control-center, package smoke
3. **证据链测试**: manifest, artifacts, reports
4. **元测试**: quality gates, release hygiene
5. **边界测试**: synthetic evidence boundaries

**特别好的设计**:
- 每个证据报告路径都有对应的测试
- 拆分后的模块都有直接测试和报告路径测试
- 控制中心的 3 种错误路径都有独立测试

---

## Analysis Evidence 分析

### Section 10 证据

**关键指标**:
- `event_visible_fraction`: 事件可见性
- `true_degraded_fraction`: 真实降级比例
- `background_event_fraction`: 背景事件比例
- `injected_window_coverage`: 注入窗口覆盖率
- `replica_bound_active` 预期类型覆盖率: `1.0`（完整覆盖）

**评估**: ⭐⭐⭐⭐⭐
- 指标选择合理，覆盖了关键的证据维度
- 明确了预期值（如 `1.0` 完整覆盖）
- 强调了完整 trace 证据的位置

### Section 11 证据

**关键内容**:
- Catch/SRE wrapper 证据
- 覆盖 3 种场景：feasible quiet solves, total overload, placement-infeasible
- 保持零容量违规

**评估**: ⭐⭐⭐⭐⭐
- 场景覆盖全面
- 约束条件明确（零容量违规）

### Section 12 证据

**关键内容**:
- 合成重放证据
- 保持 nominal background 安静
- 包含预期事件类型（如 `stability_violation`）
- 有界恢复 ticks
- 每个预期事件行都有 operator-action 注释
- 复合多信号窗口保持完整事件类型覆盖

**评估**: ⭐⭐⭐⭐⭐
- 重放证据设计严谨
- 恢复诊断完整
- operator-action 注释是很好的实践

### 证据边界 lint

**关键内容**:
- `PUBLIC_EVIDENCE_BOUNDARY_DOCS` 定义了公开文档表面
- lint 拒绝无限定的生产就绪、官方 SpaceX 实现、生产证明措辞
- 允许明确的否定边界声明（如 "not production proof"）
- 覆盖控制中心交接、事件证据 manifest、堆栈数据合同

**评估**: ⭐⭐⭐⭐⭐
- 边界保护机制设计优秀
- fail-closed 策略正确（新文档必须纳入检查）
- 允许否定声明是合理的

### 堆栈数据合同

**关键内容**:
- `sre_control.stack_data_contract()` 导出单进程研究堆栈的阶段边界
- `production_claim=false` 明确标注
- 包含每个阶段的直接运行时事件类型和路由前缀
- `analysis.evidence_report` 检查生成的 trace 事件是否符合阶段路由

**评估**: ⭐⭐⭐⭐⭐
- 数据合同设计清晰
- 生产声明明确
- 验证机制完整

---

## HTML / Asset Entry 分析

| Entry | Status | 评估 |
|-------|--------|------|
| `docs/V2_Knowledge/knowledge-base.html` | 当前规范 HTML 入口 | ✅ 正确 |
| `docs/knowledge-base.html` | V1 归档快照 | ✅ 正确 |
| `docs/assets/*` | 共享生成资产 | ✅ 正确 |
| `docs/V2_Knowledge/assets/*` | V2 HTML 资产 | ✅ 正确 |

**评估**: ⭐⭐⭐⭐⭐
- V1/V2 版本管理清晰
- 归档策略合理

---

## Current Quality Conclusion 分析

文档第 186-194 行的结论：

```text
- Unit/integration tests: passing in the current workspace.
- Analysis studies: passing in the current workspace.
- Runtime event kinds: closed by registry/docs/counterexample tests.
- Dependency direction: guarded by import-graph tests.
- Remaining useful work is evidence-strengthening, not a known "cannot run" blocker.
```

**评估**: ⭐⭐⭐⭐⭐

这个结论非常好：
1. **明确了当前状态**: 所有测试通过
2. **强调了关键保护**: 运行时事件类型闭合、依赖方向守护
3. **定性了剩余工作**: 证据加强，而非阻塞性问题
4. **避免了过度承诺**: 没有声称"完美"或"生产就绪"

---

## 与其他文档的一致性

### vs HANDOFF.md

| 项目 | QUALITY_GATES.md | HANDOFF.md | 一致性 |
|------|------------------|------------|--------|
| pytest count | 873 | 871 / 874 | ❌ 不一致 |
| 必需命令数 | 14 | 14 | ✅ 一致 |
| 命令列表 | 完全相同 | 完全相同 | ✅ 一致 |
| 证据 studies | 3 | 3 | ✅ 一致 |
| 证据 files | 8 | 8 | ✅ 一致 |

### vs OPUS_REVIEW_PACKET.md

| 项目 | QUALITY_GATES.md | OPUS_REVIEW_PACKET.md | 一致性 |
|------|------------------|----------------------|--------|
| pytest count | 873 | 873 | ✅ 一致 |
| 必需命令 | 14 | 14 | ✅ 一致 |

### vs wiki/review-backlog.md

| 项目 | QUALITY_GATES.md | review-backlog.md | 一致性 |
|------|------------------|-------------------|--------|
| pytest count | 873 | 873 | ✅ 一致 |
| 分析 studies | 12 | 12 | ✅ 一致 |

---

## 改进建议

### 立即改进（阻塞合并）

1. **更新 pytest count**
   - 第 36 行: `873 passed` → `874 passed`
   - 第 76 行: `quality gate pytest count: 873` → `874`

### 短期改进（下一个 PR）

1. **添加命令运行时间估算**
   ```markdown
   | 命令 | 预期时间 | 说明 |
   |------|----------|------|
   | pytest tests | ~30s | 快速单元测试 |
   | analysis.run_all | ~2min | 12 个 studies |
   | control_center_browser_smoke | ~10s | 浏览器启动 |
   ```

2. **添加失败案例示例**
   - 展示当某个门禁失败时的输出
   - 帮助评审人员识别问题

3. **添加依赖关系说明**
   - 哪些命令必须按顺序运行
   - 哪些可以并行运行

### 长期改进（研究方向）

1. **质量门禁可视化**
   - 生成一个 HTML 报告，展示所有门禁的状态
   - 包含历史趋势图

2. **自动化门禁运行器**
   ```bash
   python -m scripts.run_all_quality_gates --report quality-gates-report.html
   ```

---

## 总体评价

**评分**: ⭐⭐⭐⭐⭐ (4.8/5)

**优点**:
- 命令列表规范且完整
- 测试家族分类清晰
- 证据边界说明详细
- 输出示例真实可用
- 结论客观准确

**扣分原因**:
- pytest count 与实际不符（873 vs 874）

**结论**: 
QUALITY_GATES.md 是一份非常优秀的质量门禁文档，除了 pytest count 需要更新外，其他方面都达到了卓越水平。特别是测试家族的分类和证据边界的说明，可以作为最佳实践参考。

---

**分析完成时间**: 2026-05-31  
**下一步**: 分析 OPEN_RISKS.md
