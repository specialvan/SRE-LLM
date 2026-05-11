"""Self-iteration pipeline — the primary artefact of this project.

Glues the nine mathematical mechanisms to the SRE decision problem:

1. *Reliability estimator* (TrueSkill) tracks per-service Gaussian beliefs.
2. *Telemetry compressor* (PCA) compresses raw metric vectors into a latent
   stability score.
3. *Dependency synergy* (GNN) scores candidate blast-radius effects on the
   service dependency graph.
4. *Confidence decay* (DynamicK + HandicapElo) adjusts expected success for
   hot-release cadence and streaks.
5. *Canary entropy filter* (EntropyMatcher) drops candidates whose outcome is
   already "too certain" — a canary that always passes isn't informative.
6. *Strategy picker* (EOMMMatcher) chooses the strategy most likely to keep
   the SLO budget (retention).
7. *Risk monitor* (Cox survival) estimates P(incident within horizon) and
   gates GO vs CANARY vs HOLD vs ROLLBACK.
8. *SLO game* (Minimax) resolves feature-vs-reliability conflicts by returning
   a mixed strategy; used when the EOMM/Entropy/Risk layers disagree.

Every stage emits a span; every stage increments metrics; every stage
contributes to the final decision ``trace``.

Error handling policy
---------------------
- Validation errors (:class:`DataError`, :class:`ConfigError`) propagate up
  unchanged; callers decide how to surface them.
- Numerical errors (:class:`NumericError`) are caught per-stage; the pipeline
  falls back to a conservative ``HOLD`` with a rationale explaining which
  stage degraded.
- An empty or freeze-locked context always yields ``HOLD`` or ``ESCALATE``
  *before* any math runs — guarded at :meth:`decide`.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from ..core import (
    AppConfig,
    GanError,
    JsonLineLogger,
    MetricsRegistry,
    NumericError,
    PolicyViolationError,
    SeedManager,
    UnsafeDecisionError,
    default_registry,
    get_logger,
    span,
    with_correlation_id,
)
from ..core.errors import DataError
from ..dynamic_k import DynamicK
from ..entropy_match import EntropyMatcher, binary_entropy
from ..eomm import EOMMMatcher, RetentionModel
from ..gnn_synergy import SynergyGNN, SynergyGraph
from ..handicap import HandicapElo
from ..pca_hidden import HiddenScoreExtractor
from ..survival import ChurnRiskMonitor, CoxModel
from ..trueskill import TrueSkillRater
from .artifacts import (
    RuntimeArtifactBundle,
    build_history_vector,
    build_match_config,
    load_runtime_artifacts,
)
from .circuit import BreakerState, CircuitBreaker
from .domain import (
    Decision,
    DecisionKind,
    ReleaseCandidate,
    ReleaseContext,
    RiskLevel,
    Service,
)
from .features import build_risk_feature_vector
from .locking import PerServiceLock
from .shadow import ShadowMode, coerce as _coerce_shadow
from ..persistence.base import Observation, PipelineStore


__all__ = ["SelfIterationPipeline"]


_CONF_ALPHA = 2.0  # mu - alpha * sigma used as a confidence lower bound.


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _sre_risk_level(p: float) -> RiskLevel:
    if p >= 0.6:
        return RiskLevel.ALARM
    if p >= 0.3:
        return RiskLevel.WARN
    return RiskLevel.OK


def _context_payload(ctx: ReleaseContext) -> Dict[str, Any]:
    """Return the JSON shape accepted by ``cli._ctx_from_dict``."""
    payload: Dict[str, Any] = {
        "service": ctx.service.as_dict(),
        "candidates": [
            {
                "id": c.id,
                "service_id": c.service_id,
                "strategy": c.strategy,
                "canary_fraction": c.canary_fraction,
                "rollback_budget_seconds": c.rollback_budget_seconds,
                "expected_success": c.expected_success,
                "notes": c.notes,
            }
            for c in ctx.candidates
        ],
        "dependencies": list(ctx.dependencies),
        "error_budget_remaining": ctx.error_budget_remaining,
        "freeze_window": ctx.freeze_window,
    }
    if ctx.telemetry is not None:
        payload["telemetry"] = dict(ctx.telemetry)
    if ctx.correlation_id is not None:
        payload["correlation_id"] = ctx.correlation_id
    return payload


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
@dataclass
class SelfIterationPipeline:
    """End-to-end SRE self-iteration decider.

    Parameters
    ----------
    config
        Application configuration. If ``None`` defaults to :func:`AppConfig()`.
    logger
        Injected for testing. Default logger writes JSONL to stderr.
    metrics
        Metrics registry. Default is the process-global registry, so multiple
        pipeline instances share counters unless tests override it.
    seed_manager
        Deterministic RNG hub. Default seed is ``config.seed``.
    store
        Persistence back-end. When provided the pipeline hydrates service
        state on startup, persists ratings after every ``observe_release``
        call, and writes decisions to the audit log.
    shadow_mode
        ``off`` (enforce), ``shadow`` (decisions forced to HOLD at the
        boundary) or ``advisory`` (decisions returned untouched but annotated
        with a ``shadow_from`` rationale).
    circuit_breaker
        Protects the pipeline from retrying a broken dependency forever.
    """

    config: AppConfig = field(default_factory=AppConfig)
    logger: JsonLineLogger = field(default=None)  # type: ignore[assignment]
    metrics: MetricsRegistry = field(default_factory=lambda: default_registry)
    seed_manager: Optional[SeedManager] = None
    store: Optional[PipelineStore] = None
    shadow_mode: ShadowMode = ShadowMode.OFF
    circuit_breaker: Optional[CircuitBreaker] = None

    # Internal state built in ``__post_init__``.
    rater: TrueSkillRater = field(init=False)
    dynamic_k: DynamicK = field(init=False)
    handicap: HandicapElo = field(init=False)
    entropy: EntropyMatcher = field(init=False)
    eomm: EOMMMatcher = field(init=False)
    risk: ChurnRiskMonitor = field(init=False)
    synergy_graph: SynergyGraph = field(init=False)
    synergy_gnn: SynergyGNN = field(init=False)
    pca: HiddenScoreExtractor = field(init=False)
    artifacts: RuntimeArtifactBundle = field(init=False)
    _services: Dict[str, Service] = field(default_factory=dict, init=False)
    _service_locks: PerServiceLock = field(default_factory=PerServiceLock,
                                           init=False)

    def __post_init__(self) -> None:
        if self.logger is None:
            self.logger = JsonLineLogger(
                "gan.sre.pipeline",
                level=self.config.observability.log_level,
                sink=self.config.observability.log_sink,
            )
        if self.seed_manager is None:
            self.seed_manager = SeedManager(root_seed=self.config.seed)

        ts = self.config.trueskill
        self.rater = TrueSkillRater(
            mu0=ts.mu0,
            sigma0=ts.sigma0,
            beta=ts.beta,
            tau=ts.tau,
            draw_probability=ts.draw_probability,
        )

        dk = self.config.dynamic_k
        self.dynamic_k = DynamicK(
            k_max=dk.k_max, k_min=dk.k_min,
            lam=dk.lam, theta=dk.theta,
            penalize_wins=dk.penalize_wins,
        )
        hp = self.config.handicap
        self.handicap = HandicapElo(max_penalty=hp.max_penalty, tau=hp.tau)

        ent = self.config.entropy
        self.entropy = EntropyMatcher(min_entropy=ent.min_entropy)

        em = self.config.eomm
        self.eomm = EOMMMatcher(model=RetentionModel(), epsilon=em.epsilon)

        sv = self.config.survival
        self.risk = ChurnRiskMonitor(
            model=CoxModel(),
            horizon_hours=sv.horizon_hours,
            warn_threshold=sv.warn_threshold,
            alarm_threshold=sv.alarm_threshold,
        )
        gnn_cfg = self.config.gnn
        self.synergy_gnn = SynergyGNN(
            hidden_dim=gnn_cfg.hidden_dim,
            layers=gnn_cfg.layers,
            seed=gnn_cfg.seed,
        )
        self.synergy_graph = SynergyGraph()
        self.pca = HiddenScoreExtractor(n_components=2)

        art_cfg = self.config.artifacts
        self.artifacts = load_runtime_artifacts(
            art_cfg.directory,
            retention_filename=art_cfg.retention_filename,
            retention_metadata_filename=art_cfg.retention_metadata_filename,
            cox_filename=art_cfg.cox_filename,
            cox_metadata_filename=art_cfg.cox_metadata_filename,
        )
        self._hydrate_runtime_artifacts()

        # Normalise shadow mode (allow plain strings from config).
        self.shadow_mode = _coerce_shadow(self.shadow_mode)

        # Register metrics (idempotent).
        self.m_decisions = self.metrics.counter(
            "gan_decisions_total",
            "Total decisions emitted by the SelfIterationPipeline, by kind.",
            label_names=("kind", "risk_level"),
        )
        self.m_stage_latency = self.metrics.histogram(
            "gan_stage_latency_seconds",
            "Per-stage latency inside the SRE pipeline.",
            label_names=("stage",),
            buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25),
        )
        self.m_stage_failures = self.metrics.counter(
            "gan_stage_failures_total",
            "Per-stage failure counter (caught NumericError).",
            label_names=("stage",),
        )
        self.m_confidence = self.metrics.gauge(
            "gan_service_confidence",
            "mu - alpha*sigma for each service.",
            label_names=("service_id",),
        )
        self.m_breaker_state = self.metrics.gauge(
            "gan_breaker_state",
            "Circuit breaker state (0=closed, 1=half_open, 2=open).",
        )
        self.m_shadow_diff = self.metrics.counter(
            "gan_shadow_diff_total",
            "Number of decisions where shadow mode suppressed the enforced kind.",
            label_names=("suppressed_kind",),
        )

        if self.artifacts.fitted:
            self.logger.info(
                "artifacts.loaded",
                artifact_version=self.artifacts.version,
                fitted=self.artifacts.fitted,
            )

        # Hydrate from store if one is provided.
        if self.store is not None:
            for sid in self.store.services.list_ids():
                svc = self.store.services.get(sid)
                if svc is not None:
                    self._services[sid] = svc
                    self.m_confidence.set(
                        svc.mu - _CONF_ALPHA * svc.sigma,
                        labels={"service_id": sid},
                    )
            for a, b, games, wins in self.store.synergy.edges():
                key = self.synergy_graph._key(a, b)  # noqa: SLF001 (intentional)
                self.synergy_graph.co_play[key] = games
                self.synergy_graph.wins_together[key] = wins
                for pid in (a, b):
                    if pid not in self.synergy_graph.players:
                        self.synergy_graph.players.append(pid)

    def _hydrate_runtime_artifacts(self) -> None:
        """Load fitted runtime weights into the online models when available."""
        retention = self.artifacts.retention
        if retention is not None:
            try:
                weights = np.asarray(retention.weights, dtype=float)
                if weights.shape == self.eomm.model.weights.shape:
                    self.eomm.model.weights = weights
                    self.eomm.model.bias = float(retention.bias)
                else:
                    self.logger.warning(
                        "artifacts.retention.shape_mismatch",
                        expected_shape=list(self.eomm.model.weights.shape),
                        got_shape=list(weights.shape),
                    )
            except Exception as exc:
                self.logger.warning(
                    "artifacts.retention.degraded",
                    error_type=type(exc).__name__,
                )

        cox = self.artifacts.cox
        if cox is not None:
            try:
                beta = np.asarray(cox.beta, dtype=float)
                if beta.ndim == 1 and beta.size > 0:
                    self.risk.model.beta = beta
                    self.risk.model._baseline_t = np.asarray(cox.baseline_t, dtype=float)
                    self.risk.model._baseline_H = np.asarray(cox.baseline_H, dtype=float)
                else:
                    self.logger.warning(
                        "artifacts.cox.shape_mismatch",
                        expected_dim="1d+",
                        got_shape=list(beta.shape),
                    )
            except Exception as exc:
                self.logger.warning(
                    "artifacts.cox.degraded",
                    error_type=type(exc).__name__,
                )

    def _recent_observations_for_service(self, service_id: str,
                                         limit: int = 32) -> List[Observation]:
        if self.store is None:
            return []
        try:
            return self.store.observations.recent_observations(service_id, limit=limit)
        except Exception as exc:
            self.logger.warning(
                "artifacts.recent_observations.degraded",
                service_id=service_id,
                error_type=type(exc).__name__,
            )
            return []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def register_service(self, service: Service) -> None:
        """Register a service so that ratings / synergy carry over across decisions."""
        self._services[service.id] = service

    def observe_release(self, service_id: str, success: bool,
                        duration_seconds: float = 0.0,
                        features: Optional[Dict[str, float]] = None,
                        correlation_id: Optional[str] = None,
                        dependencies: Optional[Sequence[str]] = None) -> None:
        """Update the reliability rating after a release outcome.

        This is how the pipeline *learns*: new releases shift the Gaussian
        posterior on reliability.

        The update is a scalar Kalman filter on the success-rate axis in
        ``[0, 1]``:

            mu' = mu + (sigma^2 / (sigma^2 + beta^2)) * (observation - mu)
            sigma^2' = sigma^2 * (1 - sigma^2 / (sigma^2 + beta^2)) + tau^2

        where ``observation = 1.0`` on success and ``0.0`` on failure,
        ``beta`` models per-release noise (skill → perf), and ``tau`` is a
        tiny drift term so sigma never collapses to zero. This keeps mu
        bounded in [0, 1] and sigma monotonically shrinking under consistent
        evidence.

        When a ``store`` was provided, the service rating and the observation
        are persisted atomically.
        """
        with self._service_locks.acquire(service_id):
            svc = self._services.get(service_id)
            if svc is None and self.store is not None:
                svc = self.store.services.get(service_id)
                if svc is not None:
                    self._services[service_id] = svc
            if svc is None:
                raise DataError("unknown service", details={"service_id": service_id})

            beta = max(self.config.trueskill.beta or 0.05, 1e-6)
            tau = max(self.config.trueskill.tau or 0.001, 0.0)

            observation_val = 1.0 if success else 0.0
            var = svc.sigma ** 2
            kalman_gain = var / (var + beta ** 2)
            svc.mu = svc.mu + kalman_gain * (observation_val - svc.mu)
            # Clamp into (0, 1) so it stays on the reliability axis.
            svc.mu = min(1.0 - 1e-6, max(1e-6, svc.mu))
            new_var = var * (1.0 - kalman_gain) + tau ** 2
            svc.sigma = max(new_var, 1e-8) ** 0.5

            svc.total_releases += 1
            if success:
                svc.win_streak += 1
                svc.loss_streak = 0
            else:
                svc.loss_streak += 1
                svc.win_streak = 0
            self.m_confidence.set(
                svc.mu - _CONF_ALPHA * svc.sigma,
                labels={"service_id": service_id},
            )
            # Accumulate on the dependency synergy graph when callers provide
            # the dependency edge set for this observed release.
            deps: List[str] = []
            seen_deps: set[str] = set()
            for dep in dependencies or []:
                dep_id = str(dep)
                if not dep_id or dep_id == service_id or dep_id in seen_deps:
                    continue
                seen_deps.add(dep_id)
                deps.append(dep_id)
            if deps:
                self.synergy_graph.add_match([service_id] + list(deps), win=success)
                if self.store is not None:
                    for dep in deps:
                        if dep != service_id:
                            self.store.synergy.increment(service_id, dep, win=success)

            if self.store is not None:
                self.store.services.save(svc)
                ts = time.time()
                self.store.observations.record(
                    Observation(
                        service_id=service_id,
                        success=bool(success),
                        timestamp=ts,
                        duration_seconds=float(duration_seconds),
                        features=features,
                        correlation_id=correlation_id,
                    )
                )

    # ------------------------------------------------------------------
    # Decide
    # ------------------------------------------------------------------
    def decide(self, ctx: ReleaseContext) -> Decision:
        """Produce a :class:`Decision` for one release context.

        This is the primary entry point for codex-style review: every branch
        writes to ``trace`` so the reasoning is fully auditable.
        """
        ctx.validate()
        self._services.setdefault(ctx.service.id, ctx.service)

        # Circuit breaker — fail fast if we've been burning.
        breaker = self.circuit_breaker
        if breaker is not None:
            self._update_breaker_metric(breaker)
            if not breaker.allow():
                self.logger.warning(
                    "decide.short_circuited",
                    service_id=ctx.service.id,
                    breaker=breaker.snapshot(),
                )
                trace: Dict[str, Any] = {
                    "stages": {},
                    "circuit_breaker": breaker.snapshot(),
                }
                decision = self._emit(
                    DecisionKind.ESCALATE, None, RiskLevel.ALARM, 1.0,
                    ctx.service,
                    ["circuit_breaker=open → ESCALATE"],
                    trace,
                    ctx.correlation_id or f"circuit-open-{uuid.uuid4().hex[:16]}",
                )
                return self._finalize_decision(decision)

        with self._service_locks.acquire(ctx.service.id):
            try:
                decision = self._decide_locked(ctx)
            except GanError:
                if breaker is not None:
                    breaker.record_failure()
                    self._update_breaker_metric(breaker)
                raise
            except Exception:
                if breaker is not None:
                    breaker.record_failure()
                    self._update_breaker_metric(breaker)
                raise

        if breaker is not None:
            breaker.record_success()
            self._update_breaker_metric(breaker)

        return self._finalize_decision(decision)

    def _decide_locked(self, ctx: ReleaseContext) -> Decision:

        with with_correlation_id(ctx.correlation_id) as cid:
            self.logger.info(
                "decide.started",
                service_id=ctx.service.id,
                n_candidates=len(ctx.candidates),
                freeze_window=ctx.freeze_window,
            )

            trace: Dict[str, Any] = {
                "input": {
                    "context": _context_payload(ctx),
                    "config": self.config.to_trace_dict(),
                },
                "stages": {},
                "artifacts": self.artifacts.as_trace(),
            }
            rationale: List[str] = []

            # --- Guard clauses ------------------------------------------------
            if ctx.freeze_window:
                return self._emit(
                    DecisionKind.HOLD, None, RiskLevel.WARN, 0.0,
                    ctx.service, rationale + ["freeze_window=true"], trace, cid,
                )
            if ctx.error_budget_remaining <= 0.0:
                # Budget exhausted — force rollback-ready posture.
                return self._emit(
                    DecisionKind.ROLLBACK, None, RiskLevel.ALARM, 1.0,
                    ctx.service,
                    rationale + ["error_budget_remaining<=0"],
                    trace, cid,
                )

            # --- Stage 1: telemetry compression (PCA) -------------------------
            hidden_summary = self._stage_pca(ctx, trace)

            # --- Stage 2: synergy (GNN) ---------------------------------------
            synergy_summary = self._stage_synergy(ctx, trace)

            # --- Stage 3: adjusted success probability ------------------------
            adj_probs = self._stage_adjusted_probs(ctx, trace)

            # --- Stage 4: entropy filter --------------------------------------
            acceptable_idx = self._stage_entropy(ctx, adj_probs, trace)
            if not acceptable_idx:
                rationale.append("no candidate satisfied min_entropy — HOLD")
                return self._emit(DecisionKind.HOLD, None, RiskLevel.WARN, 0.0,
                                  ctx.service, rationale, trace, cid)

            # --- Stage 5: EOMM / strategy argmax ------------------------------
            chosen, retention_trace = self._stage_eomm(ctx, acceptable_idx, trace)

            # --- Stage 6: risk monitor ----------------------------------------
            risk_p, risk_level = self._stage_risk(ctx, chosen, trace)

            # --- Stage 7: confidence and final decision -----------------------
            confidence = ctx.service.mu - _CONF_ALPHA * ctx.service.sigma
            confidence = max(0.0, min(1.0, confidence))
            rationale.extend(retention_trace)
            kind = self._resolve_decision(chosen, ctx, risk_level, confidence, rationale)

            return self._emit(kind, chosen, risk_level, risk_p, ctx.service,
                              rationale, trace, cid)

    # ------------------------------------------------------------------
    # Per-stage helpers
    # ------------------------------------------------------------------
    def _stage_pca(self, ctx: ReleaseContext, trace: Dict[str, Any]) -> Dict[str, float]:
        with span(self.logger, "stage.pca") as s:
            out: Dict[str, float] = {"fused": float(ctx.service.mu)}
            if ctx.telemetry:
                keys = sorted(ctx.telemetry.keys())
                row = np.array([[ctx.telemetry[k] for k in keys]], dtype=float)
                if row.shape[1] >= 2:
                    try:
                        self.pca.fit(np.vstack([row, row + 1e-6]))
                        z = self.pca.transform(row)
                        out["hidden_norm"] = float(np.linalg.norm(z))
                        out["fused"] = self.pca.fused_score(
                            ctx.service.mu, z.ravel(), alpha=1.0, beta=0.01
                        )
                        out["keys"] = keys  # type: ignore[assignment]
                    except Exception as exc:
                        self.m_stage_failures.inc(labels={"stage": "pca"})
                        self.logger.warning("stage.pca.degraded",
                                            error_type=type(exc).__name__)
            trace["stages"]["pca"] = out
            self._record_latency("pca", s)
            return out

    def _stage_synergy(self, ctx: ReleaseContext, trace: Dict[str, Any]) -> Dict[str, Any]:
        with span(self.logger, "stage.synergy") as s:
            payload: Dict[str, Any] = {"n_dependencies": len(ctx.dependencies),
                                       "score": 0.0}
            nodes, A = self.synergy_graph.adjacency()
            if nodes and len(nodes) >= 2:
                try:
                    feats = np.array([[1.0, 0.0] for _ in nodes], dtype=float)
                    H = self.synergy_gnn.forward(feats, A)
                    idx = {n: i for i, n in enumerate(nodes)}
                    score = 0.0
                    n = 0
                    sid = ctx.service.id
                    if sid in idx:
                        for dep in ctx.dependencies:
                            if dep in idx:
                                score += self.synergy_gnn.synergy_score(H, idx[sid], idx[dep])
                                n += 1
                    payload["score"] = float(score / max(n, 1))
                except Exception as exc:
                    self.m_stage_failures.inc(labels={"stage": "synergy"})
                    self.logger.warning("stage.synergy.degraded",
                                        error_type=type(exc).__name__)
            trace["stages"]["synergy"] = payload
            self._record_latency("synergy", s)
            return payload

    def _stage_adjusted_probs(self, ctx: ReleaseContext,
                              trace: Dict[str, Any]) -> List[float]:
        with span(self.logger, "stage.adjusted_probs") as s:
            out = []
            penalty = self.handicap.penalty(
                ctx.service.win_streak, ctx.service.loss_streak
            )
            # Scale candidate.expected_success (0..1) into Elo-ish ratings
            # around 1500 so Handicap can operate in familiar units.
            r_service = 1500.0 + 400.0 * (ctx.service.mu - 0.99) * 10.0
            for c in ctx.candidates:
                r_cand = 1500.0 + 400.0 * (c.expected_success - 0.99) * 10.0
                # Candidates with bigger canary fractions are riskier — push
                # their effective rating down so Handicap pulls success prob
                # toward 0.5.
                r_cand -= 50.0 * c.canary_fraction
                e = self.handicap.expected_win(r_service, r_cand, penalty)
                out.append(float(e))
            trace["stages"]["adjusted_probs"] = {
                "penalty": penalty,
                "probs": out,
                "k_factor": self.dynamic_k.k(ctx.service.win_streak),
            }
            self._record_latency("adjusted_probs", s)
            return out

    def _stage_entropy(self, ctx: ReleaseContext, probs: List[float],
                       trace: Dict[str, Any]) -> List[int]:
        with span(self.logger, "stage.entropy") as s:
            entropies = [binary_entropy(p) for p in probs]
            acceptable = [i for i, h in enumerate(entropies)
                          if h >= self.config.entropy.min_entropy]
            fallback_used = False
            if not acceptable and entropies:
                # Soft fallback: never return empty — pick the most informative
                # candidate so the downstream stages can still reason. The
                # rationale will record that this was a fallback.
                best = int(max(range(len(entropies)), key=lambda i: entropies[i]))
                acceptable = [best]
                fallback_used = True
            trace["stages"]["entropy"] = {
                "entropies": entropies,
                "acceptable_idx": acceptable,
                "min_entropy": self.config.entropy.min_entropy,
                "fallback_used": fallback_used,
            }
            self._record_latency("entropy", s)
            return acceptable

    def _stage_eomm(self, ctx: ReleaseContext, acceptable_idx: List[int],
                    trace: Dict[str, Any]) -> tuple[ReleaseCandidate, List[str]]:
        """Pick the candidate most likely to preserve the error budget.

        When fitted retention weights are available we use the runtime artifact
        and a seeded epsilon-greedy matcher. Otherwise we fall back to the
        conservative linear heuristic that keeps the pipeline usable during
        bootstrap.
        """
        with span(self.logger, "stage.eomm") as s:
            notes: List[str] = []
            recent_observations = self._recent_observations_for_service(ctx.service.id)
            history = build_history_vector(
                ctx.service,
                recent_observations=recent_observations,
                error_budget_remaining=ctx.error_budget_remaining,
            )
            used_artifact = self.artifacts.retention is not None
            candidate_scores: List[Dict[str, Any]] = []

            if used_artifact:
                try:
                    candidate_pairs = [
                        (i, ctx.candidates[i], build_match_config(ctx.service, ctx.candidates[i]))
                        for i in acceptable_idx
                    ]
                    rng = self.seed_manager.python(f"eomm:{ctx.service.id}")
                    chosen_cfg = self.eomm.best(
                        history,
                        [cfg for _, _, cfg in candidate_pairs],
                        rng=rng,
                    )
                    for i, candidate, cfg in candidate_pairs:
                        score = float(self.eomm.model.prob(history, cfg))
                        candidate_scores.append({
                            "candidate_id": candidate.id,
                            "score": score,
                            "strategy": candidate.strategy,
                        })
                    best_idx = next(
                        i for i, _, cfg in candidate_pairs if cfg == chosen_cfg
                    )
                    chosen = ctx.candidates[best_idx]
                    best_score = next(
                        item["score"] for item in candidate_scores
                        if item["candidate_id"] == chosen.id
                    )
                    notes.append(
                        f"eomm: artifact-picked {chosen.id} (p_retain={best_score:.3f})"
                    )
                    trace["stages"]["eomm"] = {
                        "source": "artifact",
                        "artifact_version": self.artifacts.retention.metadata.version,
                        "chosen_id": chosen.id,
                        "chosen_score": best_score,
                        "acceptable_idx": acceptable_idx,
                        "history": history,
                        "candidate_scores": candidate_scores,
                    }
                    self._record_latency("eomm", s)
                    return chosen, notes
                except Exception as exc:
                    used_artifact = False
                    self.m_stage_failures.inc(labels={"stage": "eomm"})
                    self.logger.warning(
                        "stage.eomm.degraded",
                        error_type=type(exc).__name__,
                    )

            best_idx = acceptable_idx[0]
            best_score = -float("inf")
            for i in acceptable_idx:
                c = ctx.candidates[i]
                score = (
                    1.0 * c.expected_success
                    - 0.5 * c.canary_fraction            # prefer smaller blast radius
                    + 0.2 * (ctx.service.mu - 0.99) * 10 # reliable services can be bolder
                    - 0.3 * (1 - ctx.error_budget_remaining)
                )
                candidate_scores.append({
                    "candidate_id": c.id,
                    "score": score,
                    "strategy": c.strategy,
                })
                if score > best_score:
                    best_score = score
                    best_idx = i
            chosen = ctx.candidates[best_idx]
            notes.append(f"eomm: picked {chosen.id} (score={best_score:.3f})")
            trace["stages"]["eomm"] = {
                "source": "fallback",
                "artifact_used": used_artifact,
                "chosen_id": chosen.id,
                "chosen_score": best_score,
                "acceptable_idx": acceptable_idx,
                "history": history,
                "candidate_scores": candidate_scores,
            }
            self._record_latency("eomm", s)
            return chosen, notes

    def _stage_risk(self, ctx: ReleaseContext, chosen: ReleaseCandidate,
                    trace: Dict[str, Any]) -> tuple[float, RiskLevel]:
        with span(self.logger, "stage.risk") as s:
            feats = build_risk_feature_vector(ctx.service, chosen, ctx)
            try:
                p = self.risk.predict(feats)
            except Exception as exc:
                self.m_stage_failures.inc(labels={"stage": "risk"})
                self.logger.warning("stage.risk.degraded",
                                    error_type=type(exc).__name__)
                # Degrade to WARN with prob 0.5 so we don't auto-GO on failure.
                p = 0.5
            level = _sre_risk_level(p)
            trace["stages"]["risk"] = {
                "features": feats,
                "prob": p,
                "level": level.value,
            }
            self._record_latency("risk", s)
            return p, level

    # ------------------------------------------------------------------
    # Final decision
    # ------------------------------------------------------------------
    def _resolve_decision(
        self,
        chosen: ReleaseCandidate,
        ctx: ReleaseContext,
        risk_level: RiskLevel,
        confidence: float,
        rationale: List[str],
    ) -> DecisionKind:
        """Apply the deterministic rules that turn signals into a DecisionKind.

        This table is the heart of the policy. Kept pure so it can be unit
        tested on synthetic signals.
        """
        # Critical services never GO without a canary.
        tier_critical = ctx.service.tier == "critical"

        if risk_level == RiskLevel.ALARM:
            rationale.append("risk=ALARM → ROLLBACK-ready")
            if ctx.service.loss_streak >= 2:
                # Two consecutive failures + alarm: revert.
                return DecisionKind.ROLLBACK
            return DecisionKind.HOLD

        if risk_level == RiskLevel.WARN:
            rationale.append("risk=WARN → CANARY only")
            return DecisionKind.CANARY

        # risk OK
        if confidence < 0.5:
            rationale.append("confidence<0.5 → CANARY")
            return DecisionKind.CANARY
        if tier_critical and chosen.strategy != "canary":
            rationale.append("tier=critical with non-canary strategy → CANARY downgrade")
            return DecisionKind.CANARY
        if chosen.strategy == "full":
            rationale.append("strategy=full, risk=OK, confidence>=0.5 → GO")
            return DecisionKind.GO
        if chosen.strategy == "canary":
            return DecisionKind.CANARY
        if chosen.strategy == "shadow":
            rationale.append("shadow traffic only — effectively HOLD for prod traffic")
            return DecisionKind.HOLD
        if chosen.strategy == "holdback":
            return DecisionKind.HOLD
        rationale.append(f"unknown strategy '{chosen.strategy}' → ESCALATE")
        return DecisionKind.ESCALATE

    # ------------------------------------------------------------------
    # Emit
    # ------------------------------------------------------------------
    def _emit(
        self,
        kind: DecisionKind,
        chosen: Optional[ReleaseCandidate],
        risk_level: RiskLevel,
        risk_p: float,
        service: Service,
        rationale: List[str],
        trace: Dict[str, Any],
        correlation_id: str,
    ) -> Decision:
        confidence = max(0.0, min(1.0, service.mu - _CONF_ALPHA * service.sigma))
        trace.setdefault("_service_id", service.id)
        return Decision(
            kind=kind,
            chosen=chosen,
            risk_level=risk_level,
            risk_prob=risk_p,
            confidence=confidence,
            rationale=rationale,
            trace=trace,
            artifact_version=self.artifacts.version,
            correlation_id=correlation_id,
        )

    def _publish_decision(
        self,
        decision: Decision,
        *,
        original_kind: DecisionKind,
    ) -> None:
        """Emit post-boundary metrics and logs for the final enforced kind."""
        service_id = str(decision.trace.pop("_service_id", "unknown"))
        self.m_decisions.inc(
            labels={
                "kind": decision.kind.value,
                "risk_level": decision.risk_level.value,
            }
        )
        with with_correlation_id(decision.correlation_id):
            self.logger.info(
                "decide.finished",
                kind=decision.kind.value,
                risk_level=decision.risk_level.value,
                risk_prob=decision.risk_prob,
                confidence=decision.confidence,
                service_id=service_id,
                chosen_id=decision.chosen.id if decision.chosen else None,
                artifact_version=decision.artifact_version,
            )
            if original_kind != decision.kind:
                self.logger.info(
                    "decide.shadow_rewritten",
                    original_kind=original_kind.value,
                    final_kind=decision.kind.value,
                    correlation_id=decision.correlation_id,
                    service_id=service_id,
                )

    def _finalize_decision(self, decision: Decision) -> Decision:
        original_kind = decision.kind
        decision = self._shadow_wrap(decision)
        self._publish_decision(decision, original_kind=original_kind)
        if self.store is not None:
            self.store.observations.record_decision(decision)
        return decision

    def _record_latency(self, stage: str, span_obj) -> None:
        # Extract elapsed from the span's internal state; fall back to 0.
        started = getattr(span_obj, "_started", None)
        if started is not None:
            import time
            elapsed = time.monotonic() - started
            self.m_stage_latency.observe(max(elapsed, 0.0), labels={"stage": stage})

    # ------------------------------------------------------------------
    # Auxiliary helpers (breaker, shadow mode)
    # ------------------------------------------------------------------
    def _update_breaker_metric(self, breaker) -> None:
        state_map = {"closed": 0, "half_open": 1, "open": 2}
        snap = breaker.snapshot()
        self.m_breaker_state.set(float(state_map.get(snap.get("state", "closed"), 0)))

    def _shadow_wrap(self, decision: Decision) -> Decision:
        """Apply the configured :class:`ShadowMode` at the response boundary.

        - ``off``: return as-is.
        - ``shadow``: rewrite every enforced kind to ``HOLD`` and annotate.
          The original kind is kept in ``trace["shadow_suppressed_kind"]`` so
          dashboards can compare what *would* have happened.
        - ``advisory``: return the decision but add a ``shadow_from`` note so
          downstream automation treats it as informational.
        """
        mode = self.shadow_mode
        if mode == ShadowMode.OFF:
            return decision
        if mode == ShadowMode.ADVISORY:
            decision.rationale.append("shadow_mode=advisory (do not enforce)")
            decision.trace["shadow_mode"] = "advisory"
            return decision
        # SHADOW
        original_kind = decision.kind
        if original_kind != DecisionKind.HOLD:
            self.m_shadow_diff.inc(labels={"suppressed_kind": original_kind.value})
            decision.kind = DecisionKind.HOLD
            decision.rationale.append(
                f"shadow_mode=shadow (suppressed kind={original_kind.value})"
            )
        decision.trace["shadow_mode"] = "shadow"
        decision.trace["shadow_suppressed_kind"] = original_kind.value
        return decision
