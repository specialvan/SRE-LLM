# Action Items · Post-Review Work List

> These items are **for codex to execute next**. Each item is written to be self-contained:
> goal, acceptance criteria, file touchpoints, and test requirements.
>
> **Execution order**: P1 → P2 → P3.
> **Commit discipline**: one P1 per commit. P2/P3 may be batched if they touch disjoint files.
> **Do not** break any of the 7 guardrails in [`README.md`](./README.md).

Reference for context:
- [`00-review-report.md`](./00-review-report.md) — why these items exist
- [`01-detailed-architecture.md`](./01-detailed-architecture.md) — API contracts and invariants
- [`04-midflight-review.md`](./04-midflight-review.md) — **how codex consumed this file so far (read if resuming)**

---

## Changelog

> Actions here sometimes get refined after codex starts. Record each meaningful change with date + AI-ID + what changed, so an in-flight implementer knows whether to pick up deltas.

| Date | AI | Change |
| --- | --- | --- |
| 2026-05-12 | AI-4 | Added `max_dead_letters=1000` (FIFO cap) + `dead_letters_dropped` counter + companion test. See §5 of [`04-midflight-review.md`](./04-midflight-review.md) for patch guidance if you've already implemented AI-4. |
| 2026-05-12 | AI-1 | Default `max_history_ticks=10_000` confirmed — do not block P1 on cadence discussion. |
| 2026-05-12 | AI-2 | Clarified behavior when both `min_safe_samples` and `min_safe_evidence` are explicit (accept as-is, emit warning only if evidence is stricter than samples). |
| 2026-05-12 | AI-3 | Design question closed: `Lock` (not `RLock`). Codex chose `RLock` anyway; accepted retroactively in [`../adr/0001-contraction-wrapper-uses-rlock.md`](../adr/0001-contraction-wrapper-uses-rlock.md). |

---

## Priority summary

| ID | Priority | Title | Est. LoC | Files touched |
| --- | --- | --- | --- | --- |
| AI-1 | 🟡 P1 | Bound `TemporalCreditAssigner._history` | ~60 | `sre_math.py` + tests |
| AI-2 | 🟡 P1 | Disambiguate `min_safe_samples` under soft labels | ~80 | `sre_self_envelope.py` + tests + doc |
| AI-3 | 🟢 P2 | Thread-safe `ContractionAwareEnvelope` | ~30 | `sre_self_envelope.py` + tests |
| AI-4 | 🟢 P2 | Streaming replay: optional `skip_bad_lines` | ~40 | `sre_math.py` + tests |
| AI-5 | 🟢 P3 | Document dual-evidence in `observe()` | ~15 | `sre_self_envelope.py` only |
| AI-6 | 🟢 P3 | Explicit empty-input check in `_weighted_quantile` | ~5 | `sre_self_envelope.py` + 1 test |
| AI-7 | 🟢 P3 | Document DDP caveat for `share_key=False` | ~20 | `docs/ARCHITECTURE.md` |

**Total budget**: ~250 LoC + ~15 new tests across 7 items.

---

## AI-1 🟡 P1 · Bound `TemporalCreditAssigner._history`

### Problem
`TemporalCreditAssigner._history` grows without bound. `CreditAwareLabeler.__call__` invokes
`attribute()` every tick, which iterates the whole history. In long-running processes this
causes unbounded memory growth and linearly-increasing per-tick latency.

### Target behavior
- Optional parameter `max_history_ticks: Optional[int] = 10_000` at construction.
- When `None`: keep current unbounded behavior (preserves backward compatibility for tests
  that rely on short-run determinism).
- When set: internal buffer is a bounded deque; oldest records dropped when full.
- `attribute()` algorithmic result must be identical for tick windows that still lie inside
  the retained buffer.

### Acceptance criteria
1. Construction validates `max_history_ticks is None or max_history_ticks >= 1`.
2. `record()` is O(1) amortized regardless of history length.
3. `attribute()` still filters by `window` parameter, so exceeding-window records that happen
   to survive eviction are still ignored.
