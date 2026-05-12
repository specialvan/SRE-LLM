# Mid-flight Review · AI-1 → AI-7 Delta Assessment

> Reviewer: Claude · Review date: 2026-05-12 (same day as initial handback)
> Subject: Codex's in-progress work on `attention-residuals-session` (uncommitted)
> Files changed: 12 modified, 4 untracked (separate skill-research feature ignored)
> Delta: +524 / -90 lines

---

## TL;DR

**Codex has already executed 6 of 7 AI items** (AI-1, AI-2, AI-3, AI-5, AI-6, AI-7 complete;
AI-4 **partially complete** — missing `max_dead_letters` added in R2 refinement).

- 162 / 162 attention-residuals tests pass (was 154; +8 new tests).
- `tests/skill/` failures are unrelated (separate parallel feature, not in spec scope).
- Zero diagnostics on all changed files.
- Implementation quality: high; invariants preserved.

One patch needed before commit: **AI-4 must gain `max_dead_letters` + FIFO cap**
(spec was refined after codex started; see §5 below).

---

## 1. Per-item status

| AI | Priority | Status | Quality | Notes |
| --- | --- | --- | --- | --- |
| AI-1 | 🟡 P1 | ✅ Complete | 9/10 | `max_history_ticks=10_000` default respected; `deque(maxlen=N)` chosen; `evicted_count` property exposed; 2 new tests + validation |
| AI-2 | 🟡 P1 | ✅ Complete | 9.5/10 | Added `min_safe_evidence` with correct default; reasons now joined with `+`; 3 new tests covering both gates |
| AI-3 | 🟢 P2 | ✅ Complete | 8.5/10 | Uses `RLock`, not `Lock` (design deviation — see §3); 1 new concurrency test with SlowEnvelope fake |
| AI-4 | 🟢 P2 | ⚠️ Partial | 7/10 | `skip_bad_lines` + `dead_letters` + `dead_letters_count` done; **missing** `max_dead_letters` and `dead_letters_dropped` |
| AI-5 | 🟢 P3 | ✅ Complete | 9/10 | "Dual accounting" block added to `observe()` docstring with the exact example from the spec |
| AI-6 | 🟢 P3 | ✅ Complete | 10/10 | One-line fix + 1 test with `pytest.raises(ValueError, match="at least one row")` |
| AI-7 | 🟢 P3 | ✅ Complete | 9/10 | "§5.1 Distributed-training caveat" section added to `ARCHITECTURE.md`; docstring on `AttentionResidual` not yet updated (minor) |

**Overall**: 6 ✅ / 1 ⚠️. Codex is ahead of the schedule I budgeted.

---

## 2. What codex did well

1. **Honored the `Lock` vs `RLock` design question but went the other way**
   (§3 below). The reasoning is visible in the code (observe/fit/current_bounds all
   wrapped in the lock), suggesting deliberate choice not oversight. Still worth
   discussing.

2. **`test_contraction_wrapper_serializes_apply_by_default`** is an excellent
   concurrency test. Uses a `SlowEnvelope` subclass that records the max
   concurrent call count, verifying `max_active == 1`. That's a far better
   design than the naive "run N threads and hope for the best" I had sketched.

3. **AI-2 reasoning joined with `+` instead of `,`** (my spec said `,`). Minor
   improvement: makes multi-reason strings parse cleaner. The `reasons` list
   is also exposed alongside the joined string — even better for programmatic
   consumers.

4. **`test_fit_can_gate_only_on_safe_records_when_evidence_floor_is_zero`** is a
   non-obvious boundary test I did not spec. Shows codex thought about the
   `min_safe_evidence=0.0` corner case.

5. **Docs stayed synchronized** with code changes. Every code-affecting AI has
   doc updates in the same edit set (`SELF-LEARNING-ENVELOPE.md`,
   `SOFT-LABEL-CREDIT.md`, `STREAMING-AUDIT-REPLAY.md`). That's the
   "four-part rhythm" (module + test + demo + doc) working.

6. **New `[tool.pytest.ini_options] markers = [...]`** in `pyproject.toml` for
   a future `perf` marker. Forward-looking: suggests codex is thinking about
   how to tag the AI-1 performance bar test without running it in CI by default.

---

## 3. Design deviation: `RLock` instead of `Lock`

### What the spec said
> "Default to `Lock` for strictness, but document the escape hatch. RLock allows
> nested calls." (AI-3, initial version)

In R2 refinement I resolved the handoff-summary question to **`Lock`, not
`RLock`** (rationale: no nested-call path exists today).

