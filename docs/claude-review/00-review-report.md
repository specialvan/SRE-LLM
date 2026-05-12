# Review Report · Rounds 7–9

> Reviewer: Claude · Review date: 2026-05-12
> Subject: commits `ba8fad8` → `3dbfd50` on `attention-residuals-session`
> Lines changed: ~2900 additions, 258 deletions

---

## TL;DR

**Verdict: Approve with minor notes.**

- 154 / 154 tests pass (from 127 at Round 6 handoff).
- 4 new demos all run clean.
- Zero diagnostics warnings across the package.
- One real bug fix landed (`AdaptiveCombiner` static-bias override).
- Merge blockers: **none**.
- Recommended refinements: 7, see [`02-action-items.md`](./02-action-items.md).

---

## 1. Scope of review

Five commits on `attention-residuals-session`, roughly matching three substantive rounds of work:

| Commit | Round | Scope |
| --- | --- | --- |
| `ba8fad8` | R6.5 | Architecture doc + `AdaptiveCombiner` bias fix + self-envelope GIF |
| `51ae181` | R6.5 | `AttentionResidual.share_key=False` implementation |
| `7bb2228` | R7/8/9 | Soft labels + credit-aware labeler + audit replay + metric sources |
| `370eeb7` | R9 | Streaming audit replay with byte cursor |
| `3dbfd50` | R9 | `CODEX-HANDOFF.md` rewrite |

Files added: `sre_metrics.py`, 6 docs, 4 demos, 3 test files.
Files modified: `attn_residual.py`, `sre_adaptive.py`, `sre_math.py`, `sre_self_envelope.py`, `__init__.py`, `knowledge-base.html`, `README.md`.

---

## 2. Per-commit assessment

### 2.1 `ba8fad8` — Architecture doc + bias fix
**Score: 9 / 10**

**What landed**
- `docs/ARCHITECTURE.md` — 216-line architecture writeup.
- `docs/CODEX-HANDOFF.md` — 246-line handoff.
- `docs/assets/self_learning_envelope.gif` — 1 MB animation of envelope dynamics.
- `attention_residuals/sre_adaptive.py` — 1-line fix to preserve static `bias`.
- `tests/test_sre_adaptive.py` — new regression `test_adaptive_combiner_preserves_static_bias_under_learning`.

**Verdict**
- The bias fix is a **real bug I introduced in Round 4**. Codex caught it via inspection, not via a failing test. Good eye.
- Before the fix:
  ```python
  spec.bias = float(lg)      # overwrites operator's static SignalSpec.bias
  ```
  After:
  ```python
  spec.bias = float(base_bias + lg)   # stacks learner logit on top of static bias
  self._static_biases = [float(s.bias) for s in signals]  # captured at init
  ```
  This is the correct semantic — operator priors compose with the learner rather than being erased.
- The new regression test pins the exact expected behavior (`static_bias + learner.logits()`). Solid.

**Nits**
- The comment "stack the learner bias on top" uses "stack" in a way that could be read as matrix stacking. It's simple addition; a one-word change to "add" or "sum" would be clearer.

### 2.2 `51ae181` — Independent key bank
**Score: 9.5 / 10**

**What landed**
- Rewrote `AttentionResidual` so `share_key=False` actually works.
- Lazy `nn.ModuleList` that grows per history slot.
- Added `test_attn_residual_independent_key_bank_contributes` regression.
- Updated `FORMULA_MAP.md`, `ARCHITECTURE.md`, `knowledge-base.html`, `CODEX-HANDOFF.md`.

**Verdict**
- This fixes **another bug I introduced in Round 1**. The `share_key=False` branch existed in config but was never implemented; the module would have silently dropped keys or crashed depending on code path.
- Codex's lazy-growth approach via `nn.ModuleList` is elegant: no upper bound on history depth, no wasted parameters at init, and the new keys participate in gradient flow automatically through PyTorch's module registration.
- The test is the right shape — it perturbs a specific key bank's weight, runs forward, and asserts the output changed. Proves participation, not just existence.

