# 06 · Concurrency & Leases

本系统需要在**三个不同粒度**上防止状态竞争：

1. **线程级**: 同进程内多个 decide 并发
2. **进程级**: 同节点多个 pod / 手动启动的进程
3. **节点级**: 多节点多副本

三种粒度分别对应三种工具，混用会出事。

## 1. 问题矩阵

| 并发粒度 | 出问题的场景 | 今天用什么防护 | 够不够? |
|---|---|---|---|
| 同进程多线程 | HTTP server 多 worker 同服务 decide | `PerServiceLock` (RLock per service_id) | ✅ 够 |
| 同节点多进程 | 误启两次 `python -m gan_matchmaking.service`；滚动升级瞬态 | `FileLease` | ✅ 够（单节点 RWO PVC） |
| 多节点多副本 | 跨 pod 同时写 SQLite 或 artifact | ⚠️ **无** | ❌ 必须换后端 |

## 2. 线程级: `PerServiceLock`

### 2.1 契约

```python
class PerServiceLock:
    def acquire(self, key: str, timeout: float = 30.0) -> ContextManager:
        ...
```

- 按 `service_id` 串行化
- 可重入（RLock），方便递归调用
- 超时默认 30 秒，抛 `TimeoutError`

### 2.2 使用点

```python
# decide()
with self._service_locks.acquire(ctx.service.id):
    decision = self._decide_locked(ctx)

# observe_release()
with self._service_locks.acquire(service_id):
    ...
```

### 2.3 不变量

- 并发 decide(svc=A) 和 decide(svc=A) 串行
- 并发 decide(svc=A) 和 decide(svc=B) 并行（不同 key）
- decide(svc=A) 期间 observe_release(svc=A) 必须等待（同 key）
- 单个锁持有期间不得做 I/O 以外的长耗时操作

### 2.4 不防护什么

- ❌ 跨进程（两个 pod 各有一份 `PerServiceLock`）
- ❌ 死锁（锁粒度就是 service_id，不会循环等待）
- ❌ 锁里抛异常的状态回滚（异常会传播，caller 自己负责重试）

## 3. 进程级: `FileLease`

### 3.1 契约

```python
class FileLease:
    path: str | Path         # 锁文件路径
    owner: str               # 人类可读的持有者标识（hostname:pid）
    ttl_seconds: float       # TTL，过期可被接管

    def acquire(self) -> FileLease
    def refresh(self) -> LeaseSnapshot
    def release(self) -> None
```

### 3.2 原子性机制

```python
os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
```

- `O_EXCL` 保证"文件已存在"时 `acquire` 会失败
- 不用 `fcntl.flock` 是因为想让事后 `cat lockfile.json` 人工审查容易
- Lease payload 是纯 JSON，包含 owner / token / pid / acquired_at / expires_at

### 3.3 过期接管

```python
# 读到的 lease 已过期
if current.expires_at <= now():
    path.unlink()                  # 删掉
    continue                       # 重新 O_EXCL create
```

**过期接管不保证绝对单写者**——如果节点时钟漂移超过 TTL，两个节点都可能认为
锁已过期。这是 ADR-0007 明确声明的边界条件。**TTL 推荐 ≥ 60s**，节点 NTP 容忍度
应该 < 1s。

### 3.4 后台续租: `LeaseRefreshLoop`

```python
class LeaseRefreshLoop:
    def __enter__(self):
        self.lease.acquire()
        self._thread = threading.Thread(target=self._run, ...)
        ...
```

**已知问题**（F-001）：续租失败仅写到 `self.error`，无 caller 读它。
`run_wsgi` 是 blocking 循环，lease 过期后另一个 pod 接管 → split-brain。

**推荐修复（PR-fix-01）**：
- 续租失败 → `readiness_flag.clear()` → `/readyz` 返 503
- 或 → `httpd.shutdown()` 让主循环退出

## 4. 节点级: 当前**不支持** multi-writer

### 4.1 为什么不支持

- SQLite ReadWriteOnce PVC 天然只能一个 pod 挂载
- `FileLease` 在 RWO PVC 上 scale 出去就失去意义（另一个节点看不到锁文件）
- 多 pod 想共享状态必须走外部 DB

### 4.2 硬约束（ADR-0007）

