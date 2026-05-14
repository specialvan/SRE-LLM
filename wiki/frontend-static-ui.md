# Frontend Static UI

This project has no Node/React/Vite frontend. The UI surface is deliberately static and stdlib-friendly:

1. documentation knowledge pages under `docs/`
2. shared documentation enhancement assets under `docs/assets/`
3. a runtime dashboard served by the Python HTTP service from allowlisted package assets

## UI surfaces

| Surface | Entry | Assets | Purpose |
|---|---|---|---|
| V1 knowledge page | `docs/knowledge_base.html` | `docs/assets/knowledge-modern.css`, `docs/assets/knowledge-modern.js`, `docs/images/*` | Math/mechanism storytelling with before/after/gain/GIF visuals. |
| V2 knowledge hub | `docs/V2_Knowledge/knowledge-base.html` | `../assets/knowledge-modern.css`, `../assets/knowledge-modern.js` | Architecture/review/spec dashboard-style snapshot. |
| V3 knowledge snapshot | `docs/V3_Knowledge/knowledge-base.html` | `../assets/knowledge-modern.css`, `../assets/knowledge-modern.js` | Review delta snapshot for the later finding-closure pass. |
| Runtime dashboard | `/dashboard` | `/dashboard/assets/dashboard.css`, `/dashboard/assets/dashboard.js` | Live service state, readiness, service ratings, and dependency synergy. |

## Shared documentation assets

`docs/assets/knowledge-modern.css` and `docs/assets/knowledge-modern.js` are shared progressive-enhancement assets for static docs pages.

Responsibilities:

- add modern visual polish: aurora/glass effects, progress bar, search command bar, back-to-top button
- keep content readable without JavaScript
- respect `prefers-reduced-motion`
- inject a skip link only if the page does not already provide one
- reveal content with `IntersectionObserver` while also adding the legacy `in-view` class used by page-local CSS
- keep the documentation stack no-build: no `package.json`, no bundler, no frontend framework/runtime dependency

When adding another static docs page, prefer linking the shared assets instead of copying UI JavaScript.

## Documentation page external assets

No-build does not mean offline-only. Some source-controlled documentation pages load browser libraries directly from CDNs:

- `docs/knowledge_base.html` loads MathJax for formula rendering.
- `docs/V2_Knowledge/knowledge-base.html` loads MathJax and Mermaid for formula/diagram rendering.
- Mermaid currently runs with `securityLevel: 'loose'`; keep diagrams trusted and source-controlled, not user-provided.

If offline or supply-chain constraints become stricter, vendor or pin these browser assets and update `tests/test_docs_static_ui.py` plus this wiki page.

## Runtime dashboard contract

Runtime dashboard files live under `gan_matchmaking/service/static/`:

```text
gan_matchmaking/service/static/dashboard.html
gan_matchmaking/service/static/dashboard.css
gan_matchmaking/service/static/dashboard.js
```

They are served by `gan_matchmaking/service/app.py` through `gan_matchmaking/service/assets.py`.

Security boundary:

- `load_dashboard_asset(name)` only serves filenames in `ASSET_CONTENT_TYPES`.
- unknown names return 404.
- traversal attempts such as `/dashboard/assets/../app.py` and encoded traversal are covered by HTTP tests.
- dashboard JavaScript renders service IDs and graph labels through `escapeHtml` before assigning HTML.
- `/dashboard` is static; dynamic data comes from `/v1/dashboard/state`.

Runtime data contract for `/v1/dashboard/state`:

```text
status.health
status.ready
status.reason
services[]
synergy[]
limits.max_services
limits.max_synergy_edges
limits.services_truncated
limits.synergy_truncated
generated_at
```

The dashboard is observational. It must not mutate state or make deployment decisions. Dashboard and state endpoints are only served to loopback peers; expose them through authenticated operator-only access if a deployment needs remote viewing.

## Accessibility and motion rules

Static UI pages should keep these invariants:

- primary content remains visible if JavaScript is disabled or delayed
- `prefers-reduced-motion: reduce` disables decorative motion and keeps sections visible
- keyboard users can skip long navigation blocks via a skip link
- active TOC links expose `aria-current="location"` when a page implements scrollspy/active TOC behavior
- status/error messages use `role="status"` or `aria-live` when they change dynamically and need announcement
- wide tables and code blocks remain horizontally scrollable on narrow screens

## Validation commands

```bash
python -m pytest tests/test_docs_static_ui.py tests/test_http_service.py::test_dashboard_html_served tests/test_http_service.py::test_dashboard_static_assets_served tests/test_http_service.py::test_dashboard_unknown_and_traversal_assets_404 tests/test_http_service.py::test_dashboard_state_empty_store -q
python -m pytest tests/test_latency_benchmark.py -q
```

For full release confidence, still run:

```bash
python -m pytest -q
python -m bench.latency --quick --p99-ms 50
```

## Change routing

- Docs-page visual refresh: update `docs/assets/*`, affected `docs/*Knowledge*/knowledge-base.html`, and `tests/test_docs_static_ui.py`.
- Runtime dashboard UI change: update `gan_matchmaking/service/static/*`, `gan_matchmaking/service/assets.py` only if allowlisted filenames change, and `tests/test_http_service.py`.
- Dashboard state shape change: update `DecisionApp.handle_dashboard_state`, `dashboard.js`, `gan_matchmaking/service/__init__.py`, and HTTP tests.
- New dynamic dashboard endpoint: document it here and validate that it is read-only unless explicitly designed otherwise.