**Notes for production**
- Distributed training (DDP / FSDP) **will have issues** with lazy module growth if different ranks see different histories on the first forward pass. For CPU-only / single-device usage (current scope), this is fine. A one-paragraph note in `ARCHITECTURE.md` under "known limitations" would close the loop.

### 2.3 `7bb2228` — Round 7/8/9 (the big one)
**Score: 8.5 / 10** · +1997 lines / -255 lines across 16 files

This is the most valuable commit of the batch. It delivers three orthogonal capabilities, each of which corresponds to a future direction I outlined in Round 6's wrap-up.

#### 2.3.1 Round 7 · `OutcomeEvidence` + `CreditAwareLabeler`
Addresses Round-6 next-step item **#7.1 (soft labels)** and **#7.5 (credit feedback)**.

- `OutcomeEvidence(safety_score ∈ [0,1], confidence ∈ [0,1], reason)` replaces the hard binary `OutcomeLabel`. Factory methods `from_label` and `from_weights` keep backward compatibility.
- `_weighted_quantile` uses CDF-midpoint interpolation — mathematically sound, and it gracefully degrades to plain NumPy quantile when all weights are 1 (i.e., hard labels).
- `CreditAwareLabeler` wraps any `Labeler` and downgrades UNSAFE evidence proportionally to how much of the blame falls on controllable signals:
  ```
  controllable_ratio = controllable_credit / total_credit
  adjusted.unsafe_weight = original.unsafe_weight * controllable_ratio
  ```
- End-to-end integration test (added separately by me) confirms: **envelope does not tighten when SLO breach is caused by external signals** (the core value proposition).

#### 2.3.2 Round 8 · Audit replay + metric loss specs
- `AuditCreditReplay.replay_record` validates shape, non-negativity, and context type. Raises `ValueError` on bad input rather than silently skipping.
- `MetricLossSpec` with four modes (`above` / `below` / `distance` / `raw`) covers common SLO-distance formulas.
- `AuditCreditReplay.replay_jsonl` and `replay_jsonl_file` let an offline blame job be run against historical audit logs.

#### 2.3.3 Round 8 · `sre_metrics.py` adapter
- **stdlib-only** — no `requests` or `opentelemetry-sdk` dependency.
- `transport` is injectable — tests and demos never touch real HTTP.
- Prometheus `instant_query` handles both `scalar` and `vector` result types.
- OTel JSON reader supports `gauge` and `sum` metrics with `asDouble / doubleValue / asInt / intValue / value` fallback — covers variations across OTel protocol versions.

**Verdict**
- Design pattern is consistently clean: **external dependency → callable injection point**.
- Error messages are specific and actionable.
- 16 files changed, but each file has a clear single responsibility.

### 2.4 `370eeb7` — Streaming audit replay
**Score: 9 / 10**

**What landed**
- `AuditReplayCursor` dataclass (path, offset, pending bytes, reset count).
- `StreamingAuditCreditReplay.poll()` method that tails a JSONL file.
- 5 test scenarios: missing file, file truncation, bad JSON, restored cursor, partial line buffering.
- `demo_streaming_audit_replay.py` with 4-phase illustration.

**Verdict**
- The byte-cursor design is correct — it tracks `offset` for "where I've read up to" and `pending` for "the trailing partial line". Only complete newline-terminated records advance cursor state.
- Truncation reset is handled (cursor resets if file size shrinks), with a counter surfaced in diagnostics.
- Bad JSON causes `ValueError` with line number context — blocks the stream rather than silently skipping, which is the right default for audit integrity.

**Concern** (flagged as P2 action)
- If corruption is sustained (e.g., a partial write that never completes), the stream stalls indefinitely. A future `skip_bad_lines=True` option with alerting would be useful for degraded-mode operation. Not urgent.

### 2.5 `3dbfd50` — Handoff rewrite
**Score: 7 / 10**

**What landed**
- `docs/CODEX-HANDOFF.md` rewrote from 186 lines of old content to 148 lines of new content.

**Verdict**
- The rewrite explicitly clarifies that this repo is **a library of SRE control primitives + an Attention Residuals implementation**, not a runtime service. That framing is important and was missing in the previous version.
- Current state, risk boundaries, module map, and pickup checklist are all present.
- Minor: the file mixes Chinese and English; consider settling on one language per doc for consistency. (Not blocking.)

