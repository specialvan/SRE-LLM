# Audit JSONL -> Temporal Credit Replay

Round 8 closes the gap between in-process demos and production trace
replay. `AuditTrail.to_jsonl()` already exports every controller
decision with signal weights, action, and context. The new replay layer
turns those lines back into `TemporalCreditAssigner.record(...)` calls.

## API

```python
from attention_residuals.sre_math import (
    AuditCreditReplay,
    MetricLossMapper,
    MetricLossSpec,
    TemporalCreditAssigner,
)

tca = TemporalCreditAssigner(decay=0.92)
replay = AuditCreditReplay(
    tca,
    MetricLossMapper({
        "controller": MetricLossSpec("controller_error", mode="raw"),
        "traffic": MetricLossSpec("traffic_spike", mode="raw"),
    }),
)

replay.replay_jsonl(audit_jsonl_text)
top = tca.attribute(incident_tick=1234, window=60, top_k=10)
```

## Record Shape

The replay adapter expects the same shape emitted by `AuditTrail`:

```json
{
  "step": 29,
  "signals": ["controller", "traffic"],
  "weights": [0.87, 0.13],
  "action": [1.87],
  "context": {
    "controller_error": 4.0,
    "traffic_spike": 0.2
  }
}
```

`MetricLossMapper` maps signal names to context metrics. Each
`MetricLossSpec` can express common SRE loss shapes:

- `above`: metric is bad above a target;
- `below`: metric is bad below a target;
- `distance`: metric is bad when far from target;
- `raw`: metric is already a loss.

## Demo

```bash
python -m examples.demo_audit_credit_replay
```

The demo writes 30 audit records, replays the JSONL, and ranks blamed
signals for the incident window using only the persisted audit data.

## Why This Matters

This is the bridge to live SRE integration:

1. control plane emits audit JSONL;
2. post-mortem or streaming job replays it into temporal credit;
3. `CreditAwareLabeler` consumes that attribution to adjust unsafe
   evidence for the self-learning envelope.

That gives the full loop:

```text
AuditTrail -> AuditCreditReplay -> TemporalCreditAssigner
           -> CreditAwareLabeler -> LearnedSafetyEnvelope
```
