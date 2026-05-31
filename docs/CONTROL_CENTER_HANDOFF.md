# Control Center Handoff

> Locked on 2026-05-28 after user approval: the control-center visual direction is **black-gold premium mission control**. Future agents should preserve this style unless the user explicitly asks for a redesign.

## Review Authority

This file is a control-center implementation handoff, not the live completed or
open review ledger. Before using it for Opus review, read the current review
state in this order:

1. `docs/opus-review/HANDOFF.md`, especially its `Git Review Scope Snapshot`;
   refresh `git status --short --branch --untracked-files=all` and
   `git ls-files --others --exclude-standard` before reviewing dirty/untracked
   control-center files.
2. `wiki/review-backlog.md`
3. `docs/codex-review/OPEN_RISKS.md`
4. `docs/codex-review/QUALITY_GATES.md`
5. Historical packets such as `docs/opus-review/OPUS_REVIEW_PACKET.md` and
   `claude-review/docs/v2026-05-28/README.md` only for traceability.

## Entry Points

- Frontend: `docs/control-center.html`
- Data payload: `analysis/control_center_data.py`
- Local server: `python -m scripts.control_center_server`
- URL: `http://127.0.0.1:8765/control-center`
- Regression tests: `python -m pytest tests/test_control_center.py tests/test_control_center_browser_smoke.py tests/test_control_center_browser_dom.py tests/test_control_center_browser_manifest.py tests/test_control_center_browser_error_manifest.py tests/test_control_center_browser_report.py tests/test_control_center_integration_audit.py -q`

## OpenDesign Integration

OpenDesign is installed and was used as the design reference source.

- Shortcut: `C:\Users\Administrator\Desktop\Open Design release-stable-win.lnk`
- Target: `G:\Open Design release-stable-win\Open Design.exe`
- Web ports observed during integration: `127.0.0.1:56261`, `127.0.0.1:56265`
- Design reference: `G:\Open Design release-stable-win\resources\open-design\design-systems\dashboard\DESIGN.md`
- Secondary reference: `G:\Open Design release-stable-win\resources\open-design\design-systems\application\DESIGN.md`

The app payload exposes this in `payload.design_system`. Do not remove it; the UI uses it to make the design provenance visible.

## Locked Visual Direction

The approved theme is not generic dark mode. It is **black-gold premium**:

- Deep black base surfaces with restrained metallic gold highlights.
- Gold is the primary emphasis color, used sparingly for headings, active controls, selected states, chart emphasis, panel highlights, and key numeric values.
- Panels should feel like high-end control hardware: crisp 8px radius, fine borders, subtle inner highlights, and no playful decoration.
- The page should remain dense and operational. Avoid landing-page hero styling, oversized marketing sections, or decorative illustrations.

Current visual anchors in `docs/control-center.html` include:

- Gold highlight: `#f3c96b`
- Metallic gold border/accent: `#c89b3c`
- Champagne grid/background glow: `rgba(255,216,135,...)`
- Dark surfaces: `#09090b`, `#0a0c10`, and the black/brown panel gradients

Do not replace the palette with blue/purple SaaS defaults. Small semantic colors for health/warning/danger are allowed, but they should not dominate the page.

## Locked Interaction Contract

Keep these interactions working:

