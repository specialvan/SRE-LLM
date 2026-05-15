# 2026-05-16 Package Smoke Review

## Verdict

`WATCH-000` is resolved in the working tree. The repository now has an installed-wheel smoke path instead of only source-tree import checks.

## Evidence

- `scripts/package_smoke.py` builds `starship-recovery` with `pip wheel . --no-deps`.
- The smoke check verifies the wheel contains `starship/__init__.py` and `sre_control/__init__.py`.
- The smoke check launches a child Python process outside the repository root with `PYTHONPATH` set to the wheel file, then imports `starship` and `sre_control` from that wheel path.
- The command-line smoke path uses a temporary directory and leaves no `.tmp/` workspace artifact behind.
- `tests/test_package_smoke.py` covers the wheel build/import path.
- `scripts/quality_gate_counts.py` now runs the package smoke after the real pytest quality gate and before updating current-facing counts.

## Verification

```text
python -m pytest tests/test_package_smoke.py -q
.                                                                        [100%]
```

```text
python -m scripts.package_smoke
package smoke ok: starship_recovery-0.1.0-py3-none-any.whl
```

```text
python -m scripts.quality_gate_counts
quality gate pytest count: 97
```

```text
python -m pytest tests -q
........................................................................ [ 74%]
.........................                                                [100%]
```

```text
python -m scripts.build_kb
[1/3] updating quality gate counts ...
[2/3] building mechanism diagrams ...
[3/3] building benefit GIFs ...
done. open docs/knowledge-base.html in a browser.
```

Full-suite verification and collection evidence are recorded in the companion evidence snapshot.

## Backlog Result

- `WATCH-000` moved to `RES-019`.
- Remaining watch items are synthetic-evidence boundaries, adapter cause taxonomy granularity, control-center exposure policy, and release tag hygiene.
