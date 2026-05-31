# Git Timeline Review

> Historical audit artifact; it is not the current handoff.
> Opus review should start from `docs/opus-review/HANDOFF.md`, then verify
> live status in `wiki/review-backlog.md`,
> `docs/codex-review/OPEN_RISKS.md`, and
> `docs/codex-review/QUALITY_GATES.md`.

## Baseline

The visible local history starts from:

```text
cf9c8dc chore: initial backup before Claude changes
```

Current review head:

```text
13e534e chore: 同步最新分析结果 SUMMARY.txt
```

There are no local tags. `git shortlog -sn --all` reports one author for the available history:

```text
72  yangqidog
```

## Phase Map

| Phase | Representative commits | Review interpretation |
|---|---|---|
| Initial backup | `cf9c8dc` | Clean baseline before the Claude/Codex session work |
| Architecture and handoff docs | `43b58a9`, `4319a41` | SpaceX-to-SRE framing and reviewable architecture material start to appear |
| Runtime event schema | `70c1d6a`, `5e0a94e`, `2c82861`, `1ee8ae5`, `d9cecb7` | Adapter-level events move from scattered traces toward shared runtime schema |
| Claude review packet | `41cdea8`, `59389ee`, `e2658f6` | Handoff and V2 knowledge materials are introduced |
| Spec refinement | `051dfcf`, `587cb32`, `69bb255`, `5009ec4` | `PR-REQUIREMENTS.md` becomes the executable PR-level ledger |
| Medium PR implementation | `566f27e`, `63aba99`, `8b04cb4` | Failure trace, innovation gating, and stack exception handling land |
| Lyapunov/stability pass | `edad8fe` | Stability monitor and SRE wrapper become first-class |
| Review package consolidation | `c36d813`, `7961d9a`, `a547129`, `f4f9508` | Codex/Claude review packets and wiki are consolidated |
| Recent hardening and docs | `22bb894`, `fdf51b3`, `57883ed`, `b85d49a`, `57aafd0`, `f48a72a`, `c3b3815`, `bfdedd3`, `13e534e` | Tests and docs catch up on §10, EKF covariance stability, special-solution derivations, and analysis artifacts |

## Git Findings

### Versioning

`PR-REQUIREMENTS.md` is at spec version `0.3.7`, while `pyproject.toml`, `starship.__version__`, and `sre_control.__version__` are still `0.1.0`. This can be acceptable only if "spec version" and "package version" are explicitly separated.

### Evidence references

Some docs use phrases like "see git log" instead of a pinned evidence table. That keeps docs from violating the "do not pin latest commit" invariant, but it makes offline review slower. This audit package records phase maps instead of relying only on raw log lookup.

### Authorship

The local git author does not distinguish Claude, Codex, or human edits. Future review packets should avoid attributing code authorship from git author alone; use report provenance and commit content instead.

### Release hygiene

No tags exist for the spec milestones. If the project starts using `v0.3.x` as more than a document version, create lightweight or annotated tags and align them with package metadata.