```yaml
# deploy/kubernetes/deployment.yaml
spec:
  replicas: 1             # ← 硬约束
  strategy:
    type: Recreate        # ← 滚动更新禁止（避免短暂双写）
```

### 4.3 多副本的升级路径

按 [`adr/0007-single-writer-lease-boundary.md`](../adr/0007-single-writer-lease-boundary.md)
的规划，升级路径是：

```
v1 (today)          SQLite  + FileLease + replicas=1
v2 (if needed)      SQLite  + KubernetesLease  + Leader pod only writes
v3 (full scale)     Postgres/MySQL + advisory lock + replicas=N
```

每一步都必须补一条 ADR。

## 5. 死锁 / 饥饿分析

### 5.1 可能的死锁

**目前没有真实死锁风险**，因为：
- `PerServiceLock` 粒度 = service_id，不存在 A→B→A 的环
- `FileLease` 不嵌套其他锁
- SQLite 在 `timeout=5.0s` 配合 WAL 模式下自己管事务

### 5.2 可能的饥饿

**场景**: 一个服务被持续决策（比如它在 WARN 状态，caller 循环重试），其他
对同服务的 `observe_release` 可能排队很久。

**缓解**:
- `acquire(timeout=30.0)` 会抛 TimeoutError，不会永远等
- Caller 看到 TimeoutError 应该 back-off 而非立即重试
- 长期看：引入 priority-aware 锁（decide 可被 observe 抢占）不是目前范围

### 5.3 RLock 的重入

`PerServiceLock` 用 RLock，**同一线程内嵌套持有是允许的**。例如：

```python
with svc_lock.acquire("svc-a"):
    some_helper()  # 里面又 acquire("svc-a") 也不会死锁
```

注意：跨线程的嵌套是**阻塞**的，不是 reentrant。

## 6. 原子性保证

这张表列出每个写操作的原子性：

| 写操作 | 原子性级别 | 实现 |
|---|---|---|
| `Service` state 内存更新 | 单线程下原子（GIL） | Python object assignment |
| SQLite `services` 表写入 | 数据库级原子 | `BEGIN IMMEDIATE` + `COMMIT` |
| `record_decision` 写入 | 数据库级原子 + UPSERT 幂等 | `ON CONFLICT DO UPDATE` |
| 并发两个 service_id 更新 | 独立 | 不同的 service_id 走不同锁、不同行 |
| Artifact 文件写入 | 弱原子 | `np.savez` 实际是 write + rename，但不是 `fsync` |
| `FileLease` 创建 | POSIX 原子 | `O_CREAT \| O_EXCL` |

**注意**：artifact 文件写入的原子性不强。训练 job 异常死掉可能留下半个文件。
目前靠 "下次训练覆盖" 自愈，没有 corruption 检测。这是可接受的，因为
`validate_*_artifact` 会拒绝加载 corrupt 文件。

## 7. 测试矩阵

| 测试 | 位置 | 覆盖 |
|---|---|---|
| 同 service_id 并发串行 | 🔴 **建议补** (CG-009) | 线程级 |
| Lease exclusion | `tests/test_leases.py::test_file_lease_excludes_second_owner` | 进程级 |
| Lease takeover after TTL | `tests/test_leases.py::test_file_lease_takes_over_expired_owner` | 进程级 |
| Refresh 失败可见性 | 🔴 **缺失** (F-001 / CG-001) | 进程级 |
| Multi-writer safety | N/A | 节点级（不支持） |

## 8. 故障注入 checklist

合入重大改动时应该能回答：

- [ ] 两个 decide 同时进来会不会错？
- [ ] 拿着 lock 抛异常锁会释放吗？
- [ ] Lease 文件被 rm 会怎样？
- [ ] Pod OOM 被 kill 后 lease 什么时候可以被接管？
- [ ] SQLite busy 超时后会 retry 吗？
- [ ] PVC 满了 observe_release 会不会污染 in-memory 状态？

这些是 runbook 的素材，也是未来 chaos test 的候选。

## 9. 参考

- 代码：`sre/locking.py`, `sre/leases.py`, `service/__main__.py`
- ADR：`adr/0007-single-writer-lease-boundary.md`
- Runbook：`runbooks/multi-instance-lease.md`
- 测试：`tests/test_leases.py`
- Findings：`claude-review/findings.md#f-001`
