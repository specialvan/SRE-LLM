# Codex Handoff：auto-decide

> 分支：`auto-decide-session`  
> 工作目录：`D:\workspace\SRE-LLM\auto-decide`  
> 范围：架构、需求、任务拆解、方程锚点、SRE 迁移、reviewer 不变式与下一轮 refine  
> 更新时间：2026-05-12（v2 · Claude review 完成后）

> 🔴 **下一轮开工前请先读 [docs/claude-review/README.md](./claude-review/README.md)**。
> Claude 的 review 指出了 benchmark 下 `planner_emergency_rate = 42.5%` 严重违反 SLO（应 &lt; 0.5%）——
> 这是当前最高优先级任务。所有需要做的事都列在 [action items](./claude-review/05-action-items.md) 里，开工按编号走。

## 最新进展 · 2026-05-12 之后

本次迭代没有改代码（19/19 tests 仍绿），但完成了两块"给下一轮 agent 的基础建设"：

**① 完整的 Claude Review Pack**（`docs/claude-review/` · 15 文件 · ~160 KB）
- 2 个 P0 finding / 3 个 P1 / 7 个 P2；
- 14 条 action items（AI-01 ~ AI-14）；
- 5 个可 cherry-pick 的 patch（含完整 `PredictiveBrakePolicy` 实现骨架）；
- 29 条不变式 · 9 模块 + trace 的完整 pre/post 合约；
- 5 张新架构视图（类型流 / 场景矩阵 / 失败决策树 / 时延预算 / Codex 心智模型）；
- Codex 指令清单（10 DO + 10 DON'T + 15 个预期 PR 序列）；
- **canonical benchmark baseline**（n=50 seed=0，建立在 `08-benchmark-log.md`）。

**② 统一知识库入口**（`docs/V2_Knowledge/`）
- 给下一轮接手的 agent（人 / Codex / 其它 LLM）提供<strong>一个入口</strong>——不用翻 4 份文档；
- 含当前进度 state JSON，机器可直接读；
- 按"5 分钟 / 30 分钟 / 半天 / 长期"分层导航。

**③ Claude 亲手清理 4 项 P1 易改项**（2026-05-12 12:00 补丁）
- **AI-03a**：`docs/architecture.html` title mojibake `路` → `·` 修复；
- **AI-03c**：`summaizer/` 目录 → `.local-artifacts/`，`.gitignore` 新增对应条目；
- **AI-04**：`trace-schema.md` 与 `benchmark-metrics.md` 各加 "Schema Evolution" 节（对应 INV-C-TRACE / INV-C-BENCH）；
- **AI-09**：`examples/compare_e2e_vs_structural.py` 标注 `_pure_e2e_step` 为 INV-G2 合法例外。

剩余 10 项由下一轮 Codex 推进。P0 仅剩 AI-01 / AI-02；P1 仅剩 AI-03b。

**代码层**：本轮 Codex 交付的 trace / benchmark 契约、CBF 测试矩阵均保留；本轮 Claude 补丁仅涉及 docstring / `.gitignore` / 目录重命名，不改函数行为，19/19 tests 仍绿。

## 当前状态

auto-decide 已经从"论文公式落地"推进到"可被 Codex / reviewer / SRE 接手的工程知识库"。

当前主入口（按优先级顺序）：

| 优先级 | 文件 | 职责 |
| --- | --- | --- |
| ⭐ 最高 | [V2_Knowledge/index.html](./V2_Knowledge/index.html) | **V2 知识库统一入口**（为下一轮 agent 设计） |
| 🔴 高 | [claude-review/README.md](./claude-review/README.md) | Claude 评审包入口，含 action items |
| 🔴 高 | [claude-review/05-action-items.md](./claude-review/05-action-items.md) | 14 条任务清单（P0/P1/P2） |
| 🔴 高 | [claude-review/07-codex-directives.md](./claude-review/07-codex-directives.md) | 开工前必读的 DO/DON'T |
| 高 | [README.md](../README.md) | 工程入口，论文结构和代码模块的一一映射 |
| 高 | [architecture.html](./architecture.html) | Detailed Architecture |
| 高 | [trace-schema.md](./trace-schema.md) | JSONL trace 契约 |
| 高 | [benchmark-metrics.md](./benchmark-metrics.md) | benchmark metrics JSON 契约 |
| 中 | [knowledge-base.html](./knowledge-base.html) | SRE + Codex 评审知识库总览（v1） |
| 中 | [deep-dive.html](./deep-dive.html) | 9 个核心模块的算法级机制拆解 |
| 中 | [equations-digest.html](./equations-digest.html) | E-01 到 E-35 的方程手册 |
| 中 | [sre-adaptation.html](./sre-adaptation.html) | 自动驾驶机制迁移到 SRE 的模式库 |
| 参考 | [PR-REQUIREMENTS.md](../PR-REQUIREMENTS.md) | 把论文叙述拆成 PR 级功能需求 |
| 参考 | [FORMULA_MAP.md](./FORMULA_MAP.md) | 公式到代码的追踪地图 |
| 参考 | [DESIGN.md](./DESIGN.md) | 设计原则和工程裁剪说明 |

