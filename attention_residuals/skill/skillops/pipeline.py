"""SkillOps pipeline facade · PR-025.

Refined spec: ``skill-research/refined/PR-025-skillops-pipeline-refined.md``.

One entry point that advances every container exactly once per
``tick(step)``. Each phase is wrapped in a timing context that:

* measures elapsed wall-clock ms,
* captures exceptions without propagating them (an error becomes a
  field on the :class:`PhaseTiming` and the phase is marked *errored*),
* returns a :class:`PipelineReport` with per-phase stats.

The pipeline does **not** implement any of the business logic — it
wires the M0/M1/M2 components together with the "dependency injection
of Protocols" pattern described in ADR-001. That way the facade stays
additive over the growing component set.

Requirements:

* REQ-OPS-001 · ``tick`` advances every phase exactly once.
* REQ-OPS-002 · ``tick`` is re-entrant safe within a single thread.
* REQ-OPS-003 · Any container exception becomes a ``pipeline_error``
  entry in the report (the pipeline itself does not raise).
"""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import (
    Callable,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    Tuple,
)

import numpy as np

from attention_residuals.sre_control import AuditRecord
from attention_residuals.skill.governance import (
    Elite,
    ElitePool,
    SkillRepository,
)
from attention_residuals.skill.governance.conservative import (
    CommitDecision,
    ConservativeCommit,
)
from attention_residuals.skill.policy_skill import (
    DualGranularitySkillBank,
    ExplorationBiasScheduler,
    HindsightUtilityTracker,
    SkillRouter,
    StepSkill,
    UtilityAwareRetriever,
)
from attention_residuals.skill.trajectory import (
    HierarchicalPatchMerger,
    MustAttendSnapshot,
    Trace2SkillMiner,
)
from attention_residuals.skill.types import (
    BlastRadius,
    ChangeKind,
    Granularity,
    MergedSkillPatch,
    PatchField,
    PatchTarget,
    RoutingDecision,
    SkillRecord,
    SkillVariant,
    SkillVersion,
    Stage,
    VerifierFinding,
    compute_patch_id,
    compute_version_id,
)
from attention_residuals.skill.verify import (
    CombinerHarness,
    GateDecision,
    GateVerdict,
    PatcherConfig,
    ReplayCase,
    SkillPatcher,
    SkillRegressionGate,
    SkillShadowVerifier,
    VerifyResult,
)

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Report structures
# ---------------------------------------------------------------------------


@dataclass
class PhaseTiming:
    """Per-phase stats captured by :meth:`SkillOpsPipeline.tick`."""

    name: str
    elapsed_ms: float = 0.0
    errored: bool = False
    error: Optional[str] = None
    note: Optional[str] = None


@dataclass
class PipelineReport:
    """One tick's summary."""

    step: int
    total_ms: float = 0.0
    skipped_reason: Optional[str] = None
    phases: List[PhaseTiming] = field(default_factory=list)

    candidates_mined: int = 0
    merged_targets: int = 0
    variants_proposed: int = 0
    verifier_passed: int = 0
    verifier_failed: int = 0
    gate_admits: int = 0
    gate_quarantines: int = 0
    gate_rollbacks: int = 0
    elite_admissions: int = 0
    elite_evictions: int = 0
    route_picks: int = 0


# ---------------------------------------------------------------------------
# Dependency container
# ---------------------------------------------------------------------------


@dataclass
class PipelineDeps:
    """All the collaborators the pipeline orchestrates.

    Anything optional may be set to ``None``; the pipeline will skip the
    corresponding phase (and record a note) when asked to advance it.
    """

    # governance (required)
    repository: SkillRepository
    conservative: ConservativeCommit
    elite: ElitePool

    # trajectory (optional — if None, mining is skipped)
    miner: Optional[Trace2SkillMiner] = None
    merger: Optional[HierarchicalPatchMerger] = None

    # verify (optional)
    patcher: Optional[SkillPatcher] = None
    verifier: Optional[SkillShadowVerifier] = None
    gate: Optional[SkillRegressionGate] = None

    # routing (optional)
    bank: Optional[DualGranularitySkillBank] = None
    retriever: Optional[UtilityAwareRetriever] = None
    utility: Optional[HindsightUtilityTracker] = None
    explore: Optional[ExplorationBiasScheduler] = None
    router: Optional[SkillRouter] = None

    # context
    registry_snapshot: MustAttendSnapshot = field(default_factory=MustAttendSnapshot)
    default_tenant: str = "default"
    default_author: str = "skillops-pipeline"


# ---------------------------------------------------------------------------
# Pipeline facade
# ---------------------------------------------------------------------------