---

## 3. Design concerns that motivated the action list

These seven concerns drive the items in [`02-action-items.md`](./02-action-items.md). Priority labels match the action file.

### 3.1 🟡 P1 — `TemporalCreditAssigner._history` is unbounded
```python
self._history: List[dict] = []   # never truncated
```
Every call to `record()` appends. `attribute()` is O(|history|) per call. Over a long-running process this is a memory leak and a latency leak. **`CreditAwareLabeler.__call__` triggers `attribute` on every tick**, so this is on the hot path.

**Impact**: At typical cadence (1 record/sec), 24 hours = 86 k records. At 1 week = 600 k records. At that scale `attribute()` latency becomes observable (~10 ms on my laptop) and pressure on the GC is real.

**Recommendation**: Add `max_history_ticks=10_000` param with a fixed-size deque. Old records drop off the left as new ones enter. Combined with `window` filter in `attribute`, bounded memory and latency.

### 3.2 🟡 P1 — `min_safe_samples` semantic is ambiguous under soft labels
In `LearnedSafetyEnvelope.fit`:
```python
if sum(self._safe_weights) + 1e-12 < self.min_safe_samples:
    summary["reason"] = "insufficient_safe_samples"
```
Docstring says:
> Minimum SAFE observations in the buffer required to compute a trustworthy quantile.

With hard labels (`safe_weight == 1.0`), `sum == count`. With soft labels, the number of records required to reach the threshold is inflated by `1 / mean_safe_weight`. Operators tuning `min_safe_samples=20` will get silent surprises under a soft-label labeler.

**Recommendation**: Either rename to `min_safe_evidence` or add a separate `min_safe_count` parameter and check both conditions.

### 3.3 🟢 P2 — `ContractionAwareEnvelope.apply` is not thread-safe
The pattern:
```python
saved_md = self.inner.current_max_delta.copy()
self.inner.current_max_delta = saved_md * scale
try:
    ...
finally:
    self.inner.current_max_delta = saved_md
```
is correct for serial use, but two concurrent `apply` calls can overwrite `saved_md` and leak a shrunken state. The GIL protects most pure-Python execution, **but NumPy operations often release the GIL** (most ufuncs do) — so in multi-threaded code paths that include numpy work within the try/finally window, a race is possible even in single-process CPython. Multi-process / async workflows need an explicit lock unconditionally.

**Recommendation**: Add `threading.Lock` to the wrapper (optional, default enabled). Document the thread-safety contract in the docstring.

### 3.4 🟢 P2 — Streaming replay has no degraded-mode skip option
Current behavior: bad JSON → `ValueError` → cursor doesn't advance → next `poll()` re-reads the same bad line and errors again. A stuck replay blocks follow-up processing.

**Recommendation**: Add `skip_bad_lines: bool = False` to `StreamingAuditCreditReplay`. When enabled, record the bad line to a dead-letter list and advance cursor. Keep raise-by-default for audit-integrity safety.

### 3.5 🟢 P3 — Soft-label dual accounting is not documented
```python
# observed OutcomeEvidence(safety_score=0.3, confidence=1.0)
if safe_weight > 0.0:                                  # 0.3 > 0 → entered
    self._safe_actions.append(action.copy())
    self._safe_weights.append(safe_weight)              # weight 0.3
if unsafe_weight > 0.0:                                # 0.7 > 0 → also counted
    self._unsafe_since_fit += unsafe_weight             # +0.7
```
A single observation with `safety_score=0.3` both adds a weak anchor to the SAFE buffer AND contributes 0.7 to the quorum counter. This is mathematically defensible (they represent genuinely mixed evidence), but the mechanism is not obvious from reading `observe()`.

**Recommendation**: Add a 3-line comment block explaining the double-bookkeeping with an example.

### 3.6 🟢 P3 — `_weighted_quantile` empty-input failure is indirect
```python
def _weighted_quantile(values, weights, q):
    ...
    if values.ndim != 2: raise ValueError(...)
    if weights.shape != (values.shape[0],): raise ValueError(...)
    if np.any(weights < 0): raise ValueError(...)
    total = weights.sum()
    if total <= 0: raise ValueError(...)
    # If values.shape[0] == 0, np.argsort returns empty, cdf is empty, np.interp errors later.
```
Error message is less clear than it needs to be for empty input.