代码侧当前核心事实：

1. `planner.step()` 是唯一北向入口。
2. `planner.run()` 负责产生 JSONL trace。
3. `auto_decide/trace.py` 已把 trace 从调试输出提升为稳定契约（v1.0）。
4. `CBF -> T_inv -> planner.step()` 是硬安全路径，不能被名义策略绕过。
5. 软建议、稳定性、屏障约束、兜底降级已经在代码和文档中分层。
6. `examples/compare_e2e_vs_structural.py` 已支持 `--metrics-out` 输出结构化 benchmark JSON。
7. **Benchmark 实测揭示 `planner_emergency_rate = 42.5%`，违反 SLO，待 AI-02 修复**。

当前工作区提醒：

- `summaizer/` 目录处于未跟踪状态，包含可视化 HTML / zip / gif 素材。
- 本次 handoff 不纳入该目录，避免把未确认的二进制和派生产物推入仓库。
- 若后续需要提交展示包，应先决定放在 `docs/`、`examples/` 还是 release artifact。

## 模块梳理

### 1. `graph.py`：交互意图图

机制：把交通参与者抽象为时变加权有向图 `G_I=(V_I,E_I)`。边权不是简单距离，而是距离、相对朝向、意图冲突的组合。

职责：

- 维护 agent 节点。
- 计算交互边权。
- 给后续势能场、博弈层和 planner 提供离散交互结构。

边界：

- 不做连续动力学积分。
- 不直接给控制量。
- 不负责安全证明。

review 关注：

- 边权是否随距离单调衰减。
- 意图冲突是否只影响风险权重，不直接越权修改动作。
- 大量 agent 下是否仍能控制计算预算。

### 2. `dynamics.py`：连续状态传播

机制：用自行车模型和 jerk 控制传播状态 `x=(px,py,psi,v,a,mu)`。

职责：

- 定义车辆状态演化 `dot{x}=f(x,u)`。
- 执行 RK4 积分。
- 用 `mu*g` 限制物理可行加速度。

边界：

- 不判断目标策略是否好。
- 不判断障碍是否安全。
- 只负责“这个控制量作用到状态后会怎样”。

review 关注：

- 单位是否一致。
- `mu` 是否正确影响制动能力。
- dt 变化时是否有稳定性回归。

### 3. `potential.py`：软引导势能场

机制：把目标吸引、障碍排斥、规则偏置合成 `Phi(x)`，名义策略沿 `-grad Phi` 方向移动。

职责：

- 给出候选动作方向。
- 体现“想去哪”和“偏好怎么走”。
- 提供可替换的 nominal policy 入口。

边界：

- 只能输出软建议。
- 不能绕过 CBF。
- 不能把 penalty 当硬约束。

review 关注：

- 势能项是否可解释。
- 是否出现“软 penalty 代替硬 safety”的退化。
- 输出是否被 trace 记录为 `u_nn`。

### 4. `lyapunov.py`：稳定性监视

机制：用 Lyapunov 函数监控速度跟踪误差的能量是否受控。当前工程裁剪中，Lyapunov 主要看稳定性，不再混入障碍距离。

职责：

- 计算 `V`。
- 估计 `dV_dt`。
- 给 `T_inv` 提供稳定性证据。

边界：

- 不替代 CBF 做碰撞安全。
- 不独立产生最终控制量。
- 不应该把稳定性和距离安全混成一个黑盒分数。

