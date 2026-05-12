# ADR-NNNN · <short title>

- **Status**: Proposed | Accepted | Superseded by ADR-XXXX | Rejected
- **Date**: YYYY-MM-DD
- **Decider**: <name or role>
- **Affected invariants**: <I-NN list, or "none">
- **Affected public API**: <symbol list, or "none">

---

## Context

What's the situation that forced a decision? One to three paragraphs. Include
concrete code paths, production constraints, or external requirements.

Don't editorialize here. The "why one was chosen" goes in **Decision**.

## Options considered

List at least two alternatives, including the one chosen. For each:

### Option A — <label>
- What it is (1 sentence).
- What it costs (complexity / runtime / memory / learning curve).
- What it buys (correctness / flexibility / future-proofing).

### Option B — <label>
(same format)

### Option C — do nothing
(always include this; explicit rejection matters)

## Decision

Which option wins, and why. This is where trade-off reasoning lives.

One paragraph. If the rationale takes more than one paragraph, you either have
two decisions hiding in one ADR, or the Context section isn't concrete enough.

## Consequences

### Positive
- ...

### Negative
- ...

### Neutral
- ...

## Follow-ups

- [ ] Code change pointing to this ADR (file:line)
- [ ] Test that locks in the decision
- [ ] Doc that exposes the choice to operators (if user-visible)
- [ ] Any new invariant entry in `V2_Knowledge/state.json`

## References

- Related ADRs: …
- Related code: …
- Related discussions: …