4. When `max_history_ticks` is smaller than `window`, the effective result is limited by
   available history (graceful, not an error).
5. New public `__len__` returns current retained count.
6. New public `.evicted_count` exposes how many records have been dropped (for audit).
7. All existing `test_sre_math.py::test_credit_assigner_*` tests pass unchanged.

### Test specification
Add to `tests/test_sre_math.py`:

```python
def test_credit_assigner_honors_max_history():
    tca = TemporalCreditAssigner(decay=1.0, max_history_ticks=3)
    for t in range(10):
        tca.record(t, weights=np.array([1.0]), losses=np.array([1.0]),
                   signal_names=["only"])
    assert len(tca) == 3
    assert tca.evicted_count == 7
    # attribute at an old tick no longer returns those entries
    assert tca.attribute(incident_tick=5, window=100) == []
    # attribute at a recent tick still works
    assert len(tca.attribute(incident_tick=9, window=100)) == 3

def test_credit_assigner_unbounded_by_default():
    tca = TemporalCreditAssigner(decay=1.0)
    for t in range(50):
        tca.record(t, weights=np.array([1.0]), losses=np.array([1.0]),
                   signal_names=["only"])
    assert len(tca) == 50
    assert tca.evicted_count == 0

def test_credit_assigner_max_history_validation():
    with pytest.raises(ValueError):
        TemporalCreditAssigner(max_history_ticks=0)
    with pytest.raises(ValueError):
        TemporalCreditAssigner(max_history_ticks=-1)
```

### Files touched
- `attention_residuals/sre_math.py` — `TemporalCreditAssigner` class.
- `tests/test_sre_math.py` — three new tests.
- `docs/ARCHITECTURE.md` — update "known limitations" row 1 to "closed as of AI-1".

### Implementation hint
Use `collections.deque(maxlen=max_history_ticks)` when bounded; keep `list` when `None`.
Both support iteration, len, and append-right efficiently.

### Default decision (closed during review)

`max_history_ticks=10_000` 作为 P1 实现时的**默认值**。理由：
- 1 tick/s 的控制循环 → ≈ 2.8 小时历史（够一次 post-mortem 窗口）
- 0.1 tick/s 的扩缩容控制器 → ≈ 28 小时历史
- `attribute()` 在 10k 条上 < 1 ms，足以放在 CreditAwareLabeler 热路径上

若部署 cadence 更高（≥ 10 tick/s）或更低（每小时一次），在 PR 描述里记录建议调优值，但**不要阻塞 P1 合入**。

### Performance bar
Before: `attribute()` on 100k records: ~8 ms per call.
After: `attribute()` on 10k-bounded deque: ~0.8 ms per call.
Measure with `python -m timeit` and report numbers in the commit message.

---

## AI-2 🟡 P1 · Disambiguate `min_safe_samples` under soft labels

### Problem
`LearnedSafetyEnvelope.fit()` currently compares `sum(self._safe_weights)` against
`min_safe_samples`. Docstring says "Minimum SAFE observations in the buffer". Under soft
labels with mean confidence 0.5, operators set `min_safe_samples=20` expecting a 20-record
check but effectively getting a 40-record check.

### Target behavior
Add a second threshold and keep both:
- `min_safe_samples: int = 20` — keeps current meaning: **number of records** in the SAFE
  buffer (with any positive safe_weight).
- `min_safe_evidence: float = 20.0` — new: **sum of safe_weights**.
- Fit gates on BOTH (whichever is stricter). Default values align so hard-label behavior is
  unchanged.

### Acceptance criteria
1. Constructor validates both parameters (≥ 0) and `buffer_size ≥ min_safe_samples`.
2. If both `min_safe_samples` and `min_safe_evidence` unmet → reason ends with both codes.
   Example: `"insufficient_safe_samples"` or `"insufficient_safe_evidence"` or
   `"insufficient_safe_samples,insufficient_safe_evidence"`.
