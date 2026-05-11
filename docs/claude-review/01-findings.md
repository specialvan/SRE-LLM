# Findings · 本轮 Codex 交付的问题清单

每条 finding 的格式：**标题 · 严重度 · 证据 · 影响 · 修复 · 验证**。
Codex 按 finding ID 逐条过即可。

---

## 🚨 P0 级（阻断下一轮主线）

### F-P0-01 · Benchmark 默认场景下 `planner_emergency_rate` 严重违反 SLO

**严重度**：P0
**类别**：SLO / benchmark / 安全 vs 可用性权衡

**证据**：
```
$ python -m examples.compare_e2e_vs_structural --n 20 --metrics-out artifacts/review-metrics.json
=== Structural (CBF + T_inv) ===
  collision rate: 0.00%  (0/20)      ← SLO ✅
  emergency rate: 42.50%              ← SLO < 0.5% 🚨 86×
  CBF fallback  : 23.10%              ← SLO < 5%   🚨 5×
  planner status: {'non_increasing': 889, 'emergency_brake': 850, 'stable': 261}
```

对照 `docs/knowledge-base.html` §6.1 的安全 SLO 承诺：
> 紧急刹停回退率：`status == emergency_brake` 占比 **< 0.5% / 100 km**

**影响**：
- "碰撞率 0%" 的表面好看数字是刹停兜底生效的结果，不是 nominal policy 本身安全。
- 在生产里会连续触发 P1 告警并自动冻结名义策略升级（依照 knowledge-base.html 的错误预算规则）。
- 如果下一轮 Codex 看见"0% 碰撞"就提前庆祝，整个基准会产生误导。

**修复**：

1. 在 `tests/test_benchmark_metrics.py` 新增一个**契约性回归**（非调参）：
   ```python
   def test_structural_pipeline_respects_availability_budget():
       payload = run_benchmark(n=20, seed=0, horizon=100, dt=0.1)
       s = payload["summaries"]["structural"]
       # 这是生产 SLO 的 demo 版松弛（生产必须更严），但不允许回退到无上限
       assert s["planner_emergency_rate"] <= 0.10, (
           "emergency_brake 占比超过 10%：说明 nominal policy 与 CBF 不匹配，"
           "不要通过放宽 CBF/game 来降低此值，先升级 nominal policy。"
       )
       assert s["cbf_fallback_rate"] <= 0.10
   ```
2. 在 `docs/benchmark-metrics.md` 末尾加"SLO 阈值参考"表，写明 demo 与生产两档阈值。
3. 在 `README.md` 与 `codex-handoff.md` 的 Quick Start 里标注："benchmark 结果预期 emergency_rate < 10%；当前 42.5% 是已知问题 AI-02，不是达标状态"。

**验证**：
- `pytest tests/test_benchmark_metrics.py::test_structural_pipeline_respects_availability_budget` 必须通过（改 nominal policy 之后）。
- benchmark 输出 JSON 中 `structural.planner_emergency_rate < 0.10`。

---

### F-P0-02 · GradientPolicy 与 CBF 链路结构性不匹配

**严重度**：P0
**类别**：nominal policy / 控制闭环

**证据**：

上一条 finding 的 status 分布：
```
planner status: non_increasing=889, emergency_brake=850, stable=261
cbf status:     nom_ok=1470,  fallback_brake=462,  qp_ok=68
```
解读：
- `nom_ok=73.5%`：CBF 认为名义命令本身已经满足 barrier（说明 nominal 并没有在主动逼近边界）；
- `fallback_brake=23.1%`：**CBF 的 QP 级搜索找不到可行解**，说明名义命令要求加速但物理上不行；
- `emergency_brake=42.5%`：**T_inv 的松弛也救不回来**，直接刹停；
- `stable=13.0%`：真正平稳的只有 13%。

进一步观察：`GradientPolicy` 几乎不考虑**未来一两步内 CBF 会怎么拦自己**——它按照势能场选方向，一头撞到 barrier，然后 CBF 紧急刹。

