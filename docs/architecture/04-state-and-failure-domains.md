# 04 · State & Failure Domains

本文回答两个问题：

1. **哪些东西是状态？** — 分布在哪里、谁能改、怎么恢复
2. **哪些东西会失败？** — 失败域多大、影响面多广、怎么降级

## 1. 状态清单（按 durability 分级）

### 1.1 Durable 状态（进程重启保留）

| 状态 | 位置 | 写入者 | 恢复方式 |
|---|---|---|---|
| Service 可靠性 (μ, σ, streaks, total) | SQLite `services` 表 | `observe_release()` | 启动时 hydrate 到 `pipeline._services` |
| Dependency synergy 图 | SQLite `synergy_edges` 表 | `observe_release()` 或 `SynergyRepository.increment()` | 启动时 hydrate 到 `pipeline.synergy_graph` |
| 决策审计行 | SQLite `decisions` 表 | `_finalize_decision()` | 永久保留（不回放到运行态） |
| 观测日志 | SQLite `observations` 表 | `observe_release()` | 训练用，不回放到运行态 |
| Retention / Cox artifacts | 文件系统 | 训练 job | 启动时 hydrate 到 `eomm.model` / `risk.model` |
| Schema 版本 | SQLite `schema_migrations` | 启动时 migration | 自启动 |
| Lease 文件 | 本地文件系统 | `FileLease.acquire()` | TTL 过期后可被接管 |

### 1.2 Ephemeral 状态（进程生命周期内有效）

| 状态 | 位置 | 丢失后影响 |
|---|---|---|
| PCA basis | `pipeline.pca` | 重新 fit，单次决策延迟 +<1ms |
| GNN forward cache | 无缓存，每次前向 | 无影响 |
| Circuit breaker 状态 | `pipeline.circuit_breaker` 内存 | 失败计数重置，可能放过一次试探 |
| Shadow mode | config 字段 | 重启后按 config 读新值 |
| Per-service lock | `PerServiceLock._locks` | 下次 decide 重建 |
| Metrics 快照 | in-process registry | Prometheus scrape 间隙丢失 |

### 1.3 不持久化的关键决策（设计选择）

- **不持久化**: Lease refresh 失败的累计次数
  - 理由：breaker 已经做了，lease 只用短期状态判定
  - **风险**: 见 F-001，失败被静默化
- **不持久化**: PCA basis（每次 decide 重新 fit 短窗口 telemetry）
  - 理由：telemetry 只用于短期信号，长期特征走 Cox
- **不持久化**: Candidate scores 历史（仅写在 trace 里）
  - 理由：训练需要时从 `observations` 表重建

## 2. Failure Domain 视图

```mermaid
flowchart TD
  subgraph DD["决策域 (一次 decide)"]
    D1[PCA 失败]
    D2[GNN 失败]
    D3[Adjusted Probs 异常]
    D4[Entropy 失败]
    D5[EOMM artifact 失败]
    D6[Risk 失败]
  end

  subgraph SD["服务域 (一个 service_id)"]
    S1[Lock 超时]
    S2[Observe 更新冲突]
    S3[Service hydrate 失败]
  end

  subgraph PD["进程域 (一个 pipeline 实例)"]
    P1[SQLite 损坏]
    P2[Artifact 加载失败]
    P3[Circuit breaker 长期 open]
    P4[Lease 过期未续租]
  end

  subgraph ND["节点域 (整台机器)"]
    N1[PVC 无可用空间]
    N2[内存不足 OOM]
    N3[CPU starvation]
  end

  subgraph CD["集群域 (跨节点)"]
    C1[DNS 解析失败]
    C2[时间漂移]
  end

  DD -.退化.-> 单决策退化为 HOLD/CANARY
  SD -.退化.-> 单服务决策失败，其他服务不受影响
  PD -.退化.-> 整个 pipeline 实例不可用，K8s 重启
  ND -.退化.-> Pod 被驱逐，ReadWriteOnce PVC 重新挂载
  CD -.风险.-> 可能导致 lease 冲突，需人工介入
```

## 3. 每个 Failure Domain 的降级契约

### 3.1 决策域（DD）· stage 级失败

**策略**: **单 stage 失败不影响决策生成**。每个 stage 都有 fallback：

| Stage | Fallback 行为 |
|---|---|
| PCA | `fused = ctx.service.mu` |
| GNN | `score = 0.0` |
| Adjusted Probs | 无 catch（失败即抛，极少见） |
| Entropy | 空 acceptable → 取 argmax-H |
| EOMM | artifact 分支失败 → 切 fallback 规则 |
| Risk | Cox 失败 → `prob=0.5, level=warn` |

**检测**: `gan_stage_failures_total{stage}` 递增 + `stage.<name>.degraded` 日志。

**SLO**: 单 stage 失败率 < 0.1%。超过阈值触发告警。