review 关注：

- `V` 的定义是否仍为正定。
- `dV_dt` 的数值估计是否对 dt 敏感。
- trace 中 `V` / `dV_dt` 是否足够解释动作改写。

### 5. `reachable.py`：前向可达集和死区

机制：采样控制序列并前向积分，估算 `R(x0,T)`；再用近似 hull / margin 判断威胁是否进入不可规避区域。

职责：

- 估计未来可达范围。
- 标记逻辑死区。
- 给 planner 和 reviewer 提供前瞻安全证据。

边界：

- 目前是近似，不是形式化证明。
- 不应直接替代 CBF。
- 采样预算必须被限制。

review 关注：

- `T`、`n`、`dt` 是否和实时预算匹配。
- 低摩擦场景下可达集是否合理缩小。
- dead-zone flag 是否进 trace。

### 6. `game.py`：不确定性和最坏情况缓冲

机制：把他车意图的不确定性压成 safety buffer。熵越高、置信越分散，planner 越保守。

职责：

- 维护 belief / intent uncertainty。
- 输出 worst-case margin。
- 给 CBF / planner derating 信号。

边界：

- 不改变动力学方程。
- 不直接求纳什均衡的完整解析解。
- 不应该把概率高的意图当作唯一真实世界。

review 关注：

- 高熵是否扩大 buffer。
- buffer 是否可解释、可配置、可 trace。
- 最坏情况策略是否过度保守。

### 7. `cbf.py`：控制屏障函数硬门

机制：用 `h(x)>=0` 与 `dot{h}+alpha h>=0` 把名义动作投影回安全可行域。工程里保留两类 barrier：几何距离屏障和 braking-distance 屏障。

职责：

- 过滤 `u_nn`。
- 输出 `u_safe` 或 fallback。
- 记录 `cbf_status`、`cbf_slack`、`cbf_violations`。

边界：

- 这是硬门，不是 loss。
- 不负责生成聪明策略。
- 不应该悄悄放过不可行 nominal action。

review 关注：

- braking-distance barrier 是否考虑 `v*tau`、`v^2/(2*a_brake(mu))`。
- 相对阶问题是否被清楚解释。
- QP 不可行时是否进入可审计 fallback。

### 8. `invariant.py`：`T_inv` 兜底算子

机制：把 CBF 后的动作再送入控制不变集算子，检查稳定性；如果不满足，则逐级修正或 emergency brake。

职责：

- 包装 Lyapunov 检查。
- 执行有限步修正。
- 提供最终兜底状态码。

边界：

- 不对外暴露绕过 planner 的执行器接口。
- 不吞掉错误。
- 不能让 fallback 成为常态而无人发现。

review 关注：

- status code 的合法集合见 [trace-schema.md](./trace-schema.md) 的枚举表。
- emergency brake 是否进入 trace。
- fallback rate 是否可作为 SLI。

### 9. `planner.py`：唯一编排入口

机制：把图、动力学、势能、博弈、CBF、T_inv、trace 串成单步控制循环。

职责：

- 接收观测。
- 产出 `u_safe` 和 `next_state`。
- 写入可回放 trace。

边界：

- 外部调用者不应绕过 `planner.step()`。
- planner 只编排，不把所有数学逻辑塞进一个函数。
- trace schema 变更必须同步文档。

review 关注：

- `u_nn -> CBF -> T_inv -> u_safe` 顺序是否稳定。
- `next_state` 是否由同一 dynamics 模型产生。
- `planner.run()` 的 JSONL 是否严格可解析。

补充：`trace.py` 是横切契约层，不算第 10 个核心数学模块，但它是 reviewer 和 SRE 迁移的关键资产。

## 方程深拆

完整细节在 [equations-digest.html](./equations-digest.html)。
下一轮继续深挖时，每个方程都要保持六段式：

1. 符号：变量、单位、张量 / 标量形状。
2. 直觉：它在系统里解决什么问题。
3. 推导：从论文表达转成工程表达的路径。
4. 边界：什么时候不能这么用。
5. 数值坑：dt、单位、除零、饱和、不可行 QP、低摩擦。
6. 代码锚点：模块、函数、测试、trace 字段。

当前方程落点：