**影响**：
- 这个状态分布是"结构化链路的可用性底色"，没改之前无论 demo 场景怎么设计，`emergency_rate` 都不会低于 ~20%。
- 下一轮所有 "demo 好看的数字" 都会被这个问题污染。

**修复方案（推荐顺序）**：

1. **最小改动**：`GradientPolicy` 的 `jerk` 计算里加一个"若即将进入 barrier 则预刹"的前瞻项。骨架在 [06-suggested-patches/01-barrier-aware-policy.md](./06-suggested-patches/01-barrier-aware-policy.md)。
2. **中等改动**：实现 `BarrierAwareMPC`，在 2 ~ 3 步前瞻内解一个含 CBF 约束的 open-loop QP，把尾部动作收敛到刹停模式。
3. **长期**：用模仿学习（imitation learning），把 `planner.run()` 的 `u_safe` 当 ground truth 训练一个 policy，再用它替代 GradientPolicy。

不要做：
- ~~调大 `PotentialField.w_obs`~~（治标不治本）；
- ~~调小 `cbf_alpha`~~（会把碰撞率带回来）；
- ~~把 `game.base_buffer` 缩到 1 m~~（违反最坏情况博弈假设）。

**验证**：
- `python -m examples.compare_e2e_vs_structural --n 50 --seed 0` 输出 `planner_emergency_rate < 0.10`；
- 碰撞率保持 0%；
- 新增 `tests/test_nominal_policy.py`：对 "obstacle ahead + v=12" 场景，nominal policy 自己先产出 `jerk < 0` 而不是等 CBF 拦。

---

## ⚠️ P1 级（合入前应修）

### F-P1-01 · `architecture.html` 的 `<title>` 存在 mojibake

**严重度**：P1
**类别**：文档质量

**证据**：
```html
<!-- docs/architecture.html:6 -->
<title>auto-decide 路 Detailed Architecture</title>
```
"路" 应为 `·` 或 `—`。正文内容 UTF-8 正确，仅 title 有此字符。

**影响**：浏览器 tab 显示乱码；截图分享时观感差。

**修复**：一个字符的编辑：
```diff
-<title>auto-decide 路 Detailed Architecture</title>
+<title>auto-decide · Detailed Architecture</title>
```

**验证**：浏览器打开 `docs/architecture.html`，tab 标题无乱码。

---

### F-P1-02 · `T_inv` 的 status 枚举在文档中不完整

**严重度**：P1
**类别**：契约一致性

**证据**：

`codex-handoff.md` §2.8：
> 状态码是否覆盖 `ok` / `relaxed` / `fallback_brake`。

实际 `invariant.py` 与 demo trace 里出现的值：
```
{'non_increasing': 87, 'emergency_brake': 48, 'stable': 15,
 'relaxed': ..., 'relaxed_exp': ..., 'unchanged': ...}
```
共 5 种：`stable` / `relaxed_exp` / `relaxed` / `non_increasing` / `emergency_brake`。
handoff 与 `trace-schema.md` 都没有把 5 种明确列出，reviewer 按 handoff 检查会漏。

**影响**：下一轮 Codex 无从判断 status 值的合法集合；引入新 status 值时无法回归。

**修复**：在 `docs/trace-schema.md` 把 `status` 与 `cbf_status` 改成明示枚举：
```markdown
| `status` | enum | `T_inv` 的状态码之一：<br>
  - `stable` — 首次尝试即满足 dV/dt ≤ -γV<br>
  - `relaxed_exp` — 松弛后满足指数衰减目标<br>
  - `relaxed` — 松弛后只满足 dV/dt ≤ τ<br>
  - `non_increasing` — 边缘稳定（|dV/dt| ≤ τ）<br>
  - `emergency_brake` — 兜底刹停 |
| `cbf_status` | enum | `CBFQPFilter` 的状态码之一：<br>
  - `nom_ok` — 名义命令已满足 barrier<br>
  - `qp_ok` — 搜索找到非平凡可行解<br>
  - `fallback_brake` — 搜索失败，退化为刹停 |
```