3. `fit()` summary dict adds `n_safe_records` and `safe_evidence` (already present, verify).
4. Hard-label case (all `confidence=1`) produces identical behavior to Round 9 code.
5. Soft-label case (`confidence=0.5`) requires 40 records to satisfy
   `min_safe_evidence=20` but only 20 to satisfy `min_safe_samples=20` — so the effective
   gate is the harder one.
6. Update docstring with explicit formula and example.

### Test specification
Add to `tests/test_sre_self_envelope.py`:

```python
def test_fit_gates_on_both_record_count_and_evidence():
    env = _fresh_env(
        min_safe_samples=10,
        min_safe_evidence=20.0,
        unsafe_quorum=3,
    )
    # Record 10 records with soft confidence 0.5 → only 5 units of evidence.
    for _ in range(10):
        env.observe(np.array([0.5]),
                    OutcomeEvidence(safety_score=1.0, confidence=0.5))
    for _ in range(3):
        env.observe(np.array([0.0]), OutcomeLabel.UNSAFE)
    s = env.fit()
    assert "insufficient_safe_evidence" in s["reason"]
    # Add more soft records to satisfy evidence gate.
    for _ in range(30):
        env.observe(np.array([0.5]),
                    OutcomeEvidence(safety_score=1.0, confidence=0.5))
    for _ in range(3):
        env.observe(np.array([0.0]), OutcomeLabel.UNSAFE)
    s = env.fit()
    assert s["reason"] != "insufficient_safe_samples"
    assert s["reason"] != "insufficient_safe_evidence"

def test_fit_gates_backward_compatible_hard_labels():
    """Hard-label behavior unchanged from Round 9."""
    env = _fresh_env(min_safe_samples=20, unsafe_quorum=3)
    for _ in range(19):
        env.observe(np.array([0.5]), OutcomeLabel.SAFE)
    for _ in range(3):
        env.observe(np.array([0.0]), OutcomeLabel.UNSAFE)
    s = env.fit()
    assert "insufficient_safe" in s["reason"]
```

### Files touched
- `attention_residuals/sre_self_envelope.py` — `LearnedSafetyEnvelope.__init__` + `fit`.
- `tests/test_sre_self_envelope.py` — two new tests.
- `docs/SOFT-LABEL-CREDIT.md` — add section "min_safe_samples vs min_safe_evidence".
- `docs/SELF-LEARNING-ENVELOPE.md` — update config table.

### Implementation hint
```python
def __init__(self, ..., min_safe_samples: int = 20,
             min_safe_evidence: Optional[float] = None, ...):
    if min_safe_samples < 1: raise ValueError(...)
    if min_safe_evidence is None:
        # Default: numerically equal to min_safe_samples so hard-label behavior
        # doesn't change.
        min_safe_evidence = float(min_safe_samples)
    if min_safe_evidence < 0: raise ValueError(...)
    self.min_safe_samples = int(min_safe_samples)
    self.min_safe_evidence = float(min_safe_evidence)

def fit(self) -> Dict[str, Any]:
    reasons = []
    if len(self._safe_actions) < self.min_safe_samples:
        reasons.append("insufficient_safe_samples")
    if sum(self._safe_weights) + 1e-12 < self.min_safe_evidence:
        reasons.append("insufficient_safe_evidence")
    if self._unsafe_since_fit + 1e-12 < self.unsafe_quorum:
        reasons.append("no_unsafe_quorum")
    if reasons:
        summary["reason"] = ",".join(reasons)
        ...
```

### Behavior when both params are explicit (closed during review)

If the operator passes **both** `min_safe_samples=10` and `min_safe_evidence=5.0` explicitly:
- **Accept both as-is** — do NOT auto-reconcile.
- The effective gate is whichever is stricter at fit time (both clauses are AND-ed).
- If the operator wants them aligned, they should set them equal; if they want to be strict
  on counts and loose on evidence mass, they set `min_safe_samples` high and `min_safe_evidence` low.
