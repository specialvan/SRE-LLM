# 2026-05-16 Control-Center Exposure Review

## Verdict

`WATCH-003` is resolved in the working tree. The control-center server now has an explicit route policy instead of relying on implicit branch checks inside `do_GET`.

## Evidence

- `scripts/control_center_server.py` keeps the existing Host allow-list: `127.0.0.1:<port>` and `localhost:<port>` only.
- `resolve_control_center_route()` returns `"html"` only for `/`, `/control-center`, and `/control-center.html`.
- `resolve_control_center_route()` returns `"api"` only for `/api/control-center`.
- Other paths, query-string variants, asset paths, and path traversal strings resolve to `None` and fall through to 404.
- `tests/test_control_center.py` covers the Host allow-list and the route allow/deny set.

## Verification

```text
python -m pytest tests/test_control_center.py -q
.......                                                                  [100%]
```

Full-suite verification is recorded in the companion evidence snapshot after this pass.

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
[3/3] building benefit GIFs ...
done. open docs/V2_Knowledge/knowledge-base.html in a browser.
```

## Backlog Result

- `WATCH-003` moved to `RES-020`.
- Remaining watch items are synthetic-evidence boundaries, adapter cause taxonomy granularity, and release tag hygiene.
