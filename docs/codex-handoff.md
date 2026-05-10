# Codex Handoff

> 基线分支：`auto-decide-session`  
> 目标：把 auto-decide 的数学骨架、工程边界、SRE 迁移路径整理成下一轮可直接接手的说明书。

## 当前状态

这套工作已经从“文献复述”推进到“可交接的工程文档集”：

- `README.md` 已经把主入口文档串起来了。
- `docs/knowledge-base.html` 是总览型知识库。
- `docs/deep-dive.html` 是模块级深挖。
- `docs/equations-digest.html` 是 35 个方程的逐条拆解。
- `docs/sre-adaptation.html` 是迁移到 SRE 的模式映射。
- `docs/trace-schema.md` 是 JSONL trace 的字段契约。
- `docs/architecture.html` 是这轮新增的详细架构文档，按 architecture / requirements / task breakdown / refine 组织。

## 9 个核心模块

1. `graph.py`
   - 职责：把场景观测变成带权有向意图图。
   - 边界：只做离散图层，不做控制决策。
   - 输出：边、权重、邻接关系。

2. `dynamics.py`
   - 职责：传播车辆状态，处理 jerk / bicycle / clamp。
   - 边界：只负责状态演化，不负责安全证明。
   - 输出：next_state、feasibility。

3. `potential.py`
   - 职责：给出软引导方向。
   - 边界：只给建议，不做硬约束。
   - 输出：flow direction / nominal policy hint。

4. `lyapunov.py`
   - 职责：监控速度跟踪稳定性。
   - 边界：只看稳定，不代替安全门。
   - 输出：`V`、`dV_dt`。

5. `reachable.py`
   - 职责：估计前向可达集和死区。
   - 边界：做近似前瞻，不做精确证明。
   - 输出：hull、dead-zone flag。

6. `game.py`
   - 职责：把不确定性、对抗性和 belief 压成可用的缓冲语义。
   - 边界：不改数学核心，只改风险判断。
   - 输出：belief margin、worst-case hint。

7. `cbf.py`
   - 职责：把名义动作折叠进安全可行域。
   - 边界：这是硬门，不是 loss。
   - 输出：`u_safe`、violations、fallback 状态。

8. `invariant.py`
   - 职责：实现 `T_inv`，把 CBF 结果再包一层有限步兜底。
   - 边界：只做控制不变集算子，不直接暴露执行器。
   - 输出：`status`、`trace`、紧急制动结果。

9. `planner.py`
   - 职责：唯一北向入口，把所有模块串成一条可审计控制链。
   - 边界：外部不能绕过它直接调用执行器。
   - 输出：`u_safe`、`next_state`、`trace.jsonl`。

## 35 个方程的落点

- `E-01 ~ E-05` -> `graph.py`
- `E-06 ~ E-10` -> `dynamics.py`
- `E-11 ~ E-16` -> `potential.py`
- `E-17 ~ E-20` -> `lyapunov.py`
- `E-21 ~ E-22` -> `reachable.py`
- `E-23 ~ E-25` -> `game.py`
- `E-26 ~ E-33` -> `cbf.py`
- `E-34 ~ E-35` -> `invariant.py` / `planner.py`

下一轮如果要继续深挖，优先盯住三件事：

1. 每个方程的符号、直觉、推导、边界、数值坑、代码锚点是否闭环。
2. `CBF -> T_inv -> planner.step()` 这条硬路径是否真的不可绕过。
3. `trace` 是否足以支撑 review、复现和 benchmark。

## SRE 映射

这套架构迁移到 SRE 时，不是换名词，而是换语义落点：

- 意图图 `graph.py` -> 故障相关性图 / 服务依赖图
- 动力学 `dynamics.py` -> timeout budget chain / 状态传播模型
- 势能场 `potential.py` -> 调度偏置 / 风险压力
- Lyapunov `lyapunov.py` -> bounded burn rate
- 可达集 `reachable.py` -> capacity forecast / admission window
- CBF `cbf.py` -> admission controller
- `T_inv` `invariant.py` -> change guard / policy guard
- `planner.py` -> control plane

原则只有一句：**迁移机制，不迁移数学本体。**

## 风险面与不变式

### 必守不变式

- 软建议和硬边界必须分层。
- `planner.step()` 必须是唯一出口。
- `CBF` 和 `T_inv` 不能被降级成普通损失项。
- 单位必须统一，不能混用尺度。
- `trace` 必须覆盖状态、控制、稳定性、安全性和状态码。

### 主要风险

- 名义策略过强，盖住硬边界。
- CBF 相对阶处理不正确，导致“看起来安全、实际穿模”。
- 兜底逻辑过宽，掩盖真实问题。
- SRE 映射只翻译字面名词，不翻译机制。
- 文档与代码锚点不同步，导致 review 断链。

## 下一步建议

1. 先把 `trace schema` 固化成正式契约，已落到 `docs/trace-schema.md` 和 `auto_decide/trace.py`。
2. 再补 `CBF` 的相对阶和 braking-distance 语义。
3. 接着做结构化回归：结构版 vs e2e 版。
4. 然后才开始更大范围的 SRE 控制平面抽象。
5. 所有新改动都要回到 `README.md` / `knowledge-base.html` / `architecture.html` 这三条入口上。

## 交接给下一轮 Codex 的话

请先从这三份文档开始：

- [README.md](../README.md)
- [knowledge-base.html](./knowledge-base.html)
- [trace-schema.md](./trace-schema.md)
- [architecture.html](./architecture.html)

再按需下钻：

- [deep-dive.html](./deep-dive.html)
- [equations-digest.html](./equations-digest.html)
- [sre-adaptation.html](./sre-adaptation.html)

如果要继续做代码层实现，优先顺序是：

1. `types.py`
2. `graph.py`
3. `dynamics.py`
4. `cbf.py`
5. `invariant.py`
6. `planner.py`

这条顺序能最大限度避免“先把聪明层做好，结果硬边界还没站稳”的返工。
