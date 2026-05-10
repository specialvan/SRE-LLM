# PR 级功能需求清单（gan-matchmaking）

把文章里的九大机制逐项翻译成可独立交付的 PR。每个 PR 都给出：背景、验收标准（DoD）、涉及文件、对应论文定位。

> 命名规约：`PR-<section>-<seq>: <短标题>`
> 颗粒度：`1 个 PR 1~2 天、不超过 400 行代码`。

---

## Epic 1 · 评级与隐藏分

### PR-1-01 · TrueSkill 贝叶斯技能评级
- **背景**：文章第 1 张图——`s ~ N(μ, σ²)`，根据比赛结果做高斯更新。
- **范围**：
  - `Rating(mu, sigma)` 数据类，`Player(id, rating)`。
  - `TrueSkillRater.update(winners, losers)`：实现 TrueSkill 单场次高斯更新（两队简化版）。
  - 提供 `expected_score(team_a, team_b)`。
- **DoD**：
  - 新建玩家 `sigma` 收敛单调下降（合成 100 局后 <5）。
  - 随机两玩家长期对局，`mu` 差距反映真实实力差。
- **文件**：`gan_matchmaking/trueskill.py`、`tests/test_trueskill.py`。

### PR-1-02 · PCA 隐藏分特征提取
- **背景**：文章第 4 张图——`XᵀXv = λv`，从多维行为提取主成分。
- **范围**：
  - `HiddenScoreExtractor.fit(X)`：中心化、SVD、取 `k` 个主成分。
  - `transform(X)` 得到隐藏分；`explained_variance_ratio` 方便 debug。
  - 与 TrueSkill 分线性融合 `score = α·μ + β·z`。
- **DoD**：合成数据里，隐藏分能复原人工注入的潜在因子（相关系数 >0.95）。
- **文件**：`gan_matchmaking/pca_hidden.py`、`tests/test_pca_hidden.py`。

### PR-1-03 · GNN 队友协同图谱（纯 numpy）
- **背景**：文章第 5 张图——节点嵌入 `h^(l+1) = ReLU(Wh + ΣWij·hj)`。
- **范围**：
  - `SynergyGraph.add_match(team_ids, win)`：累积共现和胜率。
  - `SynergyGNN.forward(features, adj)`：2 层消息传递，纯 numpy。
  - `synergy_score(i, j)` 输出两人组队协同预估。
- **DoD**：
  - 合成"高协同对子"下，协同分 >0；"低协同对子"<0。
  - 一次 100 节点前向 <20 ms。
- **文件**：`gan_matchmaking/gnn_synergy.py`、`tests/test_gnn_synergy.py`。

---

## Epic 2 · 奖惩与匹配公平性

### PR-2-01 · Dynamic K-Factor 连胜衰减
- **背景**：文章第 3 张图——`K = K_max / (1 + e^{-λ(streak-θ)})`。
- **范围**：
  - `DynamicK(k_max, lam, theta).k(streak)` 返回当前 K。
  - 当前连胜越多 K 越小（连胜保护失效方向）。
  - 提供 `delta_rating(expected, actual, streak)`。
- **DoD**：单调性测试：`streak` 越大，赢一局得分越少；输一局扣分更多。
- **文件**：`gan_matchmaking/dynamic_k.py`、`tests/test_dynamic_k.py`。

### PR-2-02 · Handicap 连胜惩罚 Elo
- **背景**：文章第 6 张图——`E_A = 1 / (1 + 10^((R_B - R_A + Penalty)/400))`。
- **范围**：
  - `HandicapElo.penalty(streak, loss_streak)` 随连胜增大、随连败减小。
  - `expected_win(r_a, r_b, penalty)`。
  - `update(r_a, r_b, score_a, k, penalty)`。
- **DoD**：
  - 连胜 10 场后，期望胜率被拽回 ~50%。
  - 无连胜时退化为标准 Elo。
- **文件**：`gan_matchmaking/handicap.py`、`tests/test_handicap.py`。

### PR-2-03 · Information Entropy 对局熵最大化匹配
- **背景**：文章第 7 张图——`max_M H(Outcome) = -Σ p log2 p`。
- **范围**：
  - `EntropyMatcher.win_prob(team_a, team_b)` 用 Elo/TrueSkill 给出胜率。
  - `EntropyMatcher.score_config(team_a, team_b)` 返回 `H(p, 1-p)`。
  - `find_best_match(candidates)` 在候选队伍里挑熵最大（最不确定）的一组。
- **DoD**：分差 0 的对局熵=1；分差极大时熵接近 0；`find_best_match` 优先选五五开。
- **文件**：`gan_matchmaking/entropy_match.py`、`tests/test_entropy_match.py`。

---

## Epic 3 · 留存与博弈