- Top filter: `#tick-filter` with `all`, `degraded`, and `events` modes.
- Connection-pool toggle: `#show-pool`.
- Previous/next tick buttons: `#prev-tick`, `#next-tick`.
- Chart tick click updates the selected tick and single-tick audit panel.
- Timeline row click updates the chart selection and audit panel.
- Algorithm benefit card click updates the benefit focus panel.
- Segmented controls switch chart/benefit views without reloading the page.
- Keyboard left/right arrows navigate ticks when focus is not inside a control.
- Playback strip controls tick replay through `#play-toggle`, `#play-speed`, and `#tick-scrubber`; spacebar toggles playback when focus is not inside a control.
- Stage chain `#stage-chain` explains the selected tick across observe, plan, canary, guardrail, and allocate. Stage cells set a data lens and should remain compact black-gold chips.
- Risk radar `#risk-radar` summarizes current-tick event density, guardrail projection distance, connection pressure, and load-slot concentration. It is an operational signal panel, not decoration.
- Decision ledger `#decision-ledger` turns the selected tick into an audit sequence across observe, plan, guardrail, and allocate. Ledger rows should remain clickable and set the appropriate lens/chart focus.
- Allocation profile `#alloc-profile` lives inside the load allocation card. It highlights the heaviest slot, exposes per-slot share, and keeps slot clicks wired to the pool chart focus.
- Window insights `#window-insights` sits between context summary and playback. It must summarize the currently filtered/lensed window rather than the whole payload.
- Event kind lens `#event-kind-lens` sits above the event matrix. It lets users narrow the whole dashboard to one event kind through `lensMode="kind"`.
- Focus trail `#focus-trail` sits below the context summary. It exposes the active filter/chart/algorithm/lens as compact chips and must keep clear/filter actions wired.
- Window range `#window-range` sits near the context controls. It switches between all ticks and recent 6/12/24 tick windows, and all aggregate panels must read from `filteredTimeline()`.
- Window hotspots `#window-hotspots` summarizes the current filtered window and jumps directly to peak RPS, event-heavy, pool-heavy, and guardrail-heavy ticks.
- Compare baseline `#compare-baseline` lives inside selected-tick comparison. It lets users lock the current tick as baseline or clear back to previous-tick comparison.
- Share state `#share-state` emits a compact state string for selected tick, baseline, filter, window, lens, chart, benefit focus, and density. Keep copy/refresh actions wired; `#share=` URL hashes must restore before first render.
- Tick compare `#tick-compare` sits between risk radar and decision ledger. It compares the selected tick with the previous tick and keeps each delta clickable.
- Runbook panel `#runbook-panel` lives under event details. It turns the current tick's event and risk context into concise response suggestions.
- Benefit risk bridge `#benefit-risk-bridge` lives under the benefit focus panel. It maps the selected algorithm card to the current tick's risk context and keeps bridge rows clickable.
- Chart status `#chart-status` lives below the telemetry chart. It summarizes chart mode, selected tick, active window, pool visibility, and lens state.
- Shortcut hints `#shortcut-hints` sits below the focus trail. It exposes compact keyboard/action chips for previous/next tick, playback, events window, and lens clearing.
- State lens summary `#state-lens-summary` lives above state rollup. It explains the active state lens and lets users clear it from the same panel.
- Adapter lens `#adapter-lens` lives above control component cards. Component card clicks should sync the algorithm benefit focus and risk bridge.
- Alert thresholds `#alert-thresholds` sits above playback. It compresses degraded ratio, event density, pool peak, and guardrail distance into clickable threshold chips.
- Global actions `#global-actions` contains reset and density controls. Reset must restore filter/window/lens/chart/baseline/density to defaults and refresh the share hash.
- Operator receipt `#operator-receipt` and view health `#view-health` summarize the latest action, reproducible state, active window, lens, density, and share-hash status.
- Safety budget `#safety-budget` sits between alert thresholds and action queue. It derives latency, capacity, guardrail, and allocation margins from `filteredTimeline()` and keeps each budget tile clickable through `data-budget-focus`.
- Capacity budget `#capacity-budget` sits between safety budget and action queue. It derives forecast RPS, per-replica load, pool peak, canary share, and slot pressure from the live payload/current window; tiles stay clickable through `data-capacity-focus`.
- Action queue `#action-queue` turns the current filtered window into event, guardrail, capacity, and allocation follow-up actions. Queue items must update chart/lens focus and operator receipt.

Keep these DOM anchors stable because tests and future agents rely on them:

