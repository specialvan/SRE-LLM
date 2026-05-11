# Trace Schema

`planner.run()` 会输出一条一行的 JSONL trace。这个 schema 是给 review、回放、benchmark 和 SRE 迁移共用的。

## 版本

- `schema_version`: 当前为 `1.0`

## 字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `schema_version` | string | trace schema 版本 |
| `step` | int \| null | 控制循环步号 |
| `t` | float \| null | 仿真时间，`step * dt` |
| `dt` | float | 本步时间步长 |
| `state` | array[float] | 当前状态向量 |
| `next_state` | array[float] | 执行 `u_safe` 后的下一状态 |
| `u_nn` | array[float] | 名义策略输出 |
| `u_safe` | array[float] | 安全门之后的输出 |
| `min_dist` | float | 当前状态下的最小障碍距离 |
| `V` | float \| null | Lyapunov 值 |
| `dV_dt` | float \| null | Lyapunov 导数 |
| `status` | enum \| null | `T_inv.apply` 的状态码之一：<br>`stable`：首次即满足指数衰减目标；<br>`relaxed_exp`：松弛后满足指数衰减目标；<br>`relaxed`：松弛后满足 `dV_dt <= tol`；<br>`non_increasing`：首次即满足 `dV_dt <= tol` 但未达指数衰减；<br>`emergency_brake`：兜底刹停 |
| `cbf_status` | enum \| null | `CBFQPFilter.filter` 的状态码之一：<br>`nom_ok`：名义命令直接满足所有 barrier；<br>`qp_ok`：网格搜索找到非平凡可行解；<br>`fallback_brake`：搜索失败，退化为刹停 |
| `cbf_slack` | float \| null | CBF 松弛量 |
| `cbf_violations` | array[float] | 每个 barrier 的约束值 |
| `cbf` | object | 原始 CBF payload，已做 JSON-safe 清洗 |

## 不变式

1. `state` 和 `next_state` 长度固定为 6。
2. `u_nn` 和 `u_safe` 长度固定为 2。
3. `step` 只在 `run()` 场景下递增。
4. `t` 与 `dt` 一致，且 `t = step * dt`。
5. 任何非有限数都会在写入前被清洗成 `null`，保证 JSONL 严格可解析。
6. `status` 必须属于 `auto_decide.trace.PLANNER_STATUS_VALUES`。
7. `cbf_status` 必须属于 `auto_decide.trace.CBF_STATUS_VALUES`。

## 使用位置

- [`planner.py`](../auto_decide/planner.py)
- [`architecture.html`](./architecture.html)
- [`codex-handoff.md`](./codex-handoff.md)


## Schema Evolution（AI-04）

trace schema 的演进规则如下，**任何 agent 在修改 `auto_decide/trace.py` 之前必须先读这一节**。

### 版本号含义

`schema_version` 采用 `MAJOR.MINOR`：

- **MINOR bump**（`1.0 → 1.1`）：只允许**新增**字段，或把 optional 字段的取值范围扩大（例如给 `status` 加一个新的枚举值）。所有 v1.x 的读取器必须保持能解析 v1.x 的任何版本（忽略未知字段）。
- **MAJOR bump**（`1.x → 2.0`）：以下操作之一必须触发 MAJOR：
  - 删除任何已有字段；
  - 修改已有字段的类型或单位；
  - 修改已有字段语义（含 enum 值的含义变更）；
  - 调整 `state` / `u_nn` / `u_safe` 等固定长度数组的维度；
  - 把 optional 字段变为 required，或反过来。

### 下游读取器的契约

任何消费 trace 的 agent / 工具（可视化、benchmark 聚合、离线分析）都必须：

1. **第一步读 `schema_version`**；不识别的 MAJOR 必须拒绝解析并记日志，而不是静默忽略。
2. 对未知字段**静默跳过**（不崩），这是 forward compatibility 的关键。
3. 不要假设字段顺序。

### 违反举例（不要做）

- ❌ 把 `V` 字段的单位从"能量标量"改为"归一化 0-1"而不 bump MAJOR；
- ❌ 把 `cbf_violations` 从 `array[float]` 改成 `array[{barrier_id, value}]` 而不 bump MAJOR；
- ❌ 删除 `min_dist` 字段（哪怕"没人用"）而不 bump MAJOR。

### 实施要求

- 每次 bump 必须同步修改：
  1. `auto_decide/trace.py::TRACE_SCHEMA_VERSION`；
  2. 本文件的字段表；
  3. `docs/codex-handoff.md` 的 "trace 契约" 段；
  4. `docs/V2_Knowledge/state.json` 的 `code.contracts.trace_schema_version`；
  5. PR 描述里附"迁移指南"段，说明下游怎么 adapt。
- MAJOR bump 必须同时保留旧版写入器一段时间（推荐 2 个 review 轮次），便于对照。

### INV-C-TRACE

该章节所描述的规则即 [INV-C-TRACE](./claude-review/03-invariants-catalog.md#inv-c-trace) 的具体化。
