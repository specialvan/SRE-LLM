# gan-matchmaking · SRE self-iteration decider

> A production-style decision engine that decides `GO / CANARY / HOLD /
> ROLLBACK / ESCALATE` for every release, built on nine well-understood
> mathematical mechanisms (TrueSkill, PCA, GNN, Cox survival, minimax game…).
>
> Originally inspired by the community article "王者荣耀 GAN（肝）机制" which
> framed matchmaking as nine composable probabilistic tools; this project
> keeps the maths and re-expresses the domain as **SRE self-iteration**.

The nine maths modules, their SRE meaning, and the glue code to turn them
into an auditable pipeline live side by side in this repo.

---

## 1. Why this exists

Reliability engineering needs decisions that are:

1. **Auditable** — every stage's intermediate output is visible in the
   `Decision.trace` and in structured JSONL logs.
2. **Deterministic** — same config + same context ⇒ same decision (see
   [ADR-0004](docs/adr/0004-determinism-and-seeding.md)).
3. **Composable** — the Cox model, the TrueSkill rater, the entropy filter
   can be swapped or retrained individually without rewriting the rest.
4. **Safe under missing data** — Day-1 bootstrap with no training history
   still yields conservative decisions (see
   [ADR-0005](docs/adr/0005-fallback-strategy-for-untrained-models.md)).

---

## 2. Layered architecture

```
gan_matchmaking/
├── core/                    shared infrastructure
│   ├── config.py            typed, validated AppConfig
│   ├── errors.py            typed exception hierarchy
│   ├── logging.py           JSONL structured logger
│   ├── metrics.py           Prometheus-style in-process registry
│   ├── tracing.py           correlation-id + span context manager
│   ├── random.py            deterministic SeedManager
│   └── protocols.py         Protocols the domain speaks against
│
├── persistence/             pluggable state store (in-memory + SQLite)
├── sre/                     SRE domain layer
│   ├── domain.py            Service / ReleaseCandidate / ReleaseContext / Decision
│   ├── self_iteration.py    SelfIterationPipeline — the primary artefact
│   ├── circuit.py           CircuitBreaker
│   ├── locking.py           per-service mutex
│   └── shadow.py            off / shadow / advisory rollout modes
├── service/                 stdlib HTTP server (/v1/decide, /healthz, …)
├── training/                offline Cox + RetentionModel trainers
│
├── <top-level>              the nine mechanism modules
│   ├── trueskill.py         §1 Bayesian reliability rating
│   ├── pca_hidden.py        §4 telemetry compression
│   ├── gnn_synergy.py       §5 dependency synergy
│   ├── dynamic_k.py         §3 confidence decay
│   ├── handicap.py          §6 risk-adjusted success probability
│   ├── entropy_match.py     §7 informative canary filter
│   ├── eomm.py              §2 retention-of-SLO argmax
│   ├── survival.py          §8 Cox time-to-incident
│   ├── minimax_bp.py        §9 SLO / budget game
│   └── pipeline.py          game-world demo (kept for reference only)
│
├── cli.py                   `python -m gan_matchmaking.cli decide …`
├── bench/latency.py         decision-latency SLO benchmark
├── Dockerfile               multi-stage image
├── deploy/kubernetes/       ConfigMap / Deployment / CronJob / PVC / Service
├── .github/workflows/ci.yml CI: tests on 3.10 / 3.11 / 3.12 + benchmark gate
├── docs/
│   ├── adr/                 architecture decision records
│   ├── runbooks/            on-call procedures
│   ├── knowledge_base.html  single-page maths knowledge base
│   └── images/              37 per-mechanism figures + story GIF
├── examples/
│   ├── sre_demo.py          end-to-end SRE pipeline demo
│   └── demo_pipeline.py     game-world demo (legacy)
└── tests/                   80+ unit + integration + property tests
```

Layer rules (see [ADR-0003](docs/adr/0003-layered-structure-core-sre-game.md)):

- `core/` imports nothing from the package.
- Mechanism modules import `core/` only.
- `sre/` depends on both.
- `pipeline.py` (game) and `sre/self_iteration.py` never import each other.

---

## 3. The nine mechanisms and their SRE meaning

