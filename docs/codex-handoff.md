# Codex Handoff

> 分支：`auto-decide-session`
> 范围：`auto-decide/` 的架构文档、trace 契约、模块边界、SRE 迁移和下一步实现

## 当前状态

这轮整理后，auto-decide 已经从“文献落地”推进到“可交接的工程体系”：

- `README.md` 已串起主入口。
- `docs/knowledge-base.html` 是总览。
- `docs/deep-dive.html` 是算法级拆解。
- `docs/equations-digest.html` 是 35 个方程的逐条吃透。
- `docs/sre-adaptation.html` 是 SRE 迁移映射。
- `docs/architecture.html` 是详细架构页，按 architecture / requirements / task breakdown / refine 组织。
- `docs/trace-schema.md` 定义了 JSONL trace 契约。
- `auto_decide/trace.py` 统一构造 trace 记录，供 `planner` 回放和审计。

当前最重要的事实是：

1. `planner.step()` 仍然是唯一北向入口。
2. `trace` 已经从“调试输出”变成正式契约。
3. 软建议和硬边界已经被文档与代码同时分层。

## 先读顺序

下一轮 Codex 如果要接手，建议按这个顺序读：

1. [README.md](../README.md)
2. [docs/knowledge-base.html](./knowledge-base.html)
3. [docs/architecture.html](./architecture.html)
4. [docs/trace-schema.md](./trace-schema.md)
5. [docs/deep-dive.html](./deep-dive.html)
6. [docs/equations-digest.html](./equations-digest.html)
7. [docs/sre-adaptation.html](./sre-adaptation.html)

## 9 个核心模块

| 模块 | 职责 | 边界 | 主要输出 |
| --- | --- | --- | --- |
| `graph.py` | 观测场景并构造意图图 | 只做离散图层，不做控制决策 | 边、权重、邻接关系 |
| `dynamics.py` | 传播车辆状态与摩擦约束 | 只负责状态演化，不负责安全证明 | `next_state`、可行性 |
| `potential.py` | 给出软引导方向 | 只给建议，不给硬约束 | flow direction、nominal hint |
| `lyapunov.py` | 监控速度跟踪稳定性 | 只看稳定，不代替安全门 | `V`、`dV_dt` |
| `reachable.py` | 估计前向可达集和死区 | 只做近似前瞻，不做精确证明 | hull、dead-zone flag |
| `game.py` | 把不确定性压成风险缓冲 | 不改数学核心，只改风险判断 | belief margin、worst-case hint |
| `cbf.py` | 把名义动作折叠进可行域 | 这是硬门，不是 loss | `u_safe`、violations、fallback |
| `invariant.py` | 实现 `T_inv` 再包一层兜底 | 不直接暴露执行器 | `status`、`trace`、emergency brake |
| `planner.py` | 唯一北向入口 | 外部不能绕过它直达执行器 | `u_safe`、`next_state`、`trace.jsonl` |

补充说明：`trace.py` 不是第 10 个核心数学模块，它是跨模块的序列化和契约层。

## 35 个方程落点

按模块分组后，35 个方程的代码锚点是：

- `E-01 ~ E-05` -> `graph.py`
- `E-06 ~ E-10` -> `dynamics.py`
- `E-11 ~ E-16` -> `potential.py`
- `E-17 ~ E-20` -> `lyapunov.py`
- `E-21 ~ E-22` -> `reachable.py`
- `E-23 ~ E-25` -> `game.py`
- `E-26 ~ E-33` -> `cbf.py`
- `E-34 ~ E-35` -> `invariant.py` / `planner.py`

下一轮继续深挖时，优先看三件事：

1. 每条方程的符号、直觉、推导、边界、数值坑、代码锚点是否闭环。
2. `CBF -> T_inv -> planner.step()` 这条硬路径是否真的不可绕过。
3. `trace` 是否足以支撑 review、复现和 benchmark。

## SRE 映射

这套结构迁移到 SRE 时，不是换词，而是换语义落点：

- `graph.py` -> 故障相关性图 / 服务依赖图
- `dynamics.py` -> timeout budget chain / 状态传播模型
- `potential.py` -> 调度偏置 / 风险压力
- `lyapunov.py` -> bounded burn rate
- `reachable.py` -> capacity forecast / admission window
- `game.py` -> uncertainty margin / worst-case reasoning
- `cbf.py` -> admission controller
- `invariant.py` -> change guard / policy guard
- `planner.py` -> control plane
- `trace.py` -> observability contract

迁移原则只有一句：

**迁移机制，不迁移数学本体。**

## 不变式与风险

### 必守不变式

- 软建议和硬边界必须分层。
- `planner.step()` 必须是唯一出口。
- `CBF` 和 `T_inv` 不能退化成普通损失项。
- 单位必须统一，不能混用尺度。
- `trace` 必须覆盖状态、控制、稳定性、安全性和状态码。

### 主要风险

- 名义策略过强，盖住硬边界。
- CBF 相对阶处理不正确，导致“看起来安全、实际穿模”。
- 兜底逻辑过宽，掩盖真实问题。
- SRE 映射只翻译字面名词，不翻译机制。
- 文档与代码锚点不同步，导致 review 断链。

## 下一步

1. 把 `trace schema` 当成正式契约继续收紧，字段只增不乱改。
2. 继续补 `CBF` 的相对阶和 braking-distance 语义。
3. 做结构化回归：结构版 vs e2e 版。
4. 再往前推 SRE control plane 的抽象。
5. 所有新改动都回到 `README.md` / `knowledge-base.html` / `architecture.html` 这三条入口。

## 给下一轮 Codex 的话

先读这几份：

- [README.md](../README.md)
- [knowledge-base.html](./knowledge-base.html)
- [architecture.html](./architecture.html)
- [trace-schema.md](./trace-schema.md)

再按需下钻：

- [deep-dive.html](./deep-dive.html)
- [equations-digest.html](./equations-digest.html)
- [sre-adaptation.html](./sre-adaptation.html)

如果要继续做代码层实现，建议顺序是：

1. `types.py`
2. `graph.py`
3. `dynamics.py`
4. `cbf.py`
5. `invariant.py`
6. `planner.py`

这个顺序能最大限度避免“先把聪明层做好，结果硬边界还没站稳”的返工。