**Recommendation**: Add explicit `if values.shape[0] == 0: raise ValueError("values must have at least one row")` as the first check.

### 3.7 🟢 P3 — Lazy `nn.ModuleList` distributed-training caveat undocumented
`AttentionResidual.share_key=False` creates `W_K` layers on demand. Distributed training libraries (DDP, FSDP) require parameter consistency across ranks at the time wrapping is applied. Lazy creation after wrap → rank desync.

**Recommendation**: Add a paragraph to `ARCHITECTURE.md` "known limitations" section explaining that `share_key=False` requires either (a) pre-populating keys before wrapping in DDP, or (b) using `broadcast_buffers=False` and periodic parameter sync.

---

## 4. Positive patterns worth highlighting

These are practices codex applied consistently and should keep applying.

1. **External dependency → callable injection.** Every transport (HTTP, files, gains, labelers, context providers) is an injectable callable. Tests never mock at the HTTP level — they inject a `transport` function. This pattern has propagated from `ShadowRunner` in Round 4 through to `PrometheusHTTPClient.transport` in Round 8.

2. **"One feature → one doc → one demo → one test file"** rhythm held through Rounds 7/8/9:
   | Feature | Doc | Demo | Test |
   | --- | --- | --- | --- |
   | Soft labels + credit | `SOFT-LABEL-CREDIT.md` | `demo_credit_aware_envelope.py` | `test_sre_self_envelope.py` (+7) |
   | Audit replay | `AUDIT-CREDIT-REPLAY.md` | `demo_audit_credit_replay.py` | `test_sre_math.py` (+7) |
   | Metric sources | `METRIC-SOURCES.md` | `demo_metric_source_replay.py` | `test_sre_metrics.py` (+7) |
   | Streaming | `STREAMING-AUDIT-REPLAY.md` | `demo_streaming_audit_replay.py` | `test_sre_math.py` (+4) |

3. **Fail-loud on audit-integrity questions.** `AuditCreditReplay`, streaming replay, `MetricLossSpec` all raise `ValueError` on malformed inputs rather than silently degrading. This aligns with the "audit priority over availability" principle from Round 6.

4. **Honest scope in handoff.** `CODEX-HANDOFF.md` explicitly disclaims HTTP/SQLite runtime. That honesty is worth more than a claim of completeness.

5. **Stdlib-only where possible.** `sre_metrics.py` avoids adding `requests` or `opentelemetry-sdk` as runtime deps. Matters for embedding the package in restricted production environments.

---

## 5. Quality metrics

| Metric | Round 6 | Round 9 | Delta |
| --- | --- | --- | --- |
| Modules (`attention_residuals/*.py`) | 16 | 18 | +2 (`sre_math` extended, `sre_metrics` new) |
| Tests | 127 | 154 | +27 (21%) |
| Demos | 7 | 11 | +4 |
| Docs (markdown) | 5 | 13 | +8 |
| HTML knowledge base sections | 23 | 28 | +5 |
| Public symbols in `__init__.py` | 53 | 68 | +15 |
| Diagnostics | 0 | 0 | — |

**Reading**: growth in tests (+21%) slightly outpaced code growth, which is the healthy direction. Docs grew more than 2× — consistent with the "per-feature doc" discipline.

---

## 6. What's out of scope for this review

- **HTTP service**: never built; codex explicitly disclaims it in handoff. Correct scope decision.
- **SQLite persistence**: same as above.
- **Production metric exporters**: not in scope; metric adapters stop at "JSON in → context out", which is the correct seam.
- **Policy gradient / RL-based envelope**: in Round 6 backlog as #7.6. Not attempted yet.
- **Cross-service envelope federation**: in Round 6 backlog as #7.7. Not attempted yet.

---

## 7. Merge decision

**Approve. No blockers. Proceed to the P1/P2/P3 action items.**

See [`02-action-items.md`](./02-action-items.md).