| 范围 | 模块 | reviewer 重点 |
| --- | --- | --- |
| E-01 ~ E-05 | `graph.py` | 图权重、意图冲突、邻接表示 |
| E-06 ~ E-10 | `dynamics.py` | 状态向量、动力学、摩擦约束、积分 |
| E-11 ~ E-16 | `potential.py` | 势能项、梯度、受限流、soft hint 边界 |
| E-17 ~ E-20 | `lyapunov.py` | `V`、`dV_dt`、稳定性和安全性的职责分离 |
| E-21 ~ E-22 | `reachable.py` | 可达集、死区、采样预算和 hull 近似 |
| E-23 ~ E-25 | `game.py` | belief entropy、worst-case buffer、derating |
| E-26 ~ E-33 | `cbf.py` | barrier、相对阶、braking distance、QP fallback |
| E-34 ~ E-35 | `invariant.py` / `planner.py` | `T_inv`、最终安全动作、trace evidence |

特别要继续盯的方程：

- CBF 的 `dot{h}+alpha h>=0`：几何距离屏障对 jerk 驱动是相对阶 2，必须依赖 braking-distance barrier 或更高阶 CBF。
- braking-distance barrier：低摩擦 `mu` 会显著放大停车距离，不能用常数制动能力。
- Lyapunov `V`：当前主要用于速度跟踪稳定性，避免再把障碍距离塞回 V 里导致职责混淆。

## SRE 映射

迁移原则：

**迁移机制，不迁移数学本体。**

| auto-decide 模式 | 自动驾驶语义 | SRE 语义 | 可落地组件 |
| --- | --- | --- | --- |
| `graph.py` | 车辆交互图 | 服务依赖图 / 故障传播图 | topology graph、blast-radius graph |
| `dynamics.py` | 状态传播 | timeout / queue / retry 传播 | latency budget simulator |
| `potential.py` | 软引导势能 | 调度偏置 / 成本偏好 | routing preference、placement score |
| `lyapunov.py` | 稳定性能量 | bounded burn rate | error-budget Lyapunov monitor |
| `reachable.py` | 前向可达集 | 容量可达窗口 | capacity forecast、admission window |
| `game.py` | 意图不确定性 | 观测不完整时 derating | confidence-aware capacity derating |
| `cbf.py` | 安全屏障 | admission controller | deploy / traffic / queue guard |
| `invariant.py` | 控制不变集 | change guard / rollback guard | release invariant operator |
| `planner.py` | 决策控制面 | SRE control plane | policy orchestrator |
| `trace.py` | 审计记录 | observability contract | JSONL / OpenTelemetry event schema |

SRE 迁移时不要说“服务也有 Lyapunov 方程”这种空话。
应该说：

- 把错误预算当作稳定性能量。
- 把容量上界当作安全集合。
- 把准入控制当作 CBF。
- 把发布动作当作 `u_nn`。
- 把 change guard 当作 `T_inv`。
- 把每次限流 / 熔断 / 回滚写成可回放 trace。

## Architecture

架构页已经按四层组织：

1. Architecture：Sense / model layer、Safety layer、Orchestration layer。
2. Requirements：traceability、safety、performance、reviewability、SRE portability。
3. Task Breakdown：把文档、代码、trace、测试和 SRE 迁移拆成可执行任务。
4. Refine：用 schema、benchmark、failure matrix 和 SRE adapter 做迭代。

工程原则：

- 名义策略可以替换，安全门不能绕过。
- trace 字段可以新增，不能破坏既有字段。
- 文档和代码锚点必须同步。
- benchmark 必须同时看安全、舒适度、耗时和 fallback rate。
- SRE adapter 先做只读解释，再做准入控制。

## Requirements

### R1：安全控制链路

必须满足：

- 所有动作都经过 `CBFQPFilter`。
- 所有动作都经过 `ControlInvariantOperator`。
- CBF 不可行必须记录状态码。
- T_inv fallback 必须可审计。

验收：

- 测试覆盖 nominal action 被修正的场景。
- trace 能看到 `u_nn` 和 `u_safe` 的差异。

### R2：trace 契约

必须满足：

- `schema_version` 固定存在。
- 非有限数写入前清洗成 `null`。
- 状态向量和控制向量长度固定。
- `status` 与 `cbf_status` 的合法集合以 [trace-schema.md](./trace-schema.md) 为准。

