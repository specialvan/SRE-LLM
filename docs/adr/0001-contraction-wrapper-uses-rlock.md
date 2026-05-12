# ADR-0001 · `ContractionAwareEnvelope` uses `RLock` rather than `Lock`

- **Status**: Accepted
- **Date**: 2026-05-12
- **Decider**: Codex (implementation) · Claude (review)
- **Affected invariants**: I-08 (`ContractionAwareEnvelope` does not mutate inner state)
- **Affected public API**: `ContractionAwareEnvelope(..., thread_safe: bool = True)`

---

## Context

`ContractionAwareEnvelope.apply` temporarily mutates `inner.current_max_delta`
before delegating to the inner envelope's `apply`, and restores it in a
`finally` block. Two concurrent calls on the same wrapper can overlap that
window and leak a shrunken state into the "restored" value — a violation of
invariant I-08.

The initial fix (claude-review `02-action-items.md` AI-3) specified
`threading.Lock` with an explicit rationale that no nested-call path exists
today. During R2 refinement of the action items, the handoff-summary was
updated to explicitly prefer `Lock` over `RLock` for strictness.

When codex implemented AI-3, they chose `RLock` instead. The concurrency test
(`test_contraction_wrapper_serializes_apply_by_default`) passes for both
implementations, so this is a design choice, not a bug.

## Options considered

### Option A — `threading.Lock`
Non-reentrant. Any attempt to acquire the lock recursively in the same thread
deadlocks immediately — which is loud, fails fast, and makes accidental
re-entry impossible.
- Cost: if a future labeler calls `wrapper.observe()` synchronously from
  within `wrapper.apply()` (possible if a labeler triggers blame attribution
  that in turn examines current bounds), that thread would deadlock.
- Benefit: catches unintended nesting immediately at development time.

### Option B — `threading.RLock`
Reentrant. The same thread can acquire the lock multiple times; releases are
counted. Other threads still block correctly.
- Cost: accidental re-entry passes silently at dev time; a bug that relies on
  nested apply+observe could be latent until a thread race surfaces it.
- Benefit: future labelers / observers that legitimately call back into the
  envelope do not deadlock.

### Option C — do nothing (serial only, no lock)
Rely on callers to serialize. Document the requirement and ship without a lock.
- Cost: callers can (and will) forget. Concurrent calls silently corrupt state.
  No runtime signal.
- Benefit: simpler code; no lock overhead on single-threaded hot paths.

## Decision

**Option B (`RLock`).**

Reasoning:

1. The system has a credible near-term path to nested calls via
   `CreditAwareLabeler.__call__`, which invokes `TemporalCreditAssigner.attribute()`.
   A future version of `attribute()` that consults the envelope's current
   bounds (reasonable — credit weighting could use envelope tightness) would
   re-enter the apply path from within an observe path. With `Lock`, that
   future change would silently deadlock under production load.

2. The runtime cost difference between `Lock` and `RLock` is negligible
   (CPython internal benchmarks put both in the same order of magnitude; the
   dominant cost on this hot path is the numpy copy inside `apply`, not the
   mutex).

3. The `thread_safe=False` escape hatch is still there for single-threaded
   microbenchmark users, so we don't pay the lock cost when we don't want to.

The conservative choice here is the one that **doesn't deadlock** under plausible
future evolution. "Strictness catches bugs" is a good heuristic for invariants;
for locks in a system that will grow callbacks, it's the wrong heuristic.

## Consequences

### Positive
- No deadlock risk under plausible future re-entry paths.
- `thread_safe=False` users opt out cleanly when they can prove external
  serialization.
- `max_active == 1` concurrency test still passes, proving mutual exclusion is
  in effect across threads.

### Negative
- If a future bug accidentally re-enters `apply` from the same thread, the
  behavior will be silent rather than loud. We need a different signal for
  catching that (see Follow-ups).

### Neutral
- Documentation burden: a one-line code comment pointing at this ADR is
  enough. No operator-facing API surface changed.

## Follow-ups

- [ ] Add a one-line code comment in `sre_self_envelope.py` above the
  `self._lock = threading.RLock()` line: `# See ADR-0001 for Lock vs RLock.`
- [x] Test `test_contraction_wrapper_serializes_apply_by_default` already
  locks in mutual exclusion (proves I-08 under concurrency).
- [ ] If we ever see a production incident traced to silent same-thread
  re-entry, consider adding an `RLock`-wrapping debug helper that asserts
  recursion depth ≤ 1 in dev/staging builds.

## References

- Related code:
  - `attention_residuals/sre_self_envelope.py` — `ContractionAwareEnvelope.__init__` / `.apply`
  - `tests/test_sre_self_envelope.py::test_contraction_wrapper_serializes_apply_by_default`
- Related review: `docs/claude-review/04-midflight-review.md` §3
- Related spec: `docs/claude-review/02-action-items.md` AI-3
