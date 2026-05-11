# 2026-05 Session Review · `gan-session`

**Reviewer**: Claude
**Branch**: `gan-session`
**Commit range**: `master..HEAD` (11 commits, +4531 / −239)
**Pytest**: 105/105 pass
**Bench (p99)**: 1.73 ms (budget 50 ms)

## 结论 (TL;DR)

**Recommended: merge with the P1 fix, then land 3 follow-up PRs.**

这一轮是本项目从"能跑的 demo"到"可审计、可复现、可回滚、可训练的生产骨架"的关键跃迁。三项硬核能力——runtime artifact 版本化、单写者 lease 边界、fitted replay promotion——都按 PR 需求真实落地，并且都配了能证伪的测试。唯一的合入 blocker 是 `LeaseRefreshLoop` 的静默失败路径，它在错误方向上违反了 ADR-0007 的承诺。

## 范围

本轮交付文件占比：

| 类别 | 新增/修改 | 占比 |
|---|---|---|
| 生产代码 | 1612 行 | 36% |
| 测试 | 771 行 | 17% |
| 文档 | 1706 行 | 38% |
| replay fixtures | 368 行 | 8% |
| 配置 / 部署 | 74 行 | 2% |

文档占比偏高但不是凑字——每份都对应具体契约（ADR / 模块契约 / state lifecycle / 控制原语）。

## 一、交付对齐度

逐项核对 `PR-REQUIREMENTS.md` 中 `gan-session` 新增 / 更新的 PR，全部与代码对齐：

| PR | 状态声明 | 代码验证 |
|---|---|---|
| PR-3-01 Retention artifact versioning | 已完成 | ✅ `sre/artifacts.py::RetentionArtifact` + validate + save/load + hydrate |
| PR-3-02 Cox artifact versioning | 已完成 | ✅ 同上，Cox 路径 |
| PR-3-03 Artifact metadata in trace/persistence | 已完成 | ✅ `Decision.artifact_version` + SQLite migration v5 + `trace["artifacts"]` |
| PR-3-04 Fitted artifact replay promotion | 已完成 | ✅ `sre/replay.py` + export CLI + validate + archive + manifest |
| PR-5-04 SRE control primitive catalog | 已完成 | ✅ `sre/primitives.py` + `docs/sre-control-primitives.md` + tests |
| 新增 lease 边界 (ADR-0007) | 已完成 | ✅ `sre/leases.py` + `FileLease` + `LeaseRefreshLoop` + service `__main__` 集成 |

## 二、做对了什么

### 2.1 Artifact 版本化是本轮硬核

`ArtifactMetadata` 由 `name / version / trained_at / source_window / config_hash / build_id / fitted / fallback` 组成，`version` 用 SHA-256 稳定哈希生成——可复现、可审计。

三重校验：
- **名称** `name` 必须匹配 `"retention"` / `"cox"`
- **形状** weights / beta 的 ndim 和 dim
- **契约** `feature_names` 必须完全等于 `EOMM_FEATURE_NAMES` / `RISK_FEATURE_NAMES`

校验失败**不崩溃**，而是降级为 `bootstrap` 并把错误写进 `trace["artifacts"]["validation_errors"]`。`test_invalid_artifact_manifest_falls_back` 显式断言了这条路径。

### 2.2 训练 ↔ 运行 feature contract 真的对齐了

上一轮留下的最大暗坑：Cox 训练用 2 维 `[loss_streak, time_since_prev]`，运行时喂 6 维——这意味着再训出来的 β 根本套不回去。codex 把训练切到 `build_observation_risk_vector` + `RISK_FEATURE_NAMES`，EOMM 同样替换掉伪 `_StubPlayer` 改用 `build_match_config` / `empirical_service`。现在两端共享 `sre/features.py`，形状和语义都是一份契约。

### 2.3 Lease 边界处理得克制且诚实

`FileLease` 用 `O_CREAT|O_EXCL` 原子 open + token 校验 + TTL 过期接管。`test_file_lease_takes_over_expired_owner` 用假 `now` 时钟注入验证接管路径，是很优秀的测试写法。

**ADR-0007 明确声明 `FileLease` 不是分布式锁**，没有掩盖。这种诚实的边界声明在架构演进里极其重要——未来谁要搞多副本，就必须换成 Redis/etcd/k8s Lease，而不会把 FileLease 当成银弹。

### 2.4 Replay promotion 从"支持"升级到"门禁"

