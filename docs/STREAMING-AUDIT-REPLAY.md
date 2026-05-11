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

## Operational Notes

- Cursor offset is byte-based, so it is stable across UTF-8 text reads.
- The replay path still validates signal names, weight shape, positive
  weight sum, non-negative losses, and context mapping shape.
- JSON decode errors fail the poll loudly while preserving the previous
  cursor position. A production wrapper can quarantine the bad line and
  retry from the same offset.
- Rotation detection is intentionally conservative. If a platform needs
  inode-aware rotation semantics, wrap this class with an external file
  identity check.

## Demo

```bash
python -m examples.demo_streaming_audit_replay
```

The demo appends one complete line, one partial line, then the newline
that completes it. The partial record is not replayed until the newline
arrives.

## Tests

Covered in `tests/test_sre_math.py`:

- appended lines are replayed exactly once;
- partial trailing lines are buffered;
- truncation resets the cursor;
- missing-file behavior is explicit;
- invalid JSON does not advance the cursor, so operators can replace or
  quarantine the bad line and retry from the same offset;
- restored cursors resume from their saved byte offset.
