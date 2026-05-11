# Patch · F-001 LeaseRefreshLoop 可见化

## 当前代码锚点

### `gan_matchmaking/sre/leases.py`

**当前 `LeaseRefreshLoop` (L195-234)**:

```python
class LeaseRefreshLoop:
    """Context manager that keeps a lease fresh while a server runs."""

    def __init__(
        self,
        lease: FileLease,
        *,
        interval_seconds: Optional[float] = None,
    ) -> None:
        self.lease = lease
        self.interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.error: Optional[BaseException] = None

    def __enter__(self) -> "LeaseRefreshLoop":
        self.lease.acquire()
        interval = self.interval_seconds
        if interval is None:
            interval = max(1.0, min(self.lease.ttl_seconds / 3.0, 30.0))
        self._thread = threading.Thread(
            target=self._run,
            args=(float(interval),),
            name="gan-lease-refresh",
            daemon=True,
        )
        self._thread.start()
        return self

    def _run(self, interval: float) -> None:
        while not self._stop.wait(interval):
            try:
                self.lease.refresh()
            except BaseException as exc:  # pragma: no cover - surfaced by ``error``.
                self.error = exc
                self._stop.set()
                return

    def __exit__(self, exc_type, exc, tb) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self.lease.release()
```

## 目标代码

```python
class LeaseRefreshLoop:
    """Context manager that keeps a lease fresh while a server runs.

    A background thread periodically refreshes the lease. If the refresh
    call ever raises, the exception is stored on ``self.error`` for
    backwards compatibility **and** forwarded to the ``on_failure``
    callback so callers can flip their readiness state / increment
    metrics. The refresh thread always exits after the first failure —
    the assumption is that the owning process will restart or fail its
    readiness probe rather than keep retrying.
    """

    def __init__(
        self,
        lease: FileLease,
        *,
        interval_seconds: Optional[float] = None,
        on_failure: Optional[Callable[[BaseException], None]] = None,
    ) -> None:
        self.lease = lease
        self.interval_seconds = interval_seconds
        self.on_failure = on_failure
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.error: Optional[BaseException] = None

    def __enter__(self) -> "LeaseRefreshLoop":
        self.lease.acquire()
        interval = self.interval_seconds
        if interval is None:
            interval = max(1.0, min(self.lease.ttl_seconds / 3.0, 30.0))
        self._thread = threading.Thread(
            target=self._run,
            args=(float(interval),),
            name="gan-lease-refresh",
            daemon=True,
        )
        self._thread.start()
        return self

    def _run(self, interval: float) -> None:
        while not self._stop.wait(interval):
            try:
                self.lease.refresh()
            except BaseException as exc:
                self.error = exc
                if self.on_failure is not None:
                    try:
                        self.on_failure(exc)
                    except Exception:
                        # Callback failure must not mask the original cause.
                        pass
                self._stop.set()
                return

    def __exit__(self, exc_type, exc, tb) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self.lease.release()
```

变更点：

1. `__init__` 参数新增 `on_failure: Optional[Callable[[BaseException], None]] = None`
2. 删除 `# pragma: no cover - surfaced by ``error``.` 注释
3. 捕获到异常后调用 `on_failure(exc)`（用 try/except 包住避免 callback 抛错破坏原 exc 记录）

### `gan_matchmaking/service/app.py`

当前 `DecisionApp` 是 `@dataclass`。新增字段 + 方法。注意 `handle_ready`
原来签名是 `def handle_ready(self, _body)`（tuple返回）。

**新增私有辅助**（放在文件顶部 dataclass 之前）：

```python
def _make_healthy_event() -> threading.Event:
    evt = threading.Event()
    evt.set()
    return evt
```

**`DecisionApp` 字段新增**（在 `readiness_breaker: Optional[CircuitBreaker] = None` 之后）：

```python
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    _lease_healthy: threading.Event = field(
        default_factory=_make_healthy_event, init=False
    )
    _lease_unhealthy_details: dict = field(default_factory=dict, init=False)
    _lease_path: Optional[str] = field(default=None, init=False)
    _lease_owner: Optional[str] = field(default=None, init=False)
    m_lease_refresh_failures: Any = field(default=None, init=False)

    def __post_init__(self) -> None:
        # Counter may be registered on the pipeline's shared registry.
        self.m_lease_refresh_failures = self.pipeline.metrics.counter(
            "gan_lease_refresh_failures_total",
            "Number of lease refresh failures seen by the HTTP service.",
            label_names=("reason",),
        )
```

**新增方法**（放在 `handle_get_service` 之后）：