- `#series-chart`
- `#timeline-list`
- `#tick-event-details`
- `#tick-alloc-shares`
- `#playback-control`
- `#play-toggle`
- `#play-speed`
- `#tick-scrubber`
- `#stage-chain`
- `#risk-radar`
- `#risk-radar-grid`
- `#risk-radar-copy`
- `#decision-ledger`
- `#decision-ledger-list`
- `#decision-ledger-meta`
- `#alloc-profile`
- `#alloc-profile-list`
- `#alloc-profile-meta`
- `#window-insights`
- `#window-insights-grid`
- `#window-insights-copy`
- `#event-kind-lens`
- `#event-kind-lens-list`
- `#focus-trail`
- `#focus-trail-list`
- `#tick-compare`
- `#tick-compare-grid`
- `#tick-compare-meta`
- `#runbook-panel`
- `#runbook-list`
- `#runbook-meta`
- `#benefit-risk-bridge`
- `#benefit-risk-list`
- `#benefit-risk-meta`
- `#chart-status`
- `#chart-status-list`
- `#shortcut-hints`
- `#shortcut-hints-list`
- `#state-lens-summary`
- `#state-lens-copy`
- `#adapter-lens`
- `#adapter-lens-copy`
- `#alert-thresholds`
- `#alert-threshold-list`
- `#global-actions`
- `#reset-dashboard`
- `#density-toggle`
- `#tick-note`
- `#tick-note-list`
- `#operator-feedback`
- `#operator-receipt`
- `#operator-receipt-copy`
- `#operator-receipt-code`
- `#view-health`
- `#view-health-list`
- `#safety-budget`
- `#safety-budget-list`
- `#safety-budget-meta`
- `#capacity-budget`
- `#capacity-budget-list`
- `#capacity-budget-meta`
- `#action-queue`
- `#action-queue-list`
- `#action-queue-meta`
- `#algorithm-benefits-grid`
- `#benefit-focus-panel`
- `#adapters-grid`
- `#event-matrix`
- `#event-log`

## Data Contract

`analysis/control_center_data.py::build_control_center_payload()` is the source of truth. The frontend must continue to consume `/api/control-center` and should not hard-code fake metrics.

Required top-level keys:

- `generated_at`
- `design_system`
- `frontend_contract`
- `hero`
- `summary`
- `timeline`
- `adapters`
- `events`
- `series`
- `load_split`
- `stage_rollup`
- `algorithm_benefits`

`frontend_contract` is emitted by the backend and consumed by the page footer.
Current version: `control-center.v1`; current API path: `/api/control-center`.
Its `timeline_required_fields` list is the minimum field set the frontend needs
for charting, tick drilldown, event lenses, and allocation inspection.

The UI must stay fully Chinese for visible labels and microcopy.

## Do Not Do

- Do not turn this into a marketing landing page.
- Do not remove OpenDesign provenance from the payload or UI.
- Do not replace the black-gold palette with blue/purple dashboard defaults.
- Do not introduce a new frontend build stack unless explicitly requested.
- Do not add nested cards or decorative blobs/orbs.
- Do not make chart colors so bright that they overpower the gold hierarchy.
- Do not edit unrelated review packets while touching the control center.

## Verification Before Handing Off

Run these before claiming the control center is ready:

```bash
python -m pytest tests/test_control_center.py tests/test_control_center_browser_smoke.py tests/test_control_center_browser_dom.py tests/test_control_center_browser_manifest.py tests/test_control_center_browser_error_manifest.py tests/test_control_center_browser_report.py tests/test_control_center_integration_audit.py -q
python -m py_compile analysis/control_center_data.py scripts/control_center_server.py
```

Browser-runtime verification is a separate gate because it needs a real Chromium-compatible browser. Prefer Playwright when available, but the smoke script also falls back to installed Edge/Chrome on this Windows workstation:

```bash
python -m pip install playwright
python -m playwright install chromium
python -m scripts.control_center_browser_smoke
python -m scripts.control_center_browser_smoke --expect-contract-error --screenshot analysis/artifacts/control-center-browser-error-smoke.png --dom-dump analysis/artifacts/control-center-browser-error-smoke.html
python -m scripts.control_center_browser_smoke --expect-frontend-contract-error
python -m scripts.control_center_browser_smoke --verify-all-manifests
python -m scripts.control_center_browser_smoke --verify-frontend-error-manifest analysis/artifacts/control-center-browser-frontend-error-smoke-manifest.json
python -m scripts.control_center_browser_smoke --report-manifests
python -m scripts.control_center_browser_smoke --report-manifests --report-json analysis/artifacts/control-center-browser-evidence-report.json
python -m scripts.control_center_browser_smoke --verify-error-manifest analysis/artifacts/control-center-browser-error-smoke-manifest.json
python -m scripts.package_smoke
python -m scripts.control_center_integration_audit
```

The normal browser smoke script starts the local control-center server on an ephemeral port, fetches the live API payload from `/api/control-center`, records HTTP response metadata, saves that live API payload, opens `/control-center#smoke-interaction` in a real browser, executes the smoke interaction chain, and checks that rendered DOM values match the live API payload. The interaction proof includes selected tick event details, allocation shares, compact density switching, `#share=` hash generation, and reset back to `all` / `comfortable` after the probe advances the page to the next tick. Both Playwright and system-browser paths write DOM dumps and run the same payload-aware assertions.

The backend also exposes `/api/control-center/health` for lightweight runtime checks. JSON API responses include `X-Control-Center-Contract`, `X-Control-Center-API`, `Content-Type`, and `Cache-Control` metadata so contract/version/cache behavior is visible outside the payload body.

Normal-path artifacts:

- `analysis/artifacts/control-center-browser-smoke-api.json` - live API payload snapshot, contract-validated before writing.
- `analysis/artifacts/control-center-browser-smoke-manifest.json` - evidence manifest with URL, contract, summary, `api_response` HTTP metadata, `health_response` payload/metadata, `frontend_response` HTML metadata and `API_URL`, viewport metadata, PNG dimensions, nonblank screenshot status, bytes, and sha256 for each artifact.
- `analysis/artifacts/control-center-browser-smoke-desktop.png`
- `analysis/artifacts/control-center-browser-smoke-desktop.html`
- `analysis/artifacts/control-center-browser-smoke-mobile.png`
- `analysis/artifacts/control-center-browser-smoke-mobile.html`

The manifest is self-verified after generation through `verify_evidence_manifest`; it rechecks artifact existence, bytes, sha256, API snapshot contract validity, API response metadata, health_response contract consistency, frontend_response `API_URL` consistency, manifest summary/contract consistency, PNG dimensions, nonblank screenshot status, and replays the saved DOM dumps through the same payload-aware assertions used during browser generation. To replay the manifest check manually:

```bash
python -m scripts.control_center_browser_smoke --verify-manifest analysis/artifacts/control-center-browser-smoke-manifest.json
```

This command is a thin CLI wrapper around `verify_evidence_manifest` and does not start the HTTP server or browser.

Use `python -m scripts.control_center_browser_smoke --verify-all-manifests` to replay the normal, backend contract-error, and frontend contract-error manifests in one offline check.

Use `python -m scripts.control_center_browser_smoke --report-manifests` to replay the normal, backend contract-error, and frontend contract-error manifests and print a compact evidence report for CI logs or handoff review. The command also writes `analysis/artifacts/control-center-browser-evidence-report.json`; pass `--report-json <path>` to choose a different machine-readable report path. The compact report must include `frontend_error`, proving the frontend rejected a malformed HTTP-200 API payload through its own validator. It must also include `manifest_paths` and `manifest_records` for the normal, backend contract-error, and frontend contract-error manifests, including path, bytes, and sha256 evidence for each source manifest. The console output prints `manifest_paths=`, `manifest_records=`, and `manifest_replay=normal+backend_error+frontend_error` lines so CI logs retain the same provenance and replay signal as the JSON report.

The compact report must also include `contract_depth`, derived from the saved live API snapshot's `frontend_contract`. Required depth keys are `top_level`, `object_groups`, `object_fields`, `array_item_groups`, `array_item_fields`, and `timeline_fields`. This prevents a stale shallow contract report from passing after the frontend/backend payload contract expands.

