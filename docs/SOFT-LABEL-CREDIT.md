# Soft Labels + Temporal Credit (Round 7)

Round 6 made the safety envelope self-learning, but it still treated
post-hoc labels as hard `SAFE / UNSAFE / UNKNOWN`. Round 7 keeps that
path fully backward-compatible and adds an evidence layer for noisy
production labels.

## 1. Evidence Instead Of Hard Labels

`OutcomeEvidence` represents one judgement as:

```text
safe_evidence   = safety_score * confidence
unsafe_evidence = (1 - safety_score) * confidence
```

Hard labels are just special cases:

| Label | Evidence |
| --- | --- |
| `SAFE` | `OutcomeEvidence(1.0, 1.0)` |
| `UNSAFE` | `OutcomeEvidence(0.0, 1.0)` |
| `UNKNOWN` | `OutcomeEvidence(0.5, 0.0)` |

`LearnedSafetyEnvelope.observe(...)` now accepts either the old
`OutcomeLabel` values or the new `OutcomeEvidence` values. SAFE samples
feed weighted quantiles; UNSAFE samples accumulate weighted quorum.

## 2. Credit-Aware Unsafe Downgrading

An SLO breach is not always caused by the action that happened near it.
`CreditAwareLabeler` wraps a base labeler and a `TemporalCreditAssigner`
so that only controller-attributed unsafe evidence tightens the envelope:

```text
controllable_ratio = sum(blame for controllable signals) / sum(all blame)
adjusted_unsafe    = raw_unsafe * controllable_ratio
```

If blame is mostly exogenous traffic, the unsafe evidence becomes weak.
If blame lands on a controller signal, the unsafe evidence stays strong.

## 3. New API

```python
from attention_residuals.sre_self_envelope import (
    OutcomeEvidence,
    CreditAwareLabeler,
    EnvelopeLearner,
)
from attention_residuals.sre_math import TemporalCreditAssigner
```

Demo:

```bash
python -m examples.demo_credit_aware_envelope
```

The demo shows traffic-caused `UNSAFE` labels staying weak, while
controller-caused `UNSAFE` labels trigger the safety ratchet.

Audit replay handoff:

- `docs/AUDIT-CREDIT-REPLAY.md`
- `examples/demo_audit_credit_replay.py`

That path turns persisted `AuditTrail.to_jsonl()` output back into
`TemporalCreditAssigner`, then feeds `CreditAwareLabeler`.

## 4. Tests Added

`tests/test_sre_self_envelope.py` now covers:

- soft UNSAFE evidence accumulating toward quorum;
- low-confidence SAFE outliers not dominating learned quantiles;
- `EnvelopeLearner` stats tracking evidence mass;
- temporal credit downgrading exogenous UNSAFE;
- temporal credit preserving controller-caused UNSAFE.