| # | Mechanism | Maths | SRE meaning |
| --- | --- | --- | --- |
| 1 | TrueSkill | $s \sim \mathcal{N}(\mu,\sigma^2)$ | Release-confidence rating |
| 2 | EOMM | $\max\ \mathbb{E}[P(\mathrm{Retain}\mid M,H_t)]$ | Release-strategy picker (retention-of-SLO) |
| 3 | Dynamic K | $K = K_{\min}+\dfrac{K_{\max}-K_{\min}}{1+e^{\lambda(s-\theta)}}$ | Confidence decay under fast-release cadence |
| 4 | PCA | $X^{\top}Xv = \lambda v$ | Telemetry compression |
| 5 | GNN synergy | $h^{(l+1)} = \mathrm{ReLU}(Wh + \sum W_{ij}h_j)$ | Dependency blast-radius synergy |
| 6 | Handicap Elo | $E_A = 1/(1+10^{(\Delta R + P)/400})$ | Risk-adjusted success probability |
| 7 | Entropy filter | $H(p) = -p\log_2 p - (1-p)\log_2(1-p)$ | Informative-canary filter |
| 8 | Cox survival | $h(t\mid X) = h_0(t)e^{\beta^{\top}X}$ | Time-to-incident risk |
| 9 | Minimax | $\min_y\max_x U = \max_x\min_y U$ | SLO / feature-vs-reliability game |

---

## 4. Quick start

```
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]

# Run the full test suite
pytest -q

# Run the SRE demo end-to-end
python -m examples.sre_demo

# Ask for a decision from the CLI
python -m gan_matchmaking.cli decide --input examples/sample_context.json

# Launch the HTTP service (stdlib only, binds :8080)
python -m gan_matchmaking.service --state-db state.sqlite
curl -s http://localhost:8080/healthz
curl -s -X POST http://localhost:8080/v1/decide \
  -H 'Content-Type: application/json' \
  -d @examples/sample_context.json

# Run the decision-latency benchmark
python -m bench.latency --quick

# Train Cox + Retention models from persisted observations
python -m gan_matchmaking.training --state-db state.sqlite
```

A `Decision` is printed as indented JSON and can be diffed / replayed.
Structured JSONL logs go to stderr by default and can be redirected to
fluent-bit / loki / stackdriver verbatim.

---

## 5. Reviewer checklist

A short list for codex-style reviews. Each item has a concrete file:

- [x] Typed config with validation — `core/config.py` + `tests/test_core_config.py`
- [x] Typed exception hierarchy — `core/errors.py`
- [x] Structured logs + correlation ids — `core/logging.py`, `core/tracing.py`
- [x] Metrics registry with Prometheus export — `core/metrics.py`
- [x] Deterministic RNG hub — `core/random.py` + ADR-0004
- [x] Domain layer with enum-typed decisions — `sre/domain.py` + ADR-0002
- [x] Integration test suite — `tests/test_sre_self_iteration.py`
- [x] CLI + smoke tests — `gan_matchmaking/cli.py` + `tests/test_cli.py`
- [x] ADRs documented — `docs/adr/`
- [x] Runbooks for operators — `docs/runbooks/`
- [x] Math knowledge base — `docs/knowledge_base.html`
- [x] Persistence layer (in-memory + SQLite) — `persistence/` + `tests/test_persistence.py`
- [x] Concurrency guards — `sre/locking.py` + `sre/circuit.py`
- [x] Shadow rollout modes — `sre/shadow.py` (off / shadow / advisory)
- [x] HTTP service — `gan_matchmaking/service/` + `tests/test_http_service.py`
- [x] Offline training — `gan_matchmaking/training/` + `tests/test_training.py`
- [x] Container image — `Dockerfile`
- [x] Kubernetes manifests — `deploy/kubernetes/`
- [x] CI workflow — `.github/workflows/ci.yml`
- [x] Performance SLO benchmark — `bench/latency.py` (p99 &lt; 50ms budget)

---

## 6. Further reading

- [`PR-REQUIREMENTS.md`](PR-REQUIREMENTS.md) — per-PR delivery plan.
- [`docs/knowledge_base.html`](docs/knowledge_base.html) — 单页数学知识库，每机制四图（before / after / gain / gif）+ SRE 控制方案参考。
- [`docs/adr/`](docs/adr/) — architecture decisions with rationale.
- [`docs/runbooks/`](docs/runbooks/) — on-call procedures.

---

## 7. Disclaimer

This project is an academic reproduction of externally published ideas,
used here as a vehicle for SRE decision engineering. It does **not**
represent any vendor's production algorithms or parameters.
