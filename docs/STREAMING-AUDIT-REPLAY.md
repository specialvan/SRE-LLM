# Streaming Audit Replay

Round 10 turns audit replay from an offline batch job into a tail-able
SRE loop. `StreamingAuditCreditReplay` keeps a byte cursor over an
AuditTrail JSONL file and feeds only newly appended, newline-complete
records into `AuditCreditReplay`.

## Why

Round 8 already proved that persisted audit JSONL can reconstruct
temporal credit after an incident. The remaining production gap was
latency: an online control plane should not wait for a full post-mortem
job before updating blame evidence.

The streaming replay layer gives this path:

```text
AuditTrail JSONL append
  -> StreamingAuditCreditReplay.poll()
  -> AuditCreditReplay.replay_record(...)
  -> TemporalCreditAssigner.record(...)
  -> CreditAwareLabeler / post-incident ranking
```

## Cursor Contract

`AuditReplayCursor` stores:

- `path`: the JSONL source file;
- `offset`: the last byte read from disk;
- `pending`: bytes from a trailing partial line;
- `resets`: number of truncation resets observed.

The cursor is a plain dataclass, so operators can serialize these fields
outside the process and pass a restored cursor back into
`StreamingAuditCreditReplay(..., cursor=restored_cursor)`.

`poll()` follows four rules:

1. If the file is missing and `missing_ok=True`, return `0`.
2. If file size is smaller than `offset`, assume truncation or rotation
   and reset `offset` plus `pending`.
3. Read bytes from `offset` to EOF, but replay only newline-complete
   lines.
4. Keep an incomplete trailing line in `pending` until a later newline
   arrives.

This keeps the stream safe for log writers that flush mid-record.

## API

```python
from attention_residuals.sre_math import (
    AuditCreditReplay,
    MetricLossMapper,
    MetricLossSpec,
    StreamingAuditCreditReplay,
    TemporalCreditAssigner,
)

tca = TemporalCreditAssigner(decay=0.95)
replay = AuditCreditReplay(
    tca,
    MetricLossMapper({
        "controller": MetricLossSpec("controller_error", mode="raw"),
        "traffic": MetricLossSpec("traffic_spike", mode="raw"),
    }),
)
tail = StreamingAuditCreditReplay(replay, "audit.jsonl", missing_ok=True)

new_records = tail.poll()
top = tca.attribute(incident_tick=1234, window=60, top_k=10)
```

Optional recovery mode:

```python
tail = StreamingAuditCreditReplay(
    replay,
    "audit.jsonl",
    missing_ok=True,
    skip_bad_lines=True,
)
```

By default, malformed JSON still raises and preserves the previous cursor
offset. With `skip_bad_lines=True`, malformed newline-complete records
are copied into `tail.dead_letters` and the cursor advances past them.
Each dead letter contains:

- `line`: decoded bad line, using replacement characters if necessary;
- `lineno`: line number inside the current poll batch;
- `byte_offset`: absolute byte offset where that line began;
- `error`: decode or JSON parse error text.

`tail.dead_letters_count` exposes the current count.

### Bounded dead-letter buffer

A persistently corrupt log could grow the dead-letter list without bound.
The buffer is capped by ``max_dead_letters`` (default **1000**) with FIFO
eviction:

```python
tail = StreamingAuditCreditReplay(
    replay, "audit.jsonl",
    skip_bad_lines=True,
    max_dead_letters=500,   # retain at most 500 most-recent bad lines
)

# After a persistently bad stream:
tail.dead_letters_count       # ≤ 500 (the cap)
tail.dead_letters_dropped     # how many were evicted over the lifetime
```

`max_dead_letters=0` is a valid "count but never retain" mode: the stream
keeps replaying subsequent good records, every bad line increments
``dead_letters_dropped``, but the dead-letter list stays empty. This is
useful when you only care that corruption is happening (via the counter /
its Prometheus gauge in your wrapper), not about the raw bad payloads.

## Operational Notes

- Cursor offset is byte-based, so it is stable across UTF-8 text reads.
- The replay path still validates signal names, weight shape, positive
  weight sum, non-negative losses, and context mapping shape.
- JSON decode errors fail the poll loudly while preserving the previous
  cursor position unless `skip_bad_lines=True` is enabled. Recovery mode
  is useful for production tailers that prefer a dead-letter path over a
  stalled stream.
- Rotation detection is intentionally conservative. If a platform needs
  inode-aware rotation semantics, wrap this class with an external file
  identity check.

## Demo

```bash
python -m examples.demo_streaming_audit_replay
```

The demo appends one complete line, one partial line, then the newline
that completes it. The partial record is not replayed until the newline
arrives. It also appends a malformed line followed by a good line to
show `skip_bad_lines=True` recovery.

## Tests

Covered in `tests/test_sre_math.py`:

- appended lines are replayed exactly once;
- partial trailing lines are buffered;
- truncation resets the cursor;
- missing-file behavior is explicit;
- invalid JSON does not advance the cursor by default, so operators can
  replace or quarantine the bad line and retry from the same offset;
- `skip_bad_lines=True` records malformed input as a dead letter and
  continues to replay later good lines;
- `max_dead_letters` caps the dead-letter buffer FIFO (default 1000;
  `=0` means count-only, no retention);
- restored cursors resume from their saved byte offset.