`python -m scripts.package_smoke` now verifies the generated control-center evidence report after the wheel import smoke, so stale or missing frontend/backend browser evidence fails the package smoke gate. Generate or refresh `analysis/artifacts/control-center-browser-evidence-report.json` with `--report-manifests` before running package smoke. The package smoke gate requires normal desktop/mobile evidence, backend-error evidence, `frontend_error` evidence, positive `contract_depth` counts for every key listed above, matching `manifest_paths`, and non-stale `manifest_records`. It also replays the normal, backend contract-error, and frontend contract-error manifests through `verify_evidence_manifest`, `verify_error_evidence_manifest`, and `verify_frontend_error_evidence_manifest`. Its summary line includes `manifest_records=normal+backend_error+frontend_error` and `manifest_replay=normal+backend_error+frontend_error` so wrapper gates can assert the replay evidence from logs.

`python -m scripts.control_center_integration_audit` writes `analysis/artifacts/control-center-integration-audit.json`. It validates the current backend payload with `validate_control_center_payload`, reads `analysis/artifacts/control-center-browser-evidence-report.json`, reuses package-smoke report verification, and compares the normal browser manifest's saved live API snapshot against the current backend payload by SHA-256 after ignoring only the volatile `generated_at` field. This makes the current frontend/backend integration proof available as one machine-readable artifact and rejects stale browser evidence. Run it after refreshing the browser evidence report and before handing off an integration state.

The `--expect-contract-error` smoke uses a deliberately broken API handler and asserts that the frontend renders the backend failure details: `数据加载失败`, `HTTP 500`, `control_center_contract_violation`, and at least one `missing required frontend field` item. It writes the error-path screenshot, DOM dump, and `analysis/artifacts/control-center-browser-error-smoke-manifest.json`; the error manifest records artifact bytes, sha256, PNG dimensions, nonblank status, and replays the DOM through `verify_error_evidence_manifest`. It does not write the normal success API snapshot or manifest.

The `--expect-frontend-contract-error` smoke uses a deliberately malformed HTTP-200 API payload. The backend response is successful, so the failure must come from `docs/control-center.html::validatePayloadContract`; the rendered hero subtitle must include `数据加载失败` and `前端契约校验失败`. This path writes:

- `analysis/artifacts/control-center-browser-frontend-error-smoke-desktop.png`
- `analysis/artifacts/control-center-browser-frontend-error-smoke-desktop.html`
- `analysis/artifacts/control-center-browser-frontend-error-smoke-manifest.json`

Replay that evidence without starting a browser by running:

```bash
python -m scripts.control_center_browser_smoke --verify-frontend-error-manifest analysis/artifacts/control-center-browser-frontend-error-smoke-manifest.json
```

The manifest verifier is `verify_frontend_error_evidence_manifest`; it checks artifact bytes, sha256, PNG dimensions, nonblank status, and confirms the DOM still contains the frontend validation failure details.

If neither Playwright nor a system Edge/Chrome binary is available, the script exits with code `2` and prints the missing dependency/browser message instead of reporting a false pass.

Also verify the local page after server restart or refresh:

```powershell
Invoke-WebRequest -Uri 'http://127.0.0.1:8765/control-center' -UseBasicParsing
Invoke-WebRequest -Uri 'http://127.0.0.1:8765/api/control-center' -UseBasicParsing
```

Expected smoke signals:

- HTML contains `OpenDesign`.
- HTML contains `id="tick-filter"`.
- HTML contains `id="frontend-contract-version"`.
- HTML contains black-gold anchors such as `#f3c96b` and `#c89b3c`.
- API contains `"provider": "OpenDesign"`.
- API contains `"frontend_contract"` and `"control-center.v1"`.
- No visible mojibake in the browser.

## Current Acceptance Note

The user approved the current visual result with: `效果ok，锁定该版本样式`. Treat this as the baseline style until a later user instruction supersedes it.