- Emit a one-line warning via `warnings.warn` **only** if
  `min_safe_evidence > min_safe_samples` (i.e. the stricter path is evidence, which is
  the unusual case for soft-label operators).

### Docs update checklist
- [ ] `docs/SELF-LEARNING-ENVELOPE.md` — table of config params
- [ ] `docs/SOFT-LABEL-CREDIT.md` — new "gate semantics" section
- [ ] `docs/claude-review/01-detailed-architecture.md` — update API contract 4.5

---

## AI-3 🟢 P2 · Thread-safe `ContractionAwareEnvelope`

### Problem
`ContractionAwareEnvelope.apply` mutates `self.inner.current_max_delta` before calling the
inner and restores it in `finally`. Two concurrent `apply` calls on the same wrapper can
overlap and leak a shrunken state into the "restored" value. Pure-Python single-thread
execution is fine (GIL serializes), but multi-process, async, or C-extension-heavy workloads
can deadlock or corrupt state.

### Target behavior
- Add `threading.Lock` as an instance attribute.
- `apply` acquires the lock for the entire snapshot → call → restore sequence.
- Constructor accepts `thread_safe: bool = True`. When `False`, skip lock (preserves
  microbenchmark parity for single-threaded users).

### Acceptance criteria
1. Concurrent `apply` calls from two threads produce no corruption (stress test with
   `concurrent.futures.ThreadPoolExecutor`).
2. After any call completes, `self.inner.current_max_delta` equals the snapshot before the
   wrapper applied its scaling.
3. `thread_safe=False` path takes no lock (verify via `assert env._lock is None`).
4. Latency overhead with lock is < 2 × unlocked (measured via `timeit` in test).

### Test specification
```python
def test_contraction_wrapper_thread_safe_by_default():
    env = _fresh_env(initial_max_delta=np.array([2.0]))
    gains = iter([1.0, 5.0, 1.0, 3.0] * 100)
    wrapper = ContractionAwareEnvelope(
        env, gain_provider=lambda: next(gains, 1.0),
        target_gain=1.0, min_scale=0.1,
    )

    def worker():
        for _ in range(50):
            wrapper.apply(np.array([np.random.uniform(-5, 5)]))

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(worker) for _ in range(4)]
        for f in futures:
            f.result()
    # Inner should be restored to snapshot regardless of threads
    assert np.allclose(env.current_max_delta, [2.0])

def test_contraction_wrapper_opt_out():
    env = _fresh_env()
    w = ContractionAwareEnvelope(env, gain_provider=lambda: 1.0,
                                  target_gain=1.0, thread_safe=False)
    # No lock attribute (implementation detail we assert on):
    assert getattr(w, "_lock", None) is None
```

### Files touched
- `attention_residuals/sre_self_envelope.py` — `ContractionAwareEnvelope`.
- `tests/test_sre_self_envelope.py` — two new tests.
- `docs/SELF-LEARNING-ENVELOPE.md` — note thread-safety contract.

### Implementation hint
```python
import threading

def __init__(self, inner, gain_provider, *,
             target_gain=1.0, min_scale=0.1, thread_safe=True):
    ...
    self._lock = threading.Lock() if thread_safe else None

def apply(self, action):
    if self._lock is not None:
        with self._lock:
            return self._apply_locked(action)
    return self._apply_locked(action)

def _apply_locked(self, action):
    # existing logic
    ...
```

---

## AI-4 🟢 P2 · Streaming replay: optional `skip_bad_lines`

### Problem
`StreamingAuditCreditReplay.poll()` raises `ValueError` on any malformed JSON and does not
advance `cursor.offset`. Next call re-reads the same bad line and errors again. In
production, sustained upstream corruption (partial writes, log rotation) can stall the
stream indefinitely.