### PR-3-01 · EOMM 参与度优化匹配
- **背景**：文章第 2 张图——`max_M E[P(Retain | M, H_t)]`。
- **范围**：
  - `RetentionModel.prob(history, match_config)` —— 一个线性/logistic 模型，占位实现。
  - `EOMMMatcher.best(history, candidates)` 返回 argmax 留存概率的配置。
  - 支持 `epsilon`-贪婪探索参数。
- **DoD**：
  - 当历史里"上一局逆风"时，模型倾向选"下一局较好带"的配置。
  - 单次决策 <1 ms。
- **文件**：`gan_matchmaking/eomm.py`、`tests/test_eomm.py`。

### PR-3-02 · Survival Analysis 玩家流失生存分析
- **背景**：文章第 8 张图——Cox 比例风险 `h(t|X) = h_0(t) exp(βᵀX)`。
- **范围**：
  - `CoxModel.fit(X, durations, events)`：用偏似然最大化（牛顿迭代或 scipy.optimize）。
  - `hazard(X, t)` / `survival(X, t)` 输出流失风险与生存曲线。
  - 辅助 `ChurnRiskMonitor.predict(player_history)`：包装上述。
- **DoD**：
  - 合成数据上，β 估计误差 <10%。
  - 连败越多 hazard 越大（单调）。
- **文件**：`gan_matchmaking/survival.py`、`tests/test_survival.py`。

### PR-3-03 · Minimax BP 零和博弈纳什均衡
- **背景**：文章第 9 张图——`min_y max_x U(x, y) = max_x min_y U(x, y)`。
- **范围**：
  - `zero_sum_nash(U)`：用 LP 或迭代法（fictitious play）解两人零和纳什。
  - `BPSession`：BP 序列 state machine，每一步调用 Nash 求解器。
  - 返回混合策略 + 价值。
- **DoD**：
  - 对典型"石头剪刀布"矩阵能收敛到均匀分布。
  - `value(x*, y*)` 满足 minimax 定理（误差 <1e-6）。
- **文件**：`gan_matchmaking/minimax_bp.py`、`tests/test_minimax_bp.py`。

---

## Epic 4 · 端到端装配

### PR-4-01 · 肝度管线 Pipeline
- **背景**：九个模块合起来形成一条闭环管线。
- **范围**：`GanPipeline.next_match(player, pool)`：
  1. `TrueSkillRater` → 估计 μ, σ
  2. `HiddenScoreExtractor` → 融合隐藏分
  3. `SynergyGNN` → 给候选队伍打协同分
  4. `DynamicK` + `HandicapElo` → 算调整后的期望胜率
  5. `EntropyMatcher` → 过滤掉确定性过高的对局
  6. `EOMMMatcher` → 从剩余候选里挑留存概率最高的
  7. `ChurnRiskMonitor` → 若流失风险太高则手动"喂软对手"
  8. `BPSession` → 返回推荐 BP 策略
- **DoD**：`examples/demo_pipeline.py` 跑一次能打印完整 `trace`。
- **文件**：`gan_matchmaking/pipeline.py`、`examples/demo_pipeline.py`、`tests/test_pipeline.py`。

### PR-4-02 · 可观测性与日志
- **范围**：所有机制返回 `dict` trace；提供 `to_jsonl(trace)` helper。
- **DoD**：一次 demo 产出 `trace.jsonl`。

### PR-4-03 · 单元测试 & CI
- **范围**：每个模块至少一组 pytest；可选 GitHub Actions 配置。
- **DoD**：`pytest -q` 全绿，覆盖率 ≥ 70%。

---

## 附录 · PR 与文章图片的双向追溯

| PR 编号 | 文章定位 | 公式 |
| --- | --- | --- |
| PR-1-01 | 图 1 TrueSkill | `s ~ N(μ, σ²)` |
| PR-1-02 | 图 4 PCA 隐藏分 | `XᵀX v = λ v` |
| PR-1-03 | 图 5 GNN 协同 | `h^(l+1) = ReLU(Wh + ΣWij·hj)` |
| PR-2-01 | 图 3 Dynamic K | `K = K_max/(1+e^{-λ(streak-θ)})` |
| PR-2-02 | 图 6 Handicap Elo | `E_A = 1/(1+10^{(ΔR+Penalty)/400})` |
| PR-2-03 | 图 7 Entropy | `H = -Σ p log2 p` |
| PR-3-01 | 图 2 EOMM | `max E[P(Retain|M,H)]` |
| PR-3-02 | 图 8 Survival | `h(t|X) = h_0(t)exp(β^T X)` |
| PR-3-03 | 图 9 Minimax BP | `min_y max_x U = max_x min_y U` |
| PR-4-01/02/03 | 装配 / CI | — |