### What codex did
Used `threading.RLock()`.

### Is this OK?
**Yes, with a caveat**:

- `RLock` is a strict superset of `Lock` for correctness — no functional bug.
- The observable behavior the test asserts (`max_active == 1`) holds for both.
- If a future AI adds a nested path (e.g. a `CreditAwareLabeler.__call__`
  synchronously invoking `wrapper.apply` via `env.observe`), `RLock` will work
  silently where `Lock` would deadlock.

### Recommendation
**Accept.** This is the conservative choice; the design question was genuinely
close. Document the rationale in the code comment to prevent future reviewers
from "fixing" it back to `Lock`.

**Action for codex**: add one comment above `self._lock = threading.RLock() if thread_safe else None`:

```python
# RLock chosen over Lock because a future labeler that re-enters apply() via
# observe() path would deadlock under Lock. See claude-review/04-midflight-review.md §3.
```

---

## 4. Implementation quality deep-dive

### 4.1 AI-1 (`TemporalCreditAssigner` bounded history)

**Correct choices:**
- `deque(maxlen=max_history_ticks)` instead of `list + pop(0)` — O(1) eviction.
- `max_history_ticks: Optional[int] = 10_000` default preserves backward compat
  via explicit `max_history_ticks=None` for callers that want unbounded.
