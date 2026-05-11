# 05 · Artifact Lifecycle

Retention / Cox 两个 learned component 的 artifact 从**训练 → 打包 →
校验 → 部署 → 运行 → 回滚**的完整链路。这条链路是系统从 bootstrap
走向 data-driven 的唯一通道。

## 1. 生命周期总览

```mermaid
flowchart LR
  OBS[observations<br/>SQLite] --> TRAIN[training job<br/>nightly CronJob]
  TRAIN --> PKG[Artifact Bundle<br/>.npz + metadata.json]
  PKG --> VAL[Artifact Validation<br/>at pipeline startup]
  VAL -->|pass| HYDRATE[Runtime Hydrate<br/>eomm.model / risk.model]
  VAL -->|fail| BOOTSTRAP[Fallback to bootstrap<br/>+ trace.validation_errors]
  HYDRATE --> DECIDE[decide(ctx)]
  DECIDE --> TRACE[trace.stages.eomm.source="artifact"]
  DECIDE --> AUDIT[SQLite decisions.artifact_version]
  AUDIT -->|replay| REGRESS[replay corpus<br/>tests/fixtures/replay]
  REGRESS -.new fixture.-> PKG
```

## 2. 关键数据结构

### 2.1 `ArtifactMetadata`

```python
@dataclass(frozen=True)
class ArtifactMetadata:
    name: str                 # "retention" | "cox"
    version: str              # SHA-256[:16] of payload
    trained_at: float         # unix seconds
    source_window: Mapping    # {n_observations, n_events, services, ...}
    config_hash: str          # hash of training config
    build_id: str             # GIT_SHA / BUILD_ID / "unknown"
    fitted: bool              # 是否真的跑过训练
    fallback: bool            # 是否是 fallback 占位
    extra: Mapping            # feature_names, feature_dim, ...
```

**版本稳定性契约**:
- `version` 由 `_stable_version(payload)` 生成，同一份 payload 得到同一
  version（可复现）
- `payload` 包含 `name / trained_at / source_window / config_hash / build_id /
  fitted / fallback / extra`，任何一项改变都得到新 version
- `trained_at` 的存在让同样数据同样代码的两次训练得到不同 version，这是有意的
  （训练时间也是 artifact 身份的一部分）

### 2.2 `RuntimeArtifactBundle`

```python
@dataclass(frozen=True)
class RuntimeArtifactBundle:
    retention: Optional[RetentionArtifact]
    cox: Optional[CoxArtifact]
    validation_errors: Mapping[str, Sequence[str]]

    @property
    def version(self) -> str:
        # 格式: "retention@<v1>+cox@<v2>" 或 "bootstrap" 或单个部件版本
```

Bundle 的 version 是组合版本，天然描述了"retention 存在 + Cox 缺失"
这种部分 hydrate 场景。

## 3. 训练阶段

**入口**: `python -m gan_matchmaking.training --state-db state.sqlite`

**实现**: `gan_matchmaking/training/{retention,cox}.py`

### 3.1 Feature contract 与运行时对齐

这一轮最关键的改造：训练和运行共享 feature builders，**形状和语义一份契约**。

```
sre/features.py::RISK_FEATURE_NAMES
    = ("loss_streak", "win_streak", "unreliability", "sigma",
       "canary_fraction", "budget_spent")
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
        training/cox.py                  sre/self_iteration.py
        (build_observation_risk_vector)  (build_risk_feature_vector)
        ^同一份 NAMES                     ^同一份 NAMES
```

如果 `RISK_FEATURE_NAMES` 变了：
- Artifact manifest 里 `extra.feature_names` 记录的是**训练时的版本**
- Pipeline 启动时 `validate_cox_artifact` 会对比 **当前代码** vs **manifest 里的**
- 不一致 → 降级 bootstrap，`trace.validation_errors.cox = ["manifest.extra.feature_names mismatch"]`