class SkillOpsPipeline:
    """Orchestrates the M0/M1/M2 components in a single ``tick(step)``."""

    def __init__(self, deps: PipelineDeps) -> None:
        self._deps = deps
        self._lock = threading.RLock()
        self._paused = False

    # -------------------------------------------------- public API

    def pause(self) -> None:
        with self._lock:
            self._paused = True

    def resume(self) -> None:
        with self._lock:
            self._paused = False

    @property
    def deps(self) -> PipelineDeps:
        return self._deps

    def tick(
        self,
        step: int,
        *,
        audit_batch: Optional[Sequence[AuditRecord]] = None,
        verify_suite: Optional[Sequence[ReplayCase]] = None,
        holdout_suite: Optional[Sequence[ReplayCase]] = None,
        router_query: Optional[np.ndarray] = None,
        router_context: Optional[Mapping[str, float]] = None,
    ) -> PipelineReport:
        """Advance the entire SkillOps loop one step.

        All input batches are optional — absent data simply means the
        corresponding phase is skipped with a ``note`` in the report.
        """
        report = PipelineReport(step=step)
        with self._lock:
            if self._paused:
                report.skipped_reason = "paused"
                return report

            t_total = time.perf_counter()

            state: _TickState = _TickState(step=step)
            with self._phase(report, "evidence"):
                state.audit = list(audit_batch or [])
                if not state.audit:
                    raise _PhaseSkipped("no audit batch supplied")

            with self._phase(report, "mine"):
                if self._deps.miner is None:
                    raise _PhaseSkipped("no miner configured")
                state.candidates = list(
                    self._deps.miner.mine(state.audit, self._deps.registry_snapshot)
                )
                report.candidates_mined = len(state.candidates)
                if not state.candidates:
                    raise _PhaseSkipped("no candidates from miner")

            with self._phase(report, "merge"):
                if self._deps.merger is None:
                    raise _PhaseSkipped("no merger configured")
                state.merged = self._deps.merger.merge(state.candidates)
                report.merged_targets = len(state.merged.targets) if state.merged else 0
                if not state.merged or not state.merged.targets:
                    raise _PhaseSkipped("merge produced no targets")

            with self._phase(report, "propose"):
                if not state.merged or not state.merged.targets:
                    raise _PhaseSkipped("no merged patch to propose from")
                if self._deps.patcher is None:
                    # Absent patcher: treat the merged patch itself as the
                    # single base variant for verification.
                    state.variants = [_variant_from_merged(state.merged)]
                else:
                    findings = state.carried_findings
                    state.variants = list(
                        self._deps.patcher.propose(
                            state.merged, findings, self._deps.registry_snapshot
                        )
                    )
                    if not state.variants:
                        # Fall back to base variant when patcher has no
                        # findings to drive it.
                        state.variants = [_variant_from_merged(state.merged)]
                report.variants_proposed = len(state.variants)
                if not state.variants:
                    raise _PhaseSkipped("no variants proposed")

            with self._phase(report, "verify"):
                if self._deps.verifier is None or not verify_suite:
                    raise _PhaseSkipped("verifier or suite missing")
                if not state.variants:
                    raise _PhaseSkipped("no variants to verify")
                for variant in state.variants:
                    result = self._deps.verifier.verify(
                        variant, verify_suite, holdout=holdout_suite
                    )
                    state.verify_results.append((variant, result))
                    if result.pass_fail:
                        report.verifier_passed += 1
                    else:
                        report.verifier_failed += 1

            with self._phase(report, "gate"):
                if self._deps.gate is None:
                    raise _PhaseSkipped("no gate configured")
                if not state.verify_results:
                    raise _PhaseSkipped("no verify results")
                for variant, result in state.verify_results:
                    verdict = self._deps.gate.decide(result)
                    state.gate_verdicts.append((variant, verdict))
                    if verdict.decision is GateDecision.ADMIT:
                        report.gate_admits += 1
                    elif verdict.decision is GateDecision.QUARANTINE:
                        report.gate_quarantines += 1
                    else:
                        report.gate_rollbacks += 1

            with self._phase(report, "govern"):
                if not state.gate_verdicts:
                    raise _PhaseSkipped("nothing to govern")
                self._govern(state, report)

            with self._phase(report, "route"):
                if self._deps.router is None or router_query is None:
                    raise _PhaseSkipped("router or query missing")
                decisions = list(
                    self._deps.router.pick(router_query, router_context)
                )
                state.routing_decisions = decisions
                report.route_picks = len(decisions)

            report.total_ms = (time.perf_counter() - t_total) * 1000
            return report

    # -------------------------------------------------- govern

    def _govern(self, state: "_TickState", report: PipelineReport) -> None:
        """Promote ADMIT verdicts into repo + elite pool."""
        admitted = 0
        for variant, verdict in state.gate_verdicts:
            if verdict.decision is not GateDecision.ADMIT:
                continue
            # Conservative check (again) before repository put; guards the
            # pathological "patcher slipped through regression rules".
            prev_targets = self._previous_active_targets(variant.source_patch_id)
            verdict_cons = self._deps.conservative.check(prev_targets, variant.targets)
            if verdict_cons.decision is CommitDecision.REJECT:
                _LOGGER.warning(
                    "conservative blocked ADMIT for variant %s: %s",
                    variant.variant_id,
                    verdict_cons.reason,
                )
                continue

            skill_id = _skill_id_for_variant(variant)
            version = SkillVersion(
                version_id=compute_version_id(
                    skill_id, variant.targets, (), self._deps.default_author
                ),
                skill_id=skill_id,
                parents=(),
                author=self._deps.default_author,
                timestamp=time.time(),
                summary=f"admit {variant.variant_id[:8]}"[:80],
                change_kind=ChangeKind.CREATE,
                blast_radius=BlastRadius.compute(
                    [t.signal_name for t in variant.targets],
                    [self._deps.default_tenant],
                    0.1,
                ),
            )
            record = SkillRecord(
                skill_id=skill_id,
                version=version.version_id,
                tenant=self._deps.default_tenant,
                stage=Stage.SANDBOX,
                meta={"variant_id": variant.variant_id},
                targets=variant.targets,
            )
            try:
                self._deps.repository.put(record, version=version)
                self._deps.repository.promote(
                    skill_id,
                    to_stage=Stage.QUARANTINE,
                    tenant=self._deps.default_tenant,
                )
                self._deps.repository.promote(
                    skill_id,
                    to_stage=Stage.ACTIVE,
                    tenant=self._deps.default_tenant,
                )
            except Exception as exc:  # pragma: no cover - defensive
                _LOGGER.exception("govern: repo update failed")
                continue

            # Register with bank + retriever if routing is wired.
            if self._deps.bank is not None:
                self._deps.bank.put_step(
                    StepSkill(
                        skill_id=skill_id,
                        targets=variant.targets,
                    )
                )
            if self._deps.retriever is not None:
                embedding = _stub_embedding(variant, self._deps.retriever.dim)
                self._deps.retriever.upsert(skill_id, embedding)

            event = self._deps.elite.try_admit(
                Elite(variant_id=skill_id, score=verdict.core_pass_rate or 1.0),
                step=state.step,
            )
            admitted += 1
            if event is not None:
                report.elite_evictions += 1
        report.elite_admissions = admitted

    # -------------------------------------------------- phase helper

    @contextmanager
    def _phase(self, report: PipelineReport, name: str):
        t0 = time.perf_counter()
        timing = PhaseTiming(name=name)
        report.phases.append(timing)
        try:
            yield timing
        except _PhaseSkipped as skip:
            timing.note = str(skip)
        except Exception as exc:
            timing.errored = True
            timing.error = repr(exc)
            _LOGGER.exception("phase %s raised", name)
        finally:
            timing.elapsed_ms = (time.perf_counter() - t0) * 1000

    # -------------------------------------------------- helpers

    def _previous_active_targets(
        self, skill_id_hint: str
    ) -> Tuple[PatchTarget, ...]:
        """Try to fetch the current active targets for ``skill_id_hint``.

        Mirrors :meth:`SkillRepository._previous_active_targets` without
        requiring private access. Returns an empty tuple when not present.
        """
        try:
            record = self._deps.repository.get(
                skill_id_hint, tenant=self._deps.default_tenant
            )
        except KeyError:
            return ()
        return tuple(record.targets)