```python
    def bind_lease_metadata(self, *, path: str, owner: str) -> None:
        """Record lease identity for later log/metric emission."""
        self._lease_path = path
        self._lease_owner = owner

    def mark_lease_unhealthy(self, exc: BaseException) -> None:
        """Flip readiness, increment metric, emit structured log.

        Idempotent: subsequent calls while already unhealthy are no-ops.
        """
        with self._lock:
            if not self._lease_healthy.is_set():
                return
            reason = type(exc).__name__
            self._lease_unhealthy_details = {
                "reason": reason,
                "message": str(exc)[:200],
            }
            self.m_lease_refresh_failures.inc(labels={"reason": reason})
            self._lease_healthy.clear()
        self.pipeline.logger.error(
            "lease.refresh.failed",
            lease_path=self._lease_path or "unknown",
            owner=self._lease_owner or "unknown",
            error_type=reason,
        )
```

**`handle_ready` 修改**（在现有 breaker 检查之前）：

```python
    def handle_ready(self, _body: Optional[JsonDict]) -> Tuple[int, JsonDict]:
        if not self._lease_healthy.is_set():
            return 503, {"status": "not_ready",
                         "reason": "lease_unhealthy",
                         "details": dict(self._lease_unhealthy_details)}
        breaker = self.readiness_breaker or self.pipeline.circuit_breaker
        if breaker is None or breaker.allow():
            return 200, {"status": "ready"}
        return 503, {"status": "not_ready",
                     "breaker": breaker.snapshot()}
```

### `gan_matchmaking/service/__main__.py`

**当前**：

```python
if args.lease_file:
    lease = FileLease(
        Path(args.lease_file),
        owner=args.lease_owner,
        ttl_seconds=args.lease_ttl_seconds,
    )
    with LeaseRefreshLoop(lease):
        run_wsgi(app, host=args.host, port=args.port)
else:
    run_wsgi(app, host=args.host, port=args.port)
```

**改为**：

```python
if args.lease_file:
    lease = FileLease(
        Path(args.lease_file),
        owner=args.lease_owner,
        ttl_seconds=args.lease_ttl_seconds,
    )
    app.bind_lease_metadata(path=args.lease_file, owner=args.lease_owner)
    with LeaseRefreshLoop(lease, on_failure=app.mark_lease_unhealthy):
        run_wsgi(app, host=args.host, port=args.port)
else:
    run_wsgi(app, host=args.host, port=args.port)
```

## 测试函数签名

```python
# tests/test_leases.py

def test_refresh_failure_flips_readiness(tmp_path):
    from gan_matchmaking.core import MetricsRegistry
    from gan_matchmaking.service.app import build_app
    app = build_app(metrics=MetricsRegistry())
    app.bind_lease_metadata(path=str(tmp_path / "state.lock"), owner="test:1")
    app.mark_lease_unhealthy(RuntimeError("boom"))
    code, body = app.handle_ready(None)
    assert code == 503
    assert body["reason"] == "lease_unhealthy"
    assert body["details"]["reason"] == "RuntimeError"

def test_refresh_failure_increments_metric(tmp_path):
    ...
    snap = app.pipeline.metrics.get("gan_lease_refresh_failures_total").snapshot()
    assert snap.get((("reason","RuntimeError"),)) == 1.0

def test_refresh_failure_emits_structured_log(tmp_path, caplog_json):
    # caplog_json 是新增的 fixture,参见 conftest.py
    ...

def test_refresh_failure_does_not_spam(tmp_path):
    app = build_app(metrics=MetricsRegistry())
    app.bind_lease_metadata(path="/tmp/lock", owner="test")
    app.mark_lease_unhealthy(RuntimeError("a"))
    app.mark_lease_unhealthy(RuntimeError("b"))
    app.mark_lease_unhealthy(RuntimeError("c"))
    snap = app.pipeline.metrics.get("gan_lease_refresh_failures_total").snapshot()
    # 只有第一条被记
    assert sum(snap.values()) == 1

def test_healthy_app_returns_ready():
    app = build_app(metrics=MetricsRegistry())
    code, body = app.handle_ready(None)
    assert code == 200
    assert body["status"] == "ready"

def test_loop_invokes_callback_on_refresh_failure(tmp_path):
    from gan_matchmaking.sre.leases import FileLease, LeaseRefreshLoop
    calls = []
    path = tmp_path / "state.lock"
    lease = FileLease(path, owner="test", ttl_seconds=0.5)
    lease.acquire()
    try:
        # 强制 refresh 失败:删掉文件让 refresh 认为 ownership lost
        path.unlink()
        # 手动注入一次 refresh 异常
        try:
            lease.refresh()
        except Exception as exc:
            calls.append(("direct", type(exc).__name__))
        assert calls[0][0] == "direct"
    finally:
        lease.release()
        # 如果文件已删就不再 unlink
```

## 预计 LOC

- `leases.py`: +5 / -1
- `service/app.py`: +35 / -0
- `service/__main__.py`: +2 / -0
- `tests/test_leases.py`: +90 / -0

总计约 +130 LOC，单 PR 可管理。