### Target behavior
- Add `skip_bad_lines: bool = False` to `StreamingAuditCreditReplay.__init__`.
- When `True`: bad JSON → record to `self.dead_letters: list[dict]` with `{line, lineno,
  byte_offset, error}` → advance cursor past the bad line → continue.
- When `False` (default): existing raise-and-halt behavior.
- Expose `dead_letters_count` property.
- **Dead-letter buffer has an upper bound** to prevent unbounded memory growth on
  persistently-corrupt streams:
  - Add `max_dead_letters: int = 1000` parameter.
  - When full, oldest entries are dropped (FIFO).
  - Expose `dead_letters_dropped: int` counter for how many were evicted.

### Acceptance criteria
1. `skip_bad_lines=False` preserves all Round 9 behavior exactly (regression test).
2. `skip_bad_lines=True` + malformed line + following good line → returns 1 (the good line
   replayed), dead_letters_count = 1.
3. Each dead letter entry has: `line: str` (utf-8 decoded or repr if can't), `lineno: int`,
   `byte_offset: int`, `error: str`.
4. Good JSON after a bad JSON is replayed successfully.
5. Dead letters list is append-only and survives across poll calls.
6. Dead letters list respects `max_dead_letters` cap (FIFO eviction, counter exposed).
7. Demo `demo_streaming_audit_replay.py` should gain a 5th phase demonstrating recovery.

### Test specification
```python
def test_streaming_skip_bad_lines_recovers():
    path = tmp_path / "audit.jsonl"
    _tca, replay, _tail = _streaming_replay(path)
    tail = StreamingAuditCreditReplay(replay, str(path), skip_bad_lines=True)
    path.write_text(
        "{bad-json}\n" + _audit_jsonl_line(0, 1.0) + "\n",
        encoding="utf-8",
    )
    assert tail.poll() == 1
    assert tail.dead_letters_count == 1
    assert len(tail.dead_letters) == 1
    assert "bad-json" in tail.dead_letters[0]["line"]
    assert tail.dead_letters[0]["lineno"] == 1

def test_streaming_raise_on_bad_lines_is_default():
    """Default behavior unchanged from Round 9."""
    path = tmp_path / "audit.jsonl"
    _tca, replay, tail = _streaming_replay(path)
    path.write_text("{bad-json}\n", encoding="utf-8")
    with pytest.raises(ValueError):
        tail.poll()

def test_streaming_dead_letters_capped():
    path = tmp_path / "audit.jsonl"
    _tca, replay, _tail = _streaming_replay(path)
    tail = StreamingAuditCreditReplay(
        replay, str(path), skip_bad_lines=True, max_dead_letters=3,
    )
    bad = "{bad}\n" * 10
    path.write_text(bad, encoding="utf-8")
    tail.poll()
    assert tail.dead_letters_count == 3          # buffer saturated
    assert tail.dead_letters_dropped == 7        # overflow counter
```

### Files touched
- `attention_residuals/sre_math.py` — `StreamingAuditCreditReplay`.
- `tests/test_sre_math.py` — two new tests.
- `examples/demo_streaming_audit_replay.py` — add phase 5.
- `docs/STREAMING-AUDIT-REPLAY.md` — document the new parameter and dead-letter
  semantics.

### Implementation hint
Preserve the existing exception path. In the except block, when `skip_bad_lines=True`:

```python
except (UnicodeDecodeError, json.JSONDecodeError) as exc:
    if self.skip_bad_lines:
        self._dead_letters.append({
            "line": raw.decode(self.encoding, errors="replace"),
            "lineno": lineno,
            "byte_offset": self.cursor.offset + bytes_consumed_so_far,
            "error": str(exc),
        })
        continue  # skip this line, advance past it
    raise ValueError(f"invalid JSONL record in {path!r} during poll line {lineno}") from exc
```

Careful: when skipping, you still need to advance `next_offset` past the bad line so the
cursor moves forward. Compute the post-line offset explicitly.

---

## AI-5 🟢 P3 · Document dual-evidence in `LearnedSafetyEnvelope.observe()`

### Problem
Soft-label `OutcomeEvidence(safety_score=0.3, confidence=1.0)` enters **both** the SAFE
buffer (with weight 0.3) and the UNSAFE quorum counter (with weight 0.7). This is mathematically
correct but not obvious from the code.

### Target behavior
Add a docstring block to `LearnedSafetyEnvelope.observe()` that explicitly walks through
the dual-accounting for a soft label.

### Acceptance criteria
- Docstring has a "Dual accounting" section.
- Concrete numeric example: `OutcomeEvidence(safety_score=0.3, confidence=1.0)` → explains
  which buffer receives what.
- Mentions that UNKNOWN (`confidence=0`) is a no-op.
- Referenced from `docs/SOFT-LABEL-CREDIT.md`.

### Files touched
- `attention_residuals/sre_self_envelope.py` — docstring of `observe()`.
- `docs/SOFT-LABEL-CREDIT.md` — cross-reference.

### Implementation
No code change. Docstring:

```python
def observe(self, action, outcome, *, delta=None, step=None):
    """Record one (action, outcome) pair.

    ...

    Dual accounting of soft evidence
    --------------------------------
    An OutcomeEvidence with partial confidence splits evidence across the
    SAFE buffer and the UNSAFE quorum counter in proportion to
    safety_score.

    Example: ``OutcomeEvidence(safety_score=0.3, confidence=1.0)``

        safe_weight   = 0.3 * 1.0 = 0.3   → appended to _safe_actions
                                             with weight 0.3
        unsafe_weight = 0.7 * 1.0 = 0.7   → added to _unsafe_since_fit

    UNKNOWN (confidence=0) is a no-op: neither buffer receives an entry.
    This matches the "we refuse to take a stand without evidence" rule.
    """
```

---

## AI-6 🟢 P3 · Explicit empty-input check in `_weighted_quantile`

### Problem
`_weighted_quantile(values=np.empty((0, D)), weights=np.empty(0), q=0.5)` fails with an
indirect `np.interp` error after passing earlier shape/weight checks. First failure mode is
`np.argsort` returning an empty array; the error surfaces only when `cdf` is empty.

### Target behavior
Add an explicit first-line check that produces a clear error message.

### Acceptance criteria
- `_weighted_quantile(np.empty((0, 3)), np.empty(0), 0.5)` raises `ValueError` with message
  "values must have at least one row".
- All other existing behavior preserved.

### Test specification
```python
def test_weighted_quantile_rejects_empty():
    from attention_residuals.sre_self_envelope import _weighted_quantile
    with pytest.raises(ValueError, match="at least one row"):
        _weighted_quantile(np.empty((0, 2)), np.empty(0), 0.5)
```

### Files touched
- `attention_residuals/sre_self_envelope.py` — `_weighted_quantile`.
- `tests/test_sre_self_envelope.py` — one new test.

### Implementation
```python
def _weighted_quantile(values: np.ndarray, weights: np.ndarray, q: float) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    if values.ndim != 2:
        raise ValueError("values must have shape (n, d)")
    if values.shape[0] == 0:
        raise ValueError("values must have at least one row")
    ...
```

---

## AI-7 🟢 P3 · Document DDP caveat for `share_key=False`

### Problem
`AttentionResidual` with `share_key=False` uses `nn.ModuleList` that grows lazily on each
forward pass. Distributed training frameworks (DDP, FSDP) require parameter consistency
across ranks at wrap time. Lazy growth **after** wrap → rank desync → silent training bugs.

### Target behavior
Add a "Distributed training considerations" section to `docs/ARCHITECTURE.md`. Also add a
one-line note to the docstring of `AttentionResidual.__init__`.

### Acceptance criteria
- `docs/ARCHITECTURE.md` has a new section (before "Current high-priority refinements")
  explaining:
  - The issue (lazy growth + wrap-time parameter snapshot).
  - Workaround 1: pre-populate keys by calling `forward` once before wrapping.
  - Workaround 2: use `share_key=True` (recommended for distributed training).
  - Workaround 3: set `broadcast_buffers=False` in DDP and handle sync manually.
- `AttentionResidual.__init__` docstring has one-line pointer to this section.

### Files touched
- `docs/ARCHITECTURE.md` — new section.
- `attention_residuals/attn_residual.py` — docstring only.

### Suggested text
```markdown
## 5. Distributed training considerations

`AttentionResidual(share_key=False)` allocates W_K parameters lazily via
`nn.ModuleList.append()` on the first forward pass that sees a new history slot.
This is memory-efficient and works correctly on a single device, but is unsafe
with parameter-sharing frameworks like DDP / FSDP:

- **DDP** takes a parameter snapshot at `DistributedDataParallel(module)` wrap
  time. Layers created after wrap will not be broadcast across ranks and are
  invisible to gradient-sync hooks.
- **FSDP** requires parameter shapes to be known at `FullyShardedDataParallel`
  wrap time; dynamic additions break sharding.

### Workarounds
1. **Use `share_key=True`** (default; recommended for distributed training).
   Single shared W_K — no lazy growth.
2. **Pre-populate keys** before wrapping:
   ```python
   model = AttentionResidual(cfg=AttnResConfig(share_key=False))
   with torch.no_grad():
       for _ in range(MAX_LAYERS):
           model._ensure_key_layers(_ + 1)
   wrapped = DDP(model)
   ```
3. **Periodic manual sync** if you must add keys dynamically in DDP — requires
   `torch.distributed.broadcast` on new parameters after each growth event.
```

---

## Execution checklist

When starting each item:

- [ ] Read [`00-review-report.md`](./00-review-report.md) §3 for the item's context
- [ ] Read the relevant section of [`01-detailed-architecture.md`](./01-detailed-architecture.md)
- [ ] Create a branch or continue on `attention-residuals-session`
- [ ] Implement the item
- [ ] Run the specified new tests
- [ ] Run full suite: `pytest -q` → expect 154 + N passed
- [ ] Update the relevant docs
- [ ] Commit with message:
  `fix(AI-N): <one-line summary>` — include test count change and performance numbers if relevant
- [ ] Update this file's priority summary table row to strike-through

When all P1 complete:
- [ ] Re-run all demos
- [ ] Update `docs/CODEX-HANDOFF.md` with post-P1 status
- [ ] Notify the review owner

---

## Per-item execution template

Each AI-item follows this protocol. Copy into the commit description as a checklist:

```
fix(AI-N): <one-line summary>

Scope:
  - files: <list from action-item>
  - invariants affected: <I-xx or "none — convention only">

Implementation:
  - <3-5 bullets>

Tests added (N total, changing 154 → 154+N):
  - tests/<file>::<test_name>  # primary
  - tests/<file>::<test_name>  # boundary
  - tests/<file>::<test_name>  # regression guarding existing behavior

Performance impact (if relevant):
  - before: <number> ms / MB / etc.
  - after : <number> ms / MB / etc.

Docs updated:
  - <paths>

Validation run locally:
  - pytest -q                        # 154+N passing
  - pytest --collect-only -q         # 154+N collected
  - getDiagnostics on touched files  # 0 warnings
  - re-ran demos: <list>

Closes: claude-review/02-action-items.md#ai-N
```

---

## Out-of-scope reminders

These were **not** asked for. Do not attempt unless separately prioritized:

- Adding HTTP service or SQLite persistence (explicitly out of scope).
- Policy-gradient / RL-based envelope learning.
- Cross-service envelope federation.
- Integration with any specific metric backend beyond Prometheus / OTel.
- Rewriting `knowledge-base.html` from HTML into MDX / a static-site generator.

If any of these becomes necessary, open a new review cycle rather than expanding this list.