- `_evicted_count` is incremented *before* append when at capacity — correct
  semantic (we're about to drop one).
- Tests cover: bounded, unbounded, validation (0 and -1).

**Minor nit:** the eviction counter increments on append-when-full, but
`deque.append` at `maxlen` is O(1) and silently drops the oldest. The counter
math is correct but the logic could be simpler:

```python
# Current (works, slightly verbose):
if self.max_history_ticks is not None and len(self._history) >= self.max_history_ticks:
    self._evicted_count += 1
self._history.append({...})

# Alternative (one line shorter, uses deque's internal behavior):
if len(self._history) == self.max_history_ticks:
    self._evicted_count += 1
self._history.append({...})
```

**Accept either way.**

### 4.2 AI-2 (`min_safe_evidence` disambiguation)

**Correct choices:**
- Default `min_safe_evidence = float(min_safe_samples)` preserves hard-label behavior.
- Both gates checked; multiple reasons joined with `+` and exposed as `reasons` list.
- `summary["min_safe_samples"]` and `summary["min_safe_evidence"]` added for
  programmatic callers — not in spec but useful.

**Open question (non-blocking):** `reason` field now has the format
`"insufficient_safe_samples+insufficient_safe_evidence+no_unsafe_quorum"`.
Any external log parser that grepped for exact match `reason == "no_unsafe_quorum"`
will break. If there's a production consumer of this field, consider a
**migration note** in docstring: "In R10, single reasons still match; multi-reason
outputs join with `+`."

**Verdict:** accept as-is; the `reasons` list provides structured access.

### 4.3 AI-3 (thread safety) — see §3 above.

### 4.4 AI-4 (streaming replay dead-letter) — see §5 below.

### 4.5 AI-5 (dual-evidence docstring)

Docstring block added verbatim per spec. Clear, concrete example. No nits.

### 4.6 AI-6 (empty-input check in `_weighted_quantile`)

Single-line fix + single test. Uses `pytest.raises(ValueError, match="at least one row")`
which is exactly the regex I spec'd.

**One observation:** the error message changed slightly:

```python
# Spec:
raise ValueError("values must have at least one row")

# Codex implemented:
raise ValueError("values must contain at least one row")
```

"contain" vs "have". The test `match="at least one row"` matches both. No action needed.

### 4.7 AI-7 (DDP caveat)

Added as a new `§5.1` subsection in `ARCHITECTURE.md`, 18 lines. Content is
correct. Missing: the one-line pointer in `AttentionResidual.__init__` docstring
as spec'd. Minor.

**Action for codex**: add one line to `AttentionResidual.__init__` docstring
linking to `ARCHITECTURE.md §5.1`.

---

## 5. The one thing that needs a patch: AI-4 `max_dead_letters`

### Context
In my R2 refinement to `02-action-items.md` I added `max_dead_letters=1000` as
an AI-4 sub-requirement. This happened **after** codex started implementing
AI-4 in their working tree. They correctly implemented the earlier (simpler)
spec.

### What's missing from the current implementation

```python
# In StreamingAuditCreditReplay.__init__: need to add
max_dead_letters: int = 1000

# Add state:
self.dead_letters_dropped = 0

# When appending a new dead letter:
if len(self.dead_letters) >= self.max_dead_letters:
    self.dead_letters.pop(0)
    self.dead_letters_dropped += 1
self.dead_letters.append({...})

# Expose:
@property
def dead_letters_dropped_count(self) -> int:  # optional: already covered by attr above
    return self.dead_letters_dropped
```

### Test to add

```python
def test_streaming_dead_letters_capped(tmp_path):
    path = tmp_path / "audit.jsonl"
    _tca, replay, _tail = _streaming_replay(path)
    tail = StreamingAuditCreditReplay(
        replay, str(path), skip_bad_lines=True, max_dead_letters=3,
    )
    path.write_text("{bad}\n" * 10, encoding="utf-8")
    tail.poll()
    assert tail.dead_letters_count == 3         # buffer saturated
    assert tail.dead_letters_dropped == 7       # overflow counter
```

### Priority
**Fold into the AI-4 commit** before pushing. It's a 10-line addition plus 1
test. If codex already pushed, a micro follow-up commit is fine.

---

## 6. Test count reconciliation

| Source | Count |
| --- | --- |
| Handback baseline (`3dbfd50`) | 154 |
| Live (after codex's uncommitted work) | 162 |
| Expected after AI-4 `max_dead_letters` patch | 163 |
| State.json SSOT (still shows baseline) | 154 |

**Action**: after codex commits AI-1 through AI-7 with the `max_dead_letters`
patch, run `python docs/V2_Knowledge/_regenerate_state.py --write` to refresh
the snapshot.

---

## 7. Codex-side TODO before pushing

Suggested commit boundaries (for clean git history):

```
commit 1: fix(AI-1): bound TemporalCreditAssigner history
  files: sre_math.py, tests/test_sre_math.py
  tests added: +2

commit 2: fix(AI-2): disambiguate min_safe_samples vs min_safe_evidence
  files: sre_self_envelope.py, tests/test_sre_self_envelope.py,
         docs/SOFT-LABEL-CREDIT.md, docs/SELF-LEARNING-ENVELOPE.md
  tests added: +3

commit 3: fix(AI-3): serialize ContractionAwareEnvelope apply with RLock
  files: sre_self_envelope.py, tests/test_sre_self_envelope.py
  tests added: +1
  # include the comment explaining Lock vs RLock choice

commit 4: fix(AI-4): optional skip_bad_lines + bounded dead-letter buffer
  files: sre_math.py, tests/test_sre_math.py,
         examples/demo_streaming_audit_replay.py, docs/STREAMING-AUDIT-REPLAY.md
  tests added: +2  # including max_dead_letters cap test

commit 5: docs(AI-5/6/7): dual-accounting, empty-input, DDP caveat
  files: sre_self_envelope.py (docstring + weighted_quantile),
         attention_residuals/attn_residual.py (docstring pointer),
         docs/ARCHITECTURE.md, tests/test_sre_self_envelope.py
  tests added: +1
```

After commits:
1. `pytest -q` → expect 163 passing (ignore `tests/skill/` failures — unrelated)
2. `python docs/V2_Knowledge/_regenerate_state.py --write`
3. Manual edit of `state.json`: bump `snapshot_date` to today, update
   `health.tests_total = 163`, clear relevant entries from `open_actions`.
4. Update `docs/CODEX-HANDOFF.md` changelog.

---

## 8. What this means for the round-10 review cycle

**Status**: closing out within the same day. Codex consumed the handback package
within hours of it landing and implemented the majority immediately. That's
faster than any previous round. Three lessons:

1. **`02-action-items.md` format works.** Each item was self-contained enough
   for codex to execute without back-and-forth. Keep this format for future
   handbacks.

2. **Refinements that happen after handback propagate with delay.** My R2
   addition of `max_dead_letters` didn't reach codex's implementation. This is
   expected behavior, not a process bug. Future refinements should be dated and
   explicitly noted in a `CHANGELOG` section at the top of
   `02-action-items.md`.

3. **State.json snapshot semantics need strict discipline.** Right now state
   shows 154 tests; live is 162; after the patch it will be 163. The
   `_regenerate_state.py` script exists precisely to prevent stale snapshots.
   Running it after each `fix(AI-N)` commit would keep reviewers aligned.

---

## 9. Verdict

**Approve the 6 complete AI items. Patch AI-4 before pushing. Then close
Round 10.**

After the AI-4 patch lands, Claude will do a one-paragraph final review and
declare Round 10 closed. No new P1/P2/P3 items are expected from this review
cycle.
