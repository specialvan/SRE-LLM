# 2026-05-15 Quality-Gates and HTML Canonical Review

## Verdict

`AUDIT-005` and `AUDIT-010` are resolved in the working tree.

The HTML knowledge-base entry is no longer ambiguous: V2 is the canonical current entry, and V1 is labeled as an archive snapshot. Current-facing pytest counts are no longer hand-edited only; `scripts/quality_gate_counts.py` runs the real pytest quality gate, derives the count from `pytest --collect-only`, and updates the two current-facing docs.

## Evidence

- `README.md` points reviewers to `docs/V2_Knowledge/knowledge-base.html` as the canonical current entry and labels `docs/knowledge-base.html` as the V1 archive snapshot.
- `docs/knowledge-base.html` hero labels itself as a V1 archive snapshot and links to V2.
- `docs/V2_Knowledge/knowledge-base.html` labels itself as the canonical current entry and removes the stale instruction to re-layout V1 as a future canonical page.
- `scripts/quality_gate_counts.py` runs `python -m pytest tests -q`, parses pytest collection output, updates only the current-facing quality-gate fields in `PR-REQUIREMENTS.md` and V2 HTML, and fails loudly on missing or duplicate matches.
- `tests/test_quality_gate_counts.py` covers parser formats, exact-match replacement, historical-count preservation, and docs update behavior.

## Verification

```text
python -m scripts.quality_gate_counts
quality gate pytest count: 96
```

```text
python -m pytest tests/test_quality_gate_counts.py -q
...........                                                              [100%]
```

```text
python -m pytest tests -q
........................................................................ [ 75%]
........................                                                 [100%]
```

```text
python -m scripts.build_kb
[1/3] updating quality gate counts ...
[2/3] building mechanism diagrams ...
[3/3] building benefit GIFs ...
done. open docs/knowledge-base.html in a browser.
```

Full HTML parser and `git diff --check` evidence are recorded in the companion evidence snapshot for this pass.

## Backlog Result

- `AUDIT-005` moved to `RES-018`.
- `AUDIT-010` moved to `RES-017`.
- The active backlog is empty after this pass; watch items remain active as ongoing review boundaries.
