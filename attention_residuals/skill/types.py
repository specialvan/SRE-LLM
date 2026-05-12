"""Shared SkillOps data types · single source of truth.

This module implements ``architecture/01-data-model.md``. Every shared
cross-module dataclass lives here; individual modules keep only their
internal structures.

All structures:

* are ``@dataclass(frozen=True)`` (immutable after construction);
* are JSON round-trippable via :func:`to_dict` / :func:`from_dict`;
* embed a ``_schema`` field (``"skillops/v1"``, see ADR-003);
* have content-hash ids (:func:`compute_patch_id`,
  :func:`compute_version_id`) that are **deterministic** and
  **time-independent**.

Requirements covered:

* REQ-DAT-001 · frozen dataclass in types.py
* REQ-DAT-002 · to_dict / from_dict round-trip
* REQ-DAT-003 · _schema field
* REQ-DAT-004 · PatchTarget.field closed set
* REQ-DAT-005 · rationale length ≤ 200
* REQ-DAT-006 · SkillRecord unique key (skill_id, version, tenant)
* REQ-DAT-007 · SkillVersion immutable
* REQ-DAT-008 · BlastRadius.blast_score formula
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, FrozenSet, Mapping, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Schema version (ADR-003)
# ---------------------------------------------------------------------------

SCHEMA_VERSION = "skillops/v1"


# ---------------------------------------------------------------------------
# Enumerations — kept as closed sets; adding values is a breaking schema
# change and requires a new ADR (see ADR-003 and ADR-006).
# ---------------------------------------------------------------------------


class PatchField(str, Enum):
    """Which combiner field a :class:`PatchTarget` adjusts."""

    BIAS = "bias"
    FLOOR = "floor"
    CEILING = "ceiling"
    TEMPERATURE = "temperature"


class Stage(str, Enum):
    """Skill lifecycle stage."""

    SANDBOX = "sandbox"
    QUARANTINE = "quarantine"
    ACTIVE = "active"
    RETIRED = "retired"


class ChangeKind(str, Enum):
    """What kind of mutation produced a :class:`SkillVersion`."""

    CREATE = "create"
    EDIT = "edit"
    MERGE = "merge"
    SPLIT = "split"
    REVERT = "revert"
    IMPORT = "import"


class Granularity(str, Enum):
    """Task-level vs step-level skill."""

    TASK = "task"
    STEP = "step"


class EventKind(str, Enum):
    """All known SkillOps event kinds."""

    AUDIT_COMMIT = "audit_commit"
    SKILL_COMMIT = "skill_commit"
    STAGE_TRANSITION = "stage_transition"
    GUARD_EVENT = "guard_event"
    REDUNDANCY_REPORT = "redundancy_report"
    ROUTING_PICK = "routing_pick"
    GATE_VERDICT = "gate_verdict"
    MERGE_CONFLICT = "merge_conflict"
    PIPELINE_ERROR = "pipeline_error"


class ConflictReason(str, Enum):
    """Reasons a :class:`MergeConflict` may carry."""

    FLOOR_BUDGET_EXCEEDED = "floor_budget_exceeded"
    CEILING_BUDGET_INSUFFICIENT = "ceiling_budget_insufficient"
    OPPOSITE_DELTA = "opposite_delta"
    MUST_ATTEND_VIOLATION = "must_attend_violation"
    REGISTRY_DRIFT = "registry_drift"


class CommitDecision(str, Enum):
    """Output of :class:`ConservativeCommit.check`."""

    ACCEPT = "accept"
    REJECT = "reject"
    OVERRIDDEN = "overridden"


# ---------------------------------------------------------------------------
# Helpers: hashing & canonical JSON
# ---------------------------------------------------------------------------


def _canonical(obj: Any) -> Any:
    """Return a canonical JSON-ready form (sorted keys, rounded floats)."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            raise ValueError("non-finite floats are not canonicalisable")
        return round(obj, 6)
    if isinstance(obj, (list, tuple)):
        return [_canonical(x) for x in obj]
    if isinstance(obj, Mapping):
        return {k: _canonical(obj[k]) for k in sorted(obj.keys())}
    return obj


def _stable_sha1(payload: Any) -> str:
    """Return 16-char sha1 hex of canonical JSON encoding of ``payload``."""
    canonical = json.dumps(_canonical(payload), sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:16]