验收：

- `tests/test_trace.py` 通过。
- `planner.run()` 输出的 JSONL 可以逐行 `json.loads`。

### R3：reviewer 可追踪

必须满足：

- 每个核心方程能找到代码锚点。
- 每个硬门能找到测试。
- 每个 fallback 能找到 trace 字段。

验收：

- [FORMULA_MAP.md](./FORMULA_MAP.md)、[equations-digest.html](./equations-digest.html)、[trace-schema.md](./trace-schema.md) 三者一致。

### R4：SRE 可迁移

必须满足：

- 不把自动驾驶单位原样搬进 SRE。
- 每个模式都讲清“机制等价”。
- adapter 第一阶段只读，不直接执行生产变更。

验收：

- SRE 文档能对应到 admission、derating、burn rate、change guard、trace contract。

### R5：benchmark metrics 契约

必须满足：

- benchmark 既能打印人类可读摘要，也能输出 JSON。
- JSON 记录参数、两条链路 summary、差值和场景列表。
- 指标同时覆盖安全、可用性、舒适度和实时性。
- fallback / emergency 指标不能重复计数成一个模糊比例。

验收：

- `tests/test_benchmark_metrics.py` 通过。
- `python -m examples.compare_e2e_vs_structural --metrics-out <path>` 能写出严格 JSON。

## Task Breakdown

### P0：交接稳定化

1. 维持 [codex-handoff.md](./codex-handoff.md) 为最新入口。
2. 所有新文档回链到 README。
3. 所有 trace 字段变化同步 [trace-schema.md](./trace-schema.md)。
4. 未确认的展示资产不要混入代码提交。

### P1：CBF 相对阶继续收紧

1. 已补 `BrakingDistanceBarrier` 速度和低摩擦膨胀测试。
2. 已补低摩擦下 nominal acceleration 被改写成 brake 的测试。
3. 继续加近距离、高速、jerk 饱和场景。
4. 把 relative-degree limitation 写进 reviewer checklist。

### P2：benchmark 结构化回归

1. 已扩展 `examples/compare_e2e_vs_structural.py` 的 CLI 参数：`--n`、`--seed`、`--horizon`、`--dt`。
2. 已支持 `--metrics-out` 输出 JSON。
3. 已输出 collision rate、clearance、jerk、step time、CBF status、planner status。
4. 下一步把结果接入可视化 HTML，而不是手填收益。

### P3：SRE adapter 原型

1. 定义 SRE 输入：服务图、SLO、error budget、capacity、release action。
2. 定义 SRE 输出：allow / derate / block / rollback suggestion。
3. 先实现只读解释器，不直接执行。
4. trace 字段复用 auto-decide 的结构思想。

### P4：review pack

1. 决定 `summaizer/` 是否作为 release artifact。
2. 若要入仓，拆出源文件和派生产物。
3. 避免同时提交 zip 和解压目录，除非明确需要离线包。

## Refine

下一轮 refine 不要泛泛补文档，而要围绕四个问题推进：

1. 哪个 hard gate 最容易误判？
2. 哪个 trace 字段最能解释动作改写？
3. 哪个 benchmark 场景最能暴露结构版和 e2e 版差异？
4. 哪个 SRE 模式最适合先落地成只读 advisor？

推荐循环：

```text
新增失败场景
  -> 跑 benchmark
  -> 看 trace
  -> 定位模块边界
  -> 修代码或修契约
  -> 更新 architecture / equations / handoff
```

不要做：

- 为了让 demo 好看而调宽安全边界。
- 让 fallback 静默发生。
- 把 CBF 写成 penalty。
- 直接把 SRE adapter 做成自动执行器。

## 风险与不变式

### 必守不变式

- `planner.step()` 是唯一执行入口。
- `u_nn` 永远只是候选动作。
- `u_safe` 必须来自 CBF + T_inv 之后。
- CBF / T_inv 的失败必须进入 trace。
- `trace` 是 review、回放、benchmark、SRE 迁移的共同契约。
- 软建议和硬边界必须分层。
- 单位、dt、mu、速度、距离不能混用。

### 高风险面