这是"形状硬契约"的核心。Retention 同理。

### 3.2 输出物

```
training_artifacts/
├── cox_beta.npz               # {beta, baseline_t, baseline_H}
├── cox_artifact.json          # ArtifactMetadata
├── cox_report.json            # 训练报告（不被 runtime 读取）
├── retention_weights.npz      # {weights, bias}
├── retention_artifact.json    # ArtifactMetadata
└── retention_report.json      # 训练报告
```

## 4. 部署阶段

### 4.1 在 K8s 上

```yaml
# deploy/kubernetes/deployment.yaml
volumeMounts:
  - name: state
    mountPath: /state    # 包含 state.sqlite 和 training_artifacts/

# deploy/kubernetes/cronjob-training.yaml
command: ["python", "-m", "gan_matchmaking.training"]
args: ["--state-db=/state/state.sqlite",
       "--output-dir=/state/training_artifacts"]
```

**同一 PVC** 挂载到 decider pod 和 training CronJob。训练写完 artifact，
decider **下次启动**才会重新 hydrate。

**为什么不做热加载？**
- 简单性：热加载需要 atomic swap + in-flight decision 保护 + metric 重置
- 可审计：pod restart = 一个明确的 cutover 点，易于事故回溯
- 频率：daily 训练 + 受控 restart 已经足够

### 4.2 版本识别

Pipeline 启动时的日志：

```json
{"event": "artifacts.loaded",
 "artifact_version": "retention@abc123...+cox@def456...",
 "fitted": true}
```

这个 version 会出现在：
- 每次 decide 的 `trace.artifacts.version`
- 每次 decide 的 `Decision.artifact_version`
- SQLite `decisions.artifact_version` 列
- 日志 `decide.finished` 事件

## 5. 校验阶段

**入口**: `load_runtime_artifacts(directory)` → `RuntimeArtifactBundle`

三重校验（按部件分别跑）：

```python
def validate_retention_artifact(artifact) -> list[str]:
    errors = []
    # 1. 身份：name 必须是 "retention"
    # 2. 形状：weights ndim == 1, dim == 8
    # 3. 契约：extra.feature_names == EOMM_FEATURE_NAMES
    # 4. 数值：weights/bias 无 NaN/Inf
    return errors


def validate_cox_artifact(artifact) -> list[str]:
    # 类似，但 dim == 6, baseline_t/H 要存在且等长
```

**不通过的处理**：`artifact` 在 bundle 里被 set 成 None，`validation_errors`
记录所有错误原因。Pipeline 继续启动，`/readyz` 仍然 ready（fallback 是合法状态）。

**这条契约的意义**：

- 允许部署一个 "空的" artifact 目录（全 bootstrap）
- 允许 partial hydrate（只有 retention 没有 cox）
- 禁止 "看起来 fitted 但形状错" 的隐性危险

## 6. 运行阶段

### 6.1 EOMM artifact 分支

```python
# gan_matchmaking/sre/self_iteration.py::_stage_eomm
if self.artifacts.retention is not None:
    # 用 artifact 路径
    chosen = self.eomm.best(history, match_configs, rng=seeded_rng)
    trace["stages"]["eomm"] = {"source": "artifact", ...}
```

### 6.2 Cox artifact 分支

```python
# __post_init__ 里 hydrate
self.risk.model.beta = cox.beta
self.risk.model._baseline_t = cox.baseline_t
self.risk.model._baseline_H = cox.baseline_H
```

运行时 `risk.predict(features)` 会直接走 fitted 的 survival 计算，不走 logistic
heuristic。

### 6.3 Fallback 的明确性

**核心设计**：运行时永远能区分三种状态：

1. **uninitialized** — artifact 从未加载，logistic heuristic（pessimistic）
2. **fitted** — artifact 正常加载，用 survival 公式
3. **invalid** — artifact 被拒绝，回到 uninitialized，但 `trace.validation_errors` 有证据