并在 `auto_decide/trace.py` 顶部加一个常量：
```python
PLANNER_STATUS_VALUES = frozenset({
    "stable", "relaxed_exp", "relaxed", "non_increasing", "emergency_brake",
})
CBF_STATUS_VALUES = frozenset({"nom_ok", "qp_ok", "fallback_brake"})
```

**验证**：
- 新增测试：`assert trace["status"] in PLANNER_STATUS_VALUES`；
- handoff 删掉自己维护的 status 列表，改为"见 trace-schema.md"。

---

### F-P1-03 · `summaizer/` 目录拼写错且状态模糊

**严重度**：P1
**类别**：项目卫生

**证据**：
- 目录名 `summaizer/`（应为 `summarizer/`）；
- `git status` 长期显示 `Untracked files: summaizer/`；
- 内含展示 HTML + gif + zip，未 `.gitignore`。

**影响**：长期噪声 · `git status` 始终不干净 · 未来新人不确定其去留。

**修复（二选一）**：

**选项 A · 保留并入仓**：
```
git mv summaizer release-artifacts     # 或 docs/review-pack
```
并在 `.gitignore` 里加 `release-artifacts/*.zip` 避免二进制入仓。

**选项 B · 忽略**：
```
echo "summaizer/" >> .gitignore
# 或改名再忽略：
mv summaizer .local-artifacts
echo ".local-artifacts/" >> .gitignore
```

**推荐**：选项 B。展示素材不应进业务仓。

**验证**：`git status` 干净。

---

## 🟡 P2 级（可以分多次迭代）

### F-P2-01 · `trace._jsonable` 异常吞没缺乏 debug 可见性

**证据**：
```python
# auto_decide/trace.py:26
if hasattr(value, "item") and not isinstance(value, (list, tuple, dict)):
    try:
        return _jsonable(value.item())
    except Exception:
        pass
```
两层 `except Exception: pass` 会把 numpy 对象的转换失败静默吃掉。

**修复**：
```python
import logging
_LOG = logging.getLogger(__name__)

def _jsonable(value):
    ...
    if hasattr(value, "item") and not isinstance(value, (list, tuple, dict)):
        try:
            return _jsonable(value.item())
        except Exception as e:
            _LOG.debug("trace _jsonable item() failed for %r: %s", type(value), e)
```

或者给 `build_trace_record` 加一个 `strict: bool=False` 参数，`strict=True` 时把异常传播出来——测试环境开。

---

### F-P2-02 · `benchmark-metrics.md` 没写 schema 演进策略

**证据**：文档定义了 `schema_version: "benchmark.metrics.v1"`，但没规定"什么情况下必须 bump"。

**修复**：在文档末尾加：
```markdown
## Schema Evolution

- 新增字段 → `v1` 即可（向后兼容）；
- 删除字段 / 修改已有字段语义 → 必须 bump 到 `v2` 且在 CHANGELOG 里说明；
- `schema_version` 本身字段不允许删；
- 下游读 JSON 应先 check `schema_version`，再用字段。
```
同样规则复制到 `trace-schema.md`。

---

### F-P2-03 · `architecture.html` 未包含方程依赖图 / 失败决策树

**证据**：`architecture.html` 有 3 个 SVG（静态架构、runtime、refine loop），但缺 2 种值得深入的视图：
1. 失败决策树（"出现某个症状 → 哪个模块先改"）；
2. 一张能看出"哪个场景触发哪个模块"的**场景 × 模块**矩阵。

**修复**：把这两个视图合并到 [02-architecture-deep.html](./02-architecture-deep.html)（本 review pack 已附），未来 Codex 可以把同样的图搬到 `architecture.html`。

---

### F-P2-04 · benchmark 结果未与 `docs/architecture.html` 的 refine loop 联动

**证据**：`architecture.html` §4.1 的 "Symptom → refine target" 表是静态列的，没说"当前 benchmark 处于哪一行"。

**修复**：把 benchmark JSON 作为 architecture.html 的数据源：
```html
<script>
fetch("../artifacts/benchmark-metrics.json")
  .then(r => r.json())
  .then(d => {
    const rate = d.summaries.structural.planner_emergency_rate;
    if (rate > 0.10) document.getElementById("refine-target").innerText = "emergency_rate 过高 → Task AI-02";
  });
</script>
```
先 demo 级即可，不需要复杂可视化。

