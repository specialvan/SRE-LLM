# 2026-05-16 Package Smoke Evidence

## Repository State

```text
git status --short --branch
## spacex-session...origin/spacex-session [ahead 11]
 M PR-REQUIREMENTS.md
 M docs/V2_Knowledge/knowledge-base.html
 M docs/claude-development-audit/README.md
 M docs/claude-development-audit/backlog.md
?? docs/claude-development-audit/evidence/2026-05-16-package-smoke-snapshot.md
?? docs/claude-development-audit/reports/2026-05-16-package-smoke.md
?? scripts/package_smoke.py
?? tests/test_package_smoke.py
```

## Collection

```text
python -m pytest tests --collect-only -q
tests/test_allocation.py: 1
tests/test_contracts.py: 19
tests/test_control_center.py: 6
tests/test_ekf.py: 4
tests/test_event_schema.py: 5
tests/test_failure_trace.py: 10
tests/test_import_graph.py: 2
tests/test_mpc.py: 1
tests/test_package_smoke.py: 1
tests/test_quality_gate_counts.py: 11
tests/test_quaternion.py: 3
tests/test_rigid_body.py: 2
tests/test_sre_control.py: 21
tests/test_stability_monitor.py: 8
tests/test_thrust_constraints.py: 3
```

## Targeted Verification

```text
python -m pytest tests/test_package_smoke.py -q
.                                                                        [100%]
```

```text
python -m pytest tests/test_quality_gate_counts.py tests/test_package_smoke.py -q
............                                                             [100%]
```

```text
python -m scripts.package_smoke
package smoke ok: starship_recovery-0.1.0-py3-none-any.whl
```

```text
python -m scripts.quality_gate_counts
quality gate pytest count: 97
```

## Full Verification

```text
python -m pytest tests -q
........................................................................ [ 74%]
.........................                                                [100%]
```

```text
python -m scripts.build_kb
[1/3] updating quality gate counts ...
[2/3] building mechanism diagrams ...
mechanism diagrams written to: D:\workspace\SRE-LLM\spacex\docs\assets
[3/3] building benefit GIFs ...
benefit GIFs written to: D:\workspace\SRE-LLM\spacex\docs\assets
done. open docs/knowledge-base.html in a browser.
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