`export_replay_fixture` 默认**拒绝**导出 `artifact_version != "bootstrap"` 的决策。必须显式传 `--allow-fitted-artifacts` + `--artifact-dir`，而且导出器会：
1. `validate_artifact_bundle` 校验 manifest
2. 如果指定了 `artifact_output_directory` 就 `archive_artifact_bundle` 归档
3. 写 `replay_artifact_manifest.json`
4. 在 fixture 里记 `requires_artifact_version` + `artifact_bundle`

避免了最容易被忽视的坑：fitted artifact 决策落进 golden corpus 但 artifact 本身丢了，replay 时走 fallback 还通过测试——那是假的回归保障。

### 2.5 Trace 的审计密度提升一档

- `trace["input"]["context"]` + `trace["input"]["config"]` → 输入可字节级重建
- `trace["artifacts"]` 带 `version / fitted / validation_errors` → 区分 code drift 与 model drift
- `trace["stages"]["eomm"]["source"]` 明确写 `"artifact"` 或 `"fallback"` → fallback 不再是隐性事件

### 2.6 控制原语抽象（PR-5-04）是视野亮点

`CONTROL_PRIMITIVES` 是 frozen dataclass 元组，每个机制标注：
- `capability` — 工程能力名（`belief_state_estimator`、`information_value_gate` 等）
- `runtime_stage` — pipeline 里哪个阶段
- `production_status` — `production / mixed / research`
- `compounding_use` — 可复用到哪些 SRE 场景

这一步把 GAN 九机制从"算法列表"升级成"可迁移的 SRE 工程能力目录"。下一个用这套思路去做发布决策、容量调度、告警降噪的 SRE 团队，可以直接对照 catalog 选原语而不是重读九篇论文。

## 三、需要关注的问题（详见 `findings.md`）

按严重度：

- **P1** · `LeaseRefreshLoop` 续租失败静默化 — **合入前必修**
- **P2** · 监控/日志的 `kind` 和最终决策不一致（shadow rewrite 后）
- **P2** · `trace.input.config` 无 allowlist，未来易泄密
- **P3** · `setattr(ctx.service, "_deps", ...)` 副作用泄漏到调用方
- **P3** · `_service_player` 里硬编码的 `mu = 25 + 18 * ...` 魔数影响 artifact 稳定性
- **P3** · `sre/artifacts.py` 单文件 488 行，可拆
- **P3** · `cli._ctx_from_dict` 被 service/replay 跨模块 `_` 私有 import，应晋升到公共位置
- **P3** · SQLite migration v5 带了 "if column exists skip" 的特殊处理，迁移系统纯度受损
- **P4** · codex-handoff 和 implementation-roadmap 有 30% 内容重叠
- **P4** · replay fixture 命名风格不统一

## 四、评分

| 维度 | 评分 | 说明 |
|---|---|---|
| 对 PR 需求的交付度 | ★★★★★ | 5-04 新 PR 真实落地，其余"已完成"全部核对过 |
| 测试质量 | ★★★★☆ | 新增测试都验证真实行为而非 smoke，P1 缺续租失败测试 |
| 契约 / 边界清晰度 | ★★★★★ | 3 份新 ADR + 2 份新 runbook + feature contract 齐全 |
| 抽象迁移能力 | ★★★★★ | SRE 控制原语目录是本轮最有视野的一步 |
| 生产鲁棒性 | ★★★☆☆ | artifact / lease / persistence 到位，P1 / P2 上产前必须补 |
| 文档 / 代码比例 | ★★★☆☆ | 偏重但都是有用文档；handoff 与 roadmap 有重叠 |

## 五、合入建议

1. **合入前**：只需修 P1。把 `LeaseRefreshLoop` 续租失败从"静默写 `self.error`"改成"触发服务 readiness 翻转 + 告警 + 结束主循环"。必须补一个失败注入测试。
2. **合入后** 3 个 follow-up PR：
   - `fix(lease): surface refresh failure through readiness` — P1 的彻底版
   - `chore(trace): allowlist AppConfig serialization in trace.input.config` — P2
   - `refactor(sre): split artifacts.py + freeze rating-scaling constants` — P3 组合
3. **下一轮主题**：
   - 用真实观测数据校准 Cox / Retention 阈值
   - 增加 incident-style replay，覆盖 artifact validation failure / breaker short-circuit / shadow transition
   - 如果目标部署需要多写者，原型化 k8s Lease / PostgreSQL advisory lock

## 六、一句话总结

这一轮的输出从"能跑的 demo"推进到了"可审计、可复现、可回滚、可训练的生产骨架"。三个最关键的工程能力——artifact 版本化、单写者边界、fitted replay 门禁——都按 PR 需求真实落地，并且每个都配了能证伪的测试。修掉 P1 之后，这个仓库就可以作为 SRE 自迭代决策组件的参考实现被其他项目复用了。