任何时刻检查 `trace.stages.eomm.source` 和 `trace.artifacts.fitted` 就能判断
系统现在是哪种状态。

## 7. Replay & 回滚阶段

### 7.1 Bootstrap 决策可直接回放

- `correlation_id` 决定的 decision，`artifact_version == "bootstrap"`
- `export-replay` 无额外参数即可导出 JSON fixture
- Replay 时 caller 跑一次 pipeline 就可以，不需要 artifact 文件

### 7.2 Fitted 决策需要 artifact promotion

- `artifact_version != "bootstrap"` 的决策导出需要显式 flag
- `--allow-fitted-artifacts --artifact-dir <path> --artifact-output-dir <archive>`
- 导出器会：
  1. `validate_artifact_bundle(path, expected_version)` — 防止拿错 artifact 导出
  2. `archive_artifact_bundle(path, archive)` — 归档到 fixture 旁边
  3. 写 `replay_artifact_manifest.json` — bundle 元信息
  4. Fixture JSON 里记录 `requires_artifact_version` + `artifact_bundle`

**这是本项目最容易被 code review 忽视的复杂度**。Fitted replay fixture 不
是简单的"JSON 落盘"，而是"JSON + artifact bundle + manifest"的三元组。

### 7.3 模型回滚

回滚 = 用旧 artifact 替换新 artifact + restart pod：

```bash
# 假设旧 artifact 归档在某处
rsync -a backup/training_artifacts/2026-04-01/ /state/training_artifacts/
kubectl rollout restart deployment/gan-matchmaking
```

**回滚不丢决策审计**：SQLite `decisions` 表保留所有版本的决策记录，
通过 `artifact_version` 可以区分"回滚前的决策"和"回滚后的决策"。

## 8. 失败模式

| 失败场景 | 系统行为 | 告警点 |
|---|---|---|
| Artifact 文件不存在 | 降级 bootstrap | 低优（可能是首次部署） |
| Artifact 文件存在但 metadata 缺失 | 用 "unversioned" 兜底 metadata | 中（数据不完整） |
| Artifact 形状不对 | 降级 bootstrap + `validation_errors` | 高（训练/运行不一致） |
| feature_names 不对 | 同上 | 高（契约破坏） |
| weights 含 NaN | 同上 | 高（训练出问题） |
| 训练 job 挂了 | artifact 不更新，runtime 用旧版 | 中（从 last_trained_at 推断） |
| PVC 只读 | artifact 无法写入 | 高（训练失败） |

## 9. 改进方向

### 9.1 已识别（`claude-review/findings.md`）

- **F-005**: rating scaling 常数没进 metadata，未来改动会静默破坏 artifact
- **F-006**: `artifacts.py` 488 行，可拆

### 9.2 待探索

- **Object storage backend**: artifact 从本地文件升级到 S3 / GCS
  - 好处：多副本共享、版本归档天然
  - 代价：hydrate 依赖网络
- **Atomic artifact swap with blue/green**: 两份 artifact 并存，pipeline
  根据 config 选
  - 好处：回滚 < 1 秒
  - 代价：存储翻倍 + config 复杂
- **Artifact signing**: 用 build pipeline 的 private key 给 metadata 签名
  - 好处：防止手工改过的 artifact 混入
  - 代价：需要密钥管理

这三条都不是本期范围，记录在此供下一个 review cycle 讨论。

## 10. 参考

- 代码：`gan_matchmaking/sre/artifacts.py`, `gan_matchmaking/training/`
- ADR：`adr/0005-fallback-strategy-for-untrained-models.md`,
  `adr/0006-runtime-artifact-versioning.md`
- 测试：`tests/test_sre_self_iteration.py::test_pipeline_hydrates_runtime_artifacts`,
  `tests/test_sre_self_iteration.py::test_invalid_artifact_manifest_falls_back`,
  `tests/test_replay_export.py`, `tests/test_training.py`
