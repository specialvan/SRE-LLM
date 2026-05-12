# Round 11 Opening — reviewer checklist

> **Status**: template, not yet activated. Round 11 opens when codex pushes the
> Round 10 follow-up commits (AI-1..AI-7 + `max_dead_letters` patch + ADR-0001).
> Until the push lands, everything in this folder is the Round 10 close-out
> record; start here when you open Round 11.

## Pre-flight (do these before writing any review)

1. **Pull codex's commits**, confirm HEAD moved past `3dbfd50`.
2. **Archive Round 10** (one-time):
   ```powershell
   # From d:\workspace\SRE-LLM\Attention-Residuals
   python -c "import json,pathlib; p=pathlib.Path('docs/V2_Knowledge/state.json'); s=json.loads(p.read_text(encoding='utf-8')); pathlib.Path('docs/claude-review/round-10-archive.json').write_text(json.dumps({'closed_actions': s.pop('closed_actions', []), 'archived_at': s['snapshot_date']}, indent=2, ensure_ascii=False), encoding='utf-8'); s['open_actions']=[]; s.pop('_closed_actions_doc', None); p.write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding='utf-8')"
   ```
3. **Regenerate factual fields**:
   ```powershell
   python docs\V2_Knowledge\_regenerate_state.py --write
   ```
4. **Baseline gate**:
   ```powershell
   python -m pytest --ignore=tests/skill -q
   # expect: all pass; tests_total in state.json must match this number.
   ```
5. **Diagnostics sweep** on touched files — must be 0.

If any step above fails, **stop** and surface the break before opening Round 11.

## Review loop (reviewer fills in)

For each new delta since `3dbfd50`:

- [ ] Commit sha + headline
- [ ] Files touched (code / tests / docs)
- [ ] Invariants potentially in play (reference `state.json.hard_invariants` by ID)
- [ ] Tests added / modified
- [ ] New demos (must come with a doc + test)
- [ ] Any ADR needed (write it to `docs/adr/NNNN-<slug>.md` before merging)
- [ ] Verdict: green / yellow / red

## Deliverables of Round 11

Target the same shape as Round 10 so handback stays consistent:

- `docs/claude-review/06-round-11-review.md` — per-commit findings + verdict.
- `docs/claude-review/07-round-11-action-items.md` — P1/P2/P3 follow-ups with
  explicit test specs and acceptance criteria. If there are no follow-ups, still
  create the file with `# No action items — ship it.`
- Refresh `docs/V2_Knowledge/state.json.open_actions`.
- Refresh `docs/V2_Knowledge/index.html` hero badges + Z6 + Z7 tables.
- Append a row to `CODEX-HANDOFF.md` changelog.

## What not to do

- Do **not** re-open any of the 13 `hard_invariants` without first writing an
  ADR. If a change narrows an invariant (tightens a guardrail), still write an
  ADR so the bar is auditable.
- Do **not** move `closed_actions` back into `open_actions`. If you need to
  revisit AI-1..AI-7, open a new AI-ID (AI-8+) in the current cycle.
- Do **not** merge `docs/knowledge-base.html` (V1) and `docs/V2_Knowledge/` (V2).
  They have different audiences.
- Do **not** introduce HTTP runtime code, message queue integrations, or DB
  persistence into `attention_residuals/sre_*.py`. That's integration-layer
  territory.

## Backlog candidates (Round 11+)

Picked up from open gaps in `state.json.open_gaps` and Round 10 mid-flight
review §8. Reviewer should prioritize based on ops incidents since `3dbfd50`:

- **Prometheus matrix queries** (current reader only handles instant vector /
  scalar).
- **OTLP histogram bucket expansion** — p95/p99/burn-rate from raw buckets.
- **CreditAwareLabeler recent-window cache** — avoid full-history attribution
  on each incident.
- **Per-dimension unsafe quorum** — different action dims have different
  tolerance for unsafe evidence.
- **Streaming replay cursor persistence helper** — reduce boilerplate on
  callers maintaining byte offsets across restarts.
- **Shadow envelope with policy gradient** (Round 6 backlog #7.6).
- **Cross-service envelope federation** (Round 6 backlog #7.7).
- **Automated TOC + section numbering** for `knowledge-base.html` (V1 is
  hand-maintained; will drift as features land).

## Quick links

- Round 10 review → [`00-review-report.md`](./00-review-report.md)
- Round 10 detailed architecture → [`01-detailed-architecture.md`](./01-detailed-architecture.md)
- Round 10 action items → [`02-action-items.md`](./02-action-items.md)
- Round 10 mid-flight delta → [`04-midflight-review.md`](./04-midflight-review.md)
- V2 navigation → [`../V2_Knowledge/index.html`](../V2_Knowledge/index.html)
- State SSOT → [`../V2_Knowledge/state.json`](../V2_Knowledge/state.json)
- ADRs → [`../adr/`](../adr/)
