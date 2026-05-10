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
| `status` | string \| null | `T_inv` 的状态码 |
| `cbf_status` | string \| null | CBF 子层状态码 |
| `cbf_slack` | float \| null | CBF 松弛量 |
| `cbf_violations` | array[float] | 每个 barrier 的约束值 |
| `cbf` | object | 原始 CBF payload，已做 JSON-safe 清洗 |

## 不变式

1. `state` 和 `next_state` 长度固定为 6。
2. `u_nn` 和 `u_safe` 长度固定为 2。
3. `step` 只在 `run()` 场景下递增。
4. `t` 与 `dt` 一致，且 `t = step * dt`。
5. 任何非有限数都会在写入前被清洗成 `null`，保证 JSONL 严格可解析。
6. `cbf_status` 至少覆盖 `nom_ok` / `qp_ok` / `fallback_brake`。

## 使用位置

- [`planner.py`](../auto_decide/planner.py)
- [`architecture.html`](./architecture.html)
- [`codex-handoff.md`](./codex-handoff.md)