# ---------------------------------------------------------------------------
# Internal scratch state (per-tick)
# ---------------------------------------------------------------------------


@dataclass
class _TickState:
    step: int
    audit: List[AuditRecord] = field(default_factory=list)
    candidates: List = field(default_factory=list)
    merged: Optional[MergedSkillPatch] = None
    variants: List[SkillVariant] = field(default_factory=list)
    carried_findings: List[VerifierFinding] = field(default_factory=list)
    verify_results: List[Tuple[SkillVariant, VerifyResult]] = field(default_factory=list)
    gate_verdicts: List[Tuple[SkillVariant, GateVerdict]] = field(default_factory=list)
    routing_decisions: List[RoutingDecision] = field(default_factory=list)


class _PhaseSkipped(Exception):
    """Sentinel used by :class:`SkillOpsPipeline` to short-circuit a phase
    without marking it as errored.
    """


def _variant_from_merged(merged: MergedSkillPatch) -> SkillVariant:
    return SkillVariant(
        variant_id=merged.patch_id,
        source_patch_id=merged.patch_id,
        targets=merged.targets,
        derived_from=None,
        generation=0,
    )


def _skill_id_for_variant(variant: SkillVariant) -> str:
    """Derive a stable skill_id from the variant's targets."""
    if variant.derived_from:
        return f"skill-{variant.variant_id[:8]}"
    if variant.targets:
        key_signal = sorted(t.signal_name for t in variant.targets)[0]
        return f"skill-{key_signal}-{variant.variant_id[:8]}"
    return f"skill-{variant.variant_id[:8]}"


def _stub_embedding(variant: SkillVariant, dim: int) -> np.ndarray:
    """Deterministic pseudo-embedding for a variant's targets.

    M2 doesn't yet wire real sentence-embedding or learned embeddings
    into the pipeline; we instead seed a small RNG from the variant's
    content hash so the retriever has a stable surface.
    """
    rng = np.random.default_rng(abs(hash(variant.variant_id)) % (2 ** 32))
    vec = rng.standard_normal(dim).astype(np.float32)
    norm = float(np.linalg.norm(vec)) or 1.0
    return vec / norm


__all__ = [
    "PhaseTiming",
    "PipelineDeps",
    "PipelineReport",
    "SkillOpsPipeline",
]