### 3.2 服务域（SD）· 单服务级失败

**策略**: **一个服务的状态损坏不污染其他服务**。通过 per-service lock
+ per-service 字典隔离。

**场景**:
- Service `svc-a` 的 `observe_release` 竞争超时 → 抛 `TimeoutError`，caller
  自行重试
- `svc-a` 在 SQLite 里没有对应行 → 抛 `DataError`，caller 创建 service 或退出
- `svc-a` 的 synergy 边数据损坏 → 降级为空图，`stage.synergy.degraded` 日志

**边界**: `svc-a` 的故障不能让 `svc-b` 的 decide 延迟或失败。

### 3.3 进程域（PD）· pipeline 实例级失败

**策略**: **kill -9 也能恢复**。状态全在 SQLite + artifact 文件，重启 hydrate。

**场景**:
- SQLite WAL 文件损坏 → pipeline 启动失败，pod crashloop → 人工介入修复
- Artifact 目录权限错误 → 降级 bootstrap，`trace.artifacts.validation_errors`
- Circuit breaker 长期 open → `/readyz` 返 503，k8s 切流量
- Lease 过期未续租（F-001） → **当前不会自动恢复**，这是 P1 修复项

**SLO**:
- 进程启动 hydrate < 5 秒
- SIGTERM 到退出 < 3 秒（没有长尾 cleanup）

### 3.4 节点域（ND）· 单节点失败

**策略**: K8s Deployment + Recreate 策略，pod 迁移到新节点。

**场景**:
- PVC 满 → 写 observations 失败 → `DataError`。需要 runbook 响应
- 节点宕机 → PVC unbind → 新 pod 在新节点 bind PVC
- OOM → pod 重启，hydrate 恢复

**边界**: ReadWriteOnce PVC 决定了我们**不能**在节点宕机时立即起备份节点，
必须等 PVC unbind。这是已接受的 SPOF，由 ADR-0007 声明。

### 3.5 集群域（CD）· 跨节点问题

**策略**: 目前架构**不防**集群级故障。只有分布式 lease + 外部 DB 才能应对。

**场景**:
- 时间漂移超过 lease TTL → 两个 pod 都认为 lease 有效 → **split-brain**
  - 缓解：lease TTL ≥ 最大允许时钟漂移（推荐 60s，节点 NTP 容忍度 < 1s）
- 网络分区 → SQLite 无共享受影响（单机），artifact 无共享受影响（本地文件）
- DNS 不可用 → pipeline 本身不依赖 DNS

## 4. 恢复时间目标（RTO / RPO）

| 故障类型 | RTO (恢复时间) | RPO (数据丢失) | 依赖 |
|---|---|---|---|
| Pod restart | < 30s | 0 | K8s restart + hydrate |
| 节点迁移 | < 2min | 0 | PVC unbind + rebind |
| SQLite 损坏 | 手动 | 到上次备份 | 需要外部备份策略 |
| Artifact 损坏 | < 30s | 0 (降级 bootstrap) | 自动降级 + 重训 |
| Lease 过期 | < TTL (60s) | 潜在的 split-brain 写入 | **需要 F-001 修复** |

## 5. 数据一致性边界

### 5.1 读写一致性

- **Pipeline ↔ SQLite**: 同步写，强一致
- **Pipeline ↔ Artifact**: 启动时 hydrate，运行时不重读（重启才生效）
- **SQLite ↔ Training Job**: 训练 job 读 SQLite 快照，不影响线上决策

### 5.2 观测 → 训练 → 部署的最终一致性

```
observe_release → SQLite observations 表 (T+0)
                      ↓ daily cronjob
                  training job 读 SQLite (T+24h)
                      ↓ output
                  新 artifact bundle (T+24h+ε)
                      ↓ 下次 pipeline 启动
                  runtime hydrate (T+24h+pod_restart)
```

最终一致性延迟 = 训练周期 + pod 重启间隔。当前默认 **~24h**。

## 6. 写入幂等性

| 操作 | 幂等? | 保护手段 |
|---|---|---|
| `observe_release(svc, success, ...)` | ❌ 非幂等 | caller 自己去重（correlation_id 不会自动判重） |
| `decide(ctx)` 返回 | ✅ 同 ctx + seed → 同 decision | 确定性构造 |
| `record_decision(correlation_id, ...)` | ✅ UPSERT | `ON CONFLICT(correlation_id) DO UPDATE` |
| Schema migration | ✅ | `schema_migrations` 表追踪，见 F-008 |
| Artifact save | ✅ | 内容寻址 + overwrite by name |

## 7. 参考

- 代码：`gan_matchmaking/persistence/sqlite.py`, `gan_matchmaking/sre/self_iteration.py`
- 对应 ADR：0004（determinism）、0005（fallback）、0007（lease）
- 对应 runbook：`reproduce-decision.md`, `bootstrap-new-service.md`