| 风险 | 表现 | 缓解 |
| --- | --- | --- |
| 相对阶误用 | 几何 CBF 看起来满足微分条件，但 jerk 系统来不及刹 | braking-distance barrier / 更高阶 CBF / 场景测试 |
| 低摩擦低估 | 雨雪路面仍按常数刹车 | `a_brake(mu)` 状态相关 |
| fallback 泛滥 | 系统安全但不可用 | fallback rate 作为 SLI |
| trace 断链 | reviewer 看不到动作为什么被改写 | schema 测试 + JSONL 回放 |
| SRE 误迁移 | 名词翻译了，机制没迁移 | 每个模式必须对应 SRE 控制点 |
| 文档漂移 | 方程、代码、测试不一致 | 每次改动同步 `FORMULA_MAP` / `equations-digest` |

## Reviewer Checklist

review 时按这个顺序看：

1. `README.md` 是否仍能指向所有核心文档。
2. `planner.step()` 是否仍是唯一北向入口。
3. `u_nn` 是否一定经过 `cbf.py`。
4. `u_safe` 是否一定经过 `invariant.py`。
5. `status` / `cbf_status` 是否符合 [trace-schema.md](./trace-schema.md) 的枚举契约。
6. `trace` 是否能解释每次动作改写。
7. `BrakingDistanceBarrier` 是否考虑速度、反应时间和摩擦。
8. `Lyapunov` 是否只承担稳定性职责。
9. `reachable` 是否没有被当作形式化证明。
10. `game` 的不确定性是否只改变 buffer / derating。
11. benchmark 是否同时报告安全和耗时。
12. SRE 文档是否迁移机制而不是迁移术语。

## 下一步（2026-05-12 更新）

**最高优先级**（阻断主线）：

1. **[AI-01](./claude-review/05-action-items.md#ai-01)** · benchmark metrics 红线断言（xfail strict=True 守门）
2. **[AI-02](./claude-review/05-action-items.md#ai-02)** · 升级 `GradientPolicy` → `PredictiveBrakePolicy`
   （完整实现骨架见 [patch 01](./claude-review/06-suggested-patches/01-barrier-aware-policy.md)）

**次高**：

3. AI-03a/b/c · 修 architecture.html 乱码 / 锁 status 枚举 / 清理 `summaizer/`
4. AI-04 · 写 schema 演进策略

**长期**：

5. AI-05 ~ AI-14 · 文档、CI、测试的补齐（见 [05-action-items.md](./claude-review/05-action-items.md) 完整表）

不再手动维护"下一步"的自由列表——所有事项都在 action items 里，状态由 `.progress.json` 跟踪。

## 给下一轮 Codex 的话（2026-05-12 更新）

**推荐阅读顺序（首次接手）**：

1. [V2_Knowledge/index.html](./V2_Knowledge/index.html) —— 5 分钟概览
2. [claude-review/00-executive-summary.html](./claude-review/00-executive-summary.html) —— 本轮 review 结论
3. [claude-review/07-codex-directives.md](./claude-review/07-codex-directives.md) —— 开工前必读的 DO/DON'T
4. [claude-review/05-action-items.md](./claude-review/05-action-items.md) —— 找到你这轮要做的事

**开工时的代码阅读顺序**（保持不变）：

1. `auto_decide/types.py`
2. `auto_decide/dynamics.py`
3. `auto_decide/cbf.py`
4. `auto_decide/invariant.py`
5. `auto_decide/planner.py`
6. `auto_decide/trace.py`

**不要做**：

- 不要为了降 `emergency_rate` 调宽 `cbf_alpha` 或缩小 `game.base_buffer` —— 详见 [07-codex-directives §DN](./claude-review/07-codex-directives.md#dont-禁令清单)
- 不要扩新功能在 P0 没完成前
- 不要跳过 review pack 直奔代码

**做**：

- 按 [action items](./claude-review/05-action-items.md) 的 ID 顺序推进
- 每个 PR 关闭一个 AI-XX + 对应 finding
- 跑完 benchmark 后把结果追加到 `docs/claude-review/08-benchmark-log.md`（见 [patch 02](./claude-review/06-suggested-patches/02-benchmark-ci.md)）

这套项目的核心价值不是"自动驾驶 demo"，而是把不可控智能输出变成可审计、可回放、可迁移的结构化控制链路。
<strong>上一轮搭好了契约和架构，这一轮让"聪明的那一端"配得上这些契约。</strong>
