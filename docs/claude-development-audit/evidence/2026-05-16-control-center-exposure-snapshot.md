# 2026-05-16 Control-Center Exposure Evidence

> Historical audit artifact; it is not the current handoff.
> Opus review should start from `docs/opus-review/HANDOFF.md`, then verify
> live status in `wiki/review-backlog.md`,
> `docs/codex-review/OPEN_RISKS.md`, and
> `docs/codex-review/QUALITY_GATES.md`.

## Repository State

```text
git status --short --branch
## spacex-session...origin/spacex-session [ahead 13]
 M docs/claude-development-audit/README.md
 M docs/claude-development-audit/backlog.md
 M scripts/control_center_server.py
 M tests/test_control_center.py
?? docs/claude-development-audit/evidence/2026-05-16-control-center-exposure-snapshot.md
?? docs/claude-development-audit/reports/2026-05-16-control-center-exposure.md
```

## Targeted Verification

```text
python -m pytest tests/test_control_center.py -q
.......                                                                  [100%]
```

```text
python -m scripts.quality_gate_counts
quality gate pytest count: 100
```

```text
python -m pytest tests -q
........................................................................ [ 72%]
............................                                             [100%]
```

```text
python -m scripts.build_kb
[1/3] updating quality gate counts ...
[2/3] building mechanism diagrams ...
mechanism diagrams written to: D:\workspace\SRE-LLM\spacex\docs\assets
[3/3] building benefit GIFs ...
benefit GIFs written to: D:\workspace\SRE-LLM\spacex\docs\assets
done. open docs/V2_Knowledge/knowledge-base.html in a browser.
```

```text
html.parser smoke check
docs\control-center.html: ok
docs\V2_Knowledge\knowledge-base.html: ok
docs\knowledge-base.html: ok
```

```text
git diff --check
warning: LF will be replaced by CRLF warnings only; no whitespace errors.
```

## Route Policy

```text
Allowed HTML routes:
/
/control-center
/control-center.html

Allowed API route:
/api/control-center

Denied examples covered by test:
/api/control-center?debug=1
/assets/s01_lossless_convex.png
/../pyproject.toml
```