---

### F-P2-05 · `codex-handoff.md` 把 `trace.py` 定位为"第 10 个横切契约"但 deep-dive 仍是 9 模块

**证据**：handoff 明确说 "trace.py 是横切契约层，不算第 10 个核心数学模块"，但 `deep-dive.html` 仍然是 "9 模块" 结构，没有给 trace 独立章节。

**修复**：
- 要么把 trace 加进 deep-dive 作为 §4.10（推荐）；
- 要么在 README 的"目录"里显式标注 "trace.py 独立于 9 模块之外，见 trace-schema.md"。

---

### F-P2-06 · `compare_e2e_vs_structural.py` 的 `_pure_e2e_step` 使用 `dyn.step` 触发静态扫描误报

**证据**：我在 review 中跑静态扫描验证 INV-G2，命中了这一处，但它是**合法的 bypass**（用来做对比）。

**修复**：加一个 `# noqa: INV-G2 intentional bypass` 风格的注释或模块级 docstring，便于未来 CI grep 时能自动排除：
```python
"""... 这个文件为了对照 e2e pipeline 刻意直接调用 ``dyn.step``, 是 INV-G2 的已知合法例外。"""
```

---

### F-P2-07 · `architecture.html` 链接指向 `./codex-handoff.md`，handoff 反向引用 `./architecture.html`，形成环（小问题）

**建议**：所有 hub 文档（README / knowledge-base / architecture / handoff）都明示"谁是 primary entry"，避免循环导航的无限下钻。推荐 README → (knowledge-base | architecture) 二选一。

---

## ✅ 未发现问题（positive findings）

| 项目 | 评价 |
| --- | --- |
| `planner.step()` 唯一入口 | 静态 grep 通过 |
| `Control(0, -j_max)` fallback 可行性 | 仍然保持 |
| CBF 条件以不等式进入搜索 | 未被软化为 penalty |
| trace 字段向后兼容 | `schema_version="1.0"` 且仅新增字段 |
| 新测试对 E-30 / E-32 覆盖 | `test_braking_distance_barrier_inflates_with_speed_and_low_mu` 与 `test_low_friction_turns_nominal_acceleration_into_brake` 精准覆盖相对度 1 与 μ 自适应 |
| benchmark CLI 参数化 | `--n/--seed/--horizon/--dt/--metrics-out` 覆盖所有必要参数 |
| `_jsonable` 对 `inf/NaN/numpy` 的清洗 | 正确且被 `test_trace_record_is_json_safe_and_versioned` 用 `allow_nan=False` 锁住 |
| `codex-handoff.md` 的 9 模块 + 35 方程骨架 | 结构对、抓手多、对下一轮 Codex 非常友好 |

---

## 索引

| Finding ID | 类别 | 紧急度 | Action Item |
| --- | --- | --- | --- |
| F-P0-01 | SLO | P0 | [AI-01](./05-action-items.md#ai-01) |
| F-P0-02 | Policy | P0 | [AI-02](./05-action-items.md#ai-02) |
| F-P1-01 | Doc | P1 | [AI-03a](./05-action-items.md#ai-03a) |
| F-P1-02 | Contract | P1 | [AI-03b](./05-action-items.md#ai-03b) |
| F-P1-03 | Hygiene | P1 | [AI-03c](./05-action-items.md#ai-03c) |
| F-P2-01 | Debug | P2 | [AI-06](./05-action-items.md#ai-06) |
| F-P2-02 | Schema | P2 | [AI-04](./05-action-items.md#ai-04) |
| F-P2-03 | Doc | P2 | [AI-07](./05-action-items.md#ai-07) |
| F-P2-04 | Doc | P2 | [AI-05](./05-action-items.md#ai-05) |
| F-P2-05 | Doc | P2 | [AI-08](./05-action-items.md#ai-08) |
| F-P2-06 | Hygiene | P2 | [AI-09](./05-action-items.md#ai-09) |
| F-P2-07 | Navigation | P2 | [AI-10](./05-action-items.md#ai-10) |
