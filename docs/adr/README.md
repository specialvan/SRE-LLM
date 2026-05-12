# Architecture Decision Records (ADRs)

> When do you write an ADR?
>
> 1. You must violate one of the 13 hard invariants in
>    [`V2_Knowledge/state.json`](../V2_Knowledge/state.json) → **mandatory**.
> 2. You make a choice between two reasonable alternatives where the tradeoff is
>    non-obvious (e.g. `Lock` vs `RLock` — ADR-0001 captured this ex-post).
> 3. You introduce a new invariant or change the default value of one.
> 4. You break a public API (add should not require ADR; break does).
>
> If none of these apply, just ship the commit. ADRs are for decisions that
> a future engineer will want to know "why" about.

---

## Format

Follow [`_template.md`](./_template.md). Name files `NNNN-<short-slug>.md` where:

- `NNNN` is a zero-padded 4-digit sequence number.
- `<short-slug>` is 2–5 kebab-case words that summarize the decision.

Example: `0001-contraction-wrapper-uses-rlock.md`.

---

## Index

| ID | Title | Status | Date |
| --- | --- | --- | --- |
| [0001](./0001-contraction-wrapper-uses-rlock.md) | `ContractionAwareEnvelope` uses `RLock` rather than `Lock` | Accepted | 2026-05-12 |

---

## Status values

- **Proposed** — written but not merged; waiting for review.
- **Accepted** — decision is in effect; code reflects it.
- **Superseded by ADR-NNNN** — replaced by a later decision; keep the file for history.
- **Rejected** — considered and explicitly declined; keep for "we thought about it".