def compute_patch_id(
    targets: Sequence["PatchTarget"], trigger: Mapping[str, float]
) -> str:
    """Deterministic id for a (targets, trigger) pair.

    REQ-EVD-005 · same inputs yield same id.
    Order-independent: sorted by (signal_name, field) before hashing.
    """
    sorted_targets = sorted(targets, key=lambda t: (t.signal_name, t.field.value))
    payload = {
        "targets": [t.to_dict() for t in sorted_targets],
        "trigger": dict(trigger),
    }
    return _stable_sha1(payload)


def compute_version_id(
    skill_id: str,
    targets: Sequence["PatchTarget"],
    parents: Sequence[str],
    author: str,
) -> str:
    """Deterministic id for a :class:`SkillVersion`.

    Excludes timestamp — two semantically equivalent commits produce the
    same version_id, which makes revert & replay idempotent.
    """
    sorted_targets = sorted(targets, key=lambda t: (t.signal_name, t.field.value))
    payload = {
        "skill_id": skill_id,
        "targets": [t.to_dict() for t in sorted_targets],
        "parents": sorted(parents),
        "author": author,
    }
    return _stable_sha1(payload)


# ---------------------------------------------------------------------------
# Core dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PatchTarget:
    """One atomic combiner adjustment: ``field += delta`` for ``signal_name``.

    Parameters
    ----------
    signal_name
        Name of the ``SignalSpec`` this target adjusts.
    field
        One of ``PatchField`` — closed set (REQ-DAT-004).
    delta
        Additive change; signed. Must be finite.
    rationale
        Human-readable explanation, ≤ 200 chars (REQ-DAT-005).
    """

    signal_name: str
    field: PatchField
    delta: float
    rationale: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.field, PatchField):
            raise ValueError(
                f"PatchTarget.field must be PatchField, got {type(self.field).__name__}"
            )
        if not math.isfinite(self.delta):
            raise ValueError(f"PatchTarget.delta must be finite, got {self.delta}")
        if len(self.rationale) > 200:
            raise ValueError(
                f"PatchTarget.rationale length {len(self.rationale)} > 200"
            )
        # Field-specific ranges (refined/PR-012 §2)
        if self.field is PatchField.FLOOR and not (0.0 <= self.delta <= 1.0):
            raise ValueError(f"floor delta must be in [0,1], got {self.delta}")
        if self.field is PatchField.CEILING and not (-1.0 <= self.delta <= 0.0):
            raise ValueError(f"ceiling delta must be in [-1,0], got {self.delta}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "_schema": SCHEMA_VERSION,
            "signal_name": self.signal_name,
            "field": self.field.value,
            "delta": float(self.delta),
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "PatchTarget":
        return cls(
            signal_name=str(d["signal_name"]),
            field=PatchField(d["field"]),
            delta=float(d["delta"]),
            rationale=str(d.get("rationale", "")),
        )


@dataclass(frozen=True)
class MergeConflict:
    """Record of a merge step that could not be auto-resolved.

    ``candidates`` are the offending :class:`PatchTarget` list; ``reason``
    is a closed enum value (REQ-KNE-003).
    """

    signal_name: str
    field: str
    candidates: Tuple[PatchTarget, ...]
    reason: ConflictReason

    def to_dict(self) -> Dict[str, Any]:
        return {
            "_schema": SCHEMA_VERSION,
            "signal_name": self.signal_name,
            "field": self.field,
            "candidates": [c.to_dict() for c in self.candidates],
            "reason": self.reason.value,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "MergeConflict":
        return cls(
            signal_name=str(d["signal_name"]),
            field=str(d["field"]),
            candidates=tuple(PatchTarget.from_dict(x) for x in d["candidates"]),
            reason=ConflictReason(d["reason"]),
        )


@dataclass(frozen=True)
class SkillPatchCandidate:
    """Offline-mined candidate produced by :class:`Trace2SkillMiner`.

    Invariants (checked at construction):
    - ``support >= 0``
    - ``score >= 0``
    - ``patch_id`` is deterministic from ``(targets, trigger)``.
    """

    patch_id: str
    trigger: Mapping[str, float]
    targets: Tuple[PatchTarget, ...]
    evidence_steps: Tuple[int, ...]
    support: int
    avg_cost_before: float
    score: float
    registry_hash: str

    def __post_init__(self) -> None:
        if self.support < 0:
            raise ValueError("support must be >= 0")
        if self.score < 0:
            raise ValueError("score must be >= 0")
        expected = compute_patch_id(self.targets, self.trigger)
        if self.patch_id != expected:
            raise ValueError(
                f"patch_id mismatch: declared {self.patch_id}, computed {expected}"
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "_schema": SCHEMA_VERSION,
            "patch_id": self.patch_id,
            "trigger": dict(self.trigger),
            "targets": [t.to_dict() for t in self.targets],
            "evidence_steps": list(self.evidence_steps),
            "support": int(self.support),
            "avg_cost_before": float(self.avg_cost_before),
            "score": float(self.score),
            "registry_hash": self.registry_hash,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "SkillPatchCandidate":
        return cls(
            patch_id=str(d["patch_id"]),
            trigger=dict(d["trigger"]),
            targets=tuple(PatchTarget.from_dict(x) for x in d["targets"]),
            evidence_steps=tuple(int(s) for s in d["evidence_steps"]),
            support=int(d["support"]),
            avg_cost_before=float(d["avg_cost_before"]),
            score=float(d["score"]),
            registry_hash=str(d["registry_hash"]),
        )


@dataclass(frozen=True)
class MergedSkillPatch:
    """Result of :class:`HierarchicalPatchMerger.merge(...)`.

    ``dropped + conflicts`` must be consumed by the caller (REQ-DAT-011).
    """

    patch_id: str
    targets: Tuple[PatchTarget, ...]
    dropped: Tuple[PatchTarget, ...] = ()
    conflicts: Tuple[MergeConflict, ...] = ()
    provenance: Tuple[str, ...] = ()
    registry_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "_schema": SCHEMA_VERSION,
            "patch_id": self.patch_id,
            "targets": [t.to_dict() for t in self.targets],
            "dropped": [t.to_dict() for t in self.dropped],
            "conflicts": [c.to_dict() for c in self.conflicts],
            "provenance": list(self.provenance),
            "registry_hash": self.registry_hash,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "MergedSkillPatch":
        return cls(
            patch_id=str(d["patch_id"]),
            targets=tuple(PatchTarget.from_dict(x) for x in d["targets"]),
            dropped=tuple(PatchTarget.from_dict(x) for x in d.get("dropped", [])),
            conflicts=tuple(MergeConflict.from_dict(x) for x in d.get("conflicts", [])),
            provenance=tuple(str(x) for x in d.get("provenance", [])),
            registry_hash=str(d.get("registry_hash", "")),
        )


@dataclass(frozen=True)
class VerifierFinding:
    """Diagnosis emitted by PR-007 SkillShadowVerifier on a failing case."""

    finding_id: str
    offending_signals: Tuple[str, ...]
    suggested_direction: Mapping[str, int]
    severity: float
    diagnostics: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not (0.0 <= self.severity <= 1.0):
            raise ValueError(f"severity must be in [0,1], got {self.severity}")
        for name, d in self.suggested_direction.items():
            if d not in (-1, 0, 1):
                raise ValueError(
                    f"suggested_direction[{name}] must be -1/0/+1, got {d}"
                )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "_schema": SCHEMA_VERSION,
            "finding_id": self.finding_id,
            "offending_signals": list(self.offending_signals),
            "suggested_direction": dict(self.suggested_direction),
            "severity": float(self.severity),
            "diagnostics": {k: float(v) for k, v in self.diagnostics.items()},
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "VerifierFinding":
        return cls(
            finding_id=str(d["finding_id"]),
            offending_signals=tuple(str(x) for x in d["offending_signals"]),
            suggested_direction={k: int(v) for k, v in d["suggested_direction"].items()},
            severity=float(d["severity"]),
            diagnostics={k: float(v) for k, v in d.get("diagnostics", {}).items()},
        )


@dataclass(frozen=True)
class SkillVariant:
    """A patcher-generated variant awaiting verification."""

    variant_id: str
    source_patch_id: str
    targets: Tuple[PatchTarget, ...]
    derived_from: Optional[str] = None
    generation: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "_schema": SCHEMA_VERSION,
            "variant_id": self.variant_id,
            "source_patch_id": self.source_patch_id,
            "targets": [t.to_dict() for t in self.targets],
            "derived_from": self.derived_from,
            "generation": int(self.generation),
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "SkillVariant":
        return cls(
            variant_id=str(d["variant_id"]),
            source_patch_id=str(d["source_patch_id"]),
            targets=tuple(PatchTarget.from_dict(x) for x in d["targets"]),
            derived_from=(str(d["derived_from"]) if d.get("derived_from") else None),
            generation=int(d.get("generation", 0)),
        )


@dataclass(frozen=True)
class BlastRadius:
    """Impact estimate used at promote time (REQ-DAT-008).

    ``blast_score = 0.4·|S|/N_S + 0.3·|T|/N_T + 0.3·traffic_share``
    """

    affected_signals: Tuple[str, ...]
    affected_tenants: Tuple[str, ...]
    estimated_traffic_share: float
    blast_score: float

    @staticmethod
    def compute(
        affected_signals: Sequence[str],
        affected_tenants: Sequence[str],
        estimated_traffic_share: float,
        total_signals: int = 10,
        total_tenants: int = 3,
    ) -> "BlastRadius":
        s_ratio = len(set(affected_signals)) / max(total_signals, 1)
        t_ratio = len(set(affected_tenants)) / max(total_tenants, 1)
        traffic = float(max(0.0, min(1.0, estimated_traffic_share)))
        score = 0.4 * s_ratio + 0.3 * t_ratio + 0.3 * traffic
        score = float(max(0.0, min(1.0, score)))
        return BlastRadius(
            affected_signals=tuple(sorted(set(affected_signals))),
            affected_tenants=tuple(sorted(set(affected_tenants))),
            estimated_traffic_share=traffic,
            blast_score=score,
        )

    def is_safe(self, threshold: float = 0.3) -> bool:
        return self.blast_score < threshold

    def to_dict(self) -> Dict[str, Any]:
        return {
            "_schema": SCHEMA_VERSION,
            "affected_signals": list(self.affected_signals),
            "affected_tenants": list(self.affected_tenants),
            "estimated_traffic_share": float(self.estimated_traffic_share),
            "blast_score": float(self.blast_score),
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "BlastRadius":
        return cls(
            affected_signals=tuple(str(x) for x in d["affected_signals"]),
            affected_tenants=tuple(str(x) for x in d["affected_tenants"]),
            estimated_traffic_share=float(d["estimated_traffic_share"]),
            blast_score=float(d["blast_score"]),
        )


@dataclass(frozen=True)
class SkillVersion:
    """A node in :class:`SkillVersionGraph` (PR-013).

    Content-hash id; immutable after commit (REQ-DAT-007).
    """

    version_id: str
    skill_id: str
    parents: Tuple[str, ...]
    author: str
    timestamp: float
    summary: str
    change_kind: ChangeKind
    blast_radius: BlastRadius

    def __post_init__(self) -> None:
        if self.version_id in self.parents:
            raise ValueError(
                f"SkillVersion.version_id {self.version_id!r} cannot be its own parent"
            )
        if len(self.summary) > 80:
            raise ValueError(
                f"SkillVersion.summary length {len(self.summary)} > 80"
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "_schema": SCHEMA_VERSION,
            "version_id": self.version_id,
            "skill_id": self.skill_id,
            "parents": list(self.parents),
            "author": self.author,
            "timestamp": float(self.timestamp),
            "summary": self.summary,
            "change_kind": self.change_kind.value,
            "blast_radius": self.blast_radius.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "SkillVersion":
        return cls(
            version_id=str(d["version_id"]),
            skill_id=str(d["skill_id"]),
            parents=tuple(str(x) for x in d["parents"]),
            author=str(d["author"]),
            timestamp=float(d["timestamp"]),
            summary=str(d["summary"]),
            change_kind=ChangeKind(d["change_kind"]),
            blast_radius=BlastRadius.from_dict(d["blast_radius"]),
        )


@dataclass(frozen=True)
class SkillRecord:
    """Skill as it sits in the :class:`SkillRepository` (PR-012).

    Uniquely keyed by ``(skill_id, version, tenant)`` (REQ-DAT-006).
    """

    skill_id: str
    version: str
    tenant: str
    stage: Stage
    meta: Mapping[str, str]
    targets: Tuple[PatchTarget, ...]
    utility: float = 0.0
    use_count: int = 0
    tags: FrozenSet[str] = frozenset()
    created_at: float = 0.0

    def key(self) -> Tuple[str, str, str]:
        """Primary key tuple."""
        return (self.skill_id, self.version, self.tenant)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "_schema": SCHEMA_VERSION,
            "skill_id": self.skill_id,
            "version": self.version,
            "tenant": self.tenant,
            "stage": self.stage.value,
            "meta": dict(self.meta),
            "targets": [t.to_dict() for t in self.targets],
            "utility": float(self.utility),
            "use_count": int(self.use_count),
            "tags": sorted(self.tags),
            "created_at": float(self.created_at),
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "SkillRecord":
        return cls(
            skill_id=str(d["skill_id"]),
            version=str(d["version"]),
            tenant=str(d["tenant"]),
            stage=Stage(d["stage"]),
            meta=dict(d["meta"]),
            targets=tuple(PatchTarget.from_dict(x) for x in d["targets"]),
            utility=float(d.get("utility", 0.0)),
            use_count=int(d.get("use_count", 0)),
            tags=frozenset(str(x) for x in d.get("tags", [])),
            created_at=float(d.get("created_at", 0.0)),
        )


@dataclass(frozen=True)
class RoutingRationale:
    """Score breakdown returned by :class:`SkillRouter`."""

    sim_score: float
    utility_score: float
    exploration_bonus: float
    final_score: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "_schema": SCHEMA_VERSION,
            "sim_score": float(self.sim_score),
            "utility_score": float(self.utility_score),
            "exploration_bonus": float(self.exploration_bonus),
            "final_score": float(self.final_score),
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "RoutingRationale":
        return cls(
            sim_score=float(d["sim_score"]),
            utility_score=float(d["utility_score"]),
            exploration_bonus=float(d["exploration_bonus"]),
            final_score=float(d["final_score"]),
        )


@dataclass(frozen=True)
class RoutingDecision:
    """What :class:`SkillRouter.pick()` returns."""

    skill_id: str
    version: str
    confidence: float
    granularity: Granularity
    rationale: RoutingRationale

    def to_dict(self) -> Dict[str, Any]:
        return {
            "_schema": SCHEMA_VERSION,
            "skill_id": self.skill_id,
            "version": self.version,
            "confidence": float(self.confidence),
            "granularity": self.granularity.value,
            "rationale": self.rationale.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "RoutingDecision":
        return cls(
            skill_id=str(d["skill_id"]),
            version=str(d["version"]),
            confidence=float(d["confidence"]),
            granularity=Granularity(d["granularity"]),
            rationale=RoutingRationale.from_dict(d["rationale"]),
        )


@dataclass(frozen=True)
class OverrideInfo:
    """Bundled override metadata for conservative-commit bypass.

    REQ-SEC-006 · operator + reason + ticket_id non-empty.
    """

    operator: str
    reason: str
    ticket_id: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "_schema": SCHEMA_VERSION,
            "operator": self.operator,
            "reason": self.reason,
            "ticket_id": self.ticket_id,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "OverrideInfo":
        return cls(
            operator=str(d["operator"]),
            reason=str(d["reason"]),
            ticket_id=str(d["ticket_id"]),
        )


@dataclass(frozen=True)
class SkillOpsEvent:
    """Envelope for every message on the :class:`SkillOpsEventBus`."""

    kind: EventKind
    step: int
    tenant: str
    payload: Mapping[str, Any]
    trace_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "_schema": SCHEMA_VERSION,
            "kind": self.kind.value,
            "step": int(self.step),
            "tenant": self.tenant,
            "payload": dict(self.payload),
            "trace_id": self.trace_id,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "SkillOpsEvent":
        return cls(
            kind=EventKind(d["kind"]),
            step=int(d["step"]),
            tenant=str(d["tenant"]),
            payload=dict(d.get("payload", {})),
            trace_id=str(d.get("trace_id", "")),
        )


# ---------------------------------------------------------------------------
# Type aliases and exports
# ---------------------------------------------------------------------------


__all__ = [
    "SCHEMA_VERSION",
    # enums
    "PatchField",
    "Stage",
    "ChangeKind",
    "Granularity",
    "EventKind",
    "ConflictReason",
    "CommitDecision",
    # dataclasses
    "PatchTarget",
    "MergeConflict",
    "SkillPatchCandidate",
    "MergedSkillPatch",
    "VerifierFinding",
    "SkillVariant",
    "BlastRadius",
    "SkillVersion",
    "SkillRecord",
    "RoutingRationale",
    "RoutingDecision",
    "OverrideInfo",
    "SkillOpsEvent",
    # helpers
    "compute_patch_id",
    "compute_version_id",
]
