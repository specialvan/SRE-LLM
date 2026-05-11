"""SRE domain types.

These are the plain-data objects that cross module boundaries inside the
SRE layer. Keeping them in one file lets reviewers see the whole contract
at a glance.
"""
from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence


class RiskLevel(str, enum.Enum):
    """Coarse risk bucket used by the risk monitor and the decider."""
    OK = "ok"
    WARN = "warn"
    ALARM = "alarm"


class DecisionKind(str, enum.Enum):
    """Possible top-level actions the self-iteration pipeline can emit."""
    GO = "go"                 # full rollout, proceed.
    CANARY = "canary"         # small-percent canary first.
    HOLD = "hold"             # wait, gather more signal.
    ROLLBACK = "rollback"     # the live version is unhealthy, revert.
    ESCALATE = "escalate"     # pipeline could not decide — page a human.


@dataclass
class Service:
    """A deployable service tracked by the SRE layer.

    Reliability is modelled as a Gaussian ``N(mu, sigma^2)`` where ``mu`` is
    the long-run success-rate belief and ``sigma`` is the remaining
    uncertainty. This is a direct reuse of the TrueSkill rating with SRE
    semantics.
    """
    id: str
    mu: float = 0.99
    sigma: float = 0.02
    win_streak: int = 0   # consecutive successful releases
    loss_streak: int = 0  # consecutive failed releases
    total_releases: int = 0
    tier: str = "standard"  # "critical", "standard", "experiment"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "mu": self.mu,
            "sigma": self.sigma,
            "win_streak": self.win_streak,
            "loss_streak": self.loss_streak,
            "total_releases": self.total_releases,
            "tier": self.tier,
        }


@dataclass
class ReleaseCandidate:
    """A candidate release strategy for one service."""
    id: str                  # e.g. "canary-10pct"
    service_id: str
    strategy: str            # "full" | "canary" | "shadow" | "holdback"
    canary_fraction: float   # 0..1
    rollback_budget_seconds: float
    expected_success: float = 0.99   # naive prior before adjustments
    notes: str = ""

    def validate(self) -> None:
        from ..core.errors import DataError
        if not 0.0 <= self.canary_fraction <= 1.0:
            raise DataError(
                "canary_fraction must be in [0, 1]",
                details={"candidate": self.id, "canary_fraction": self.canary_fraction},
            )
        if self.rollback_budget_seconds <= 0:
            raise DataError(
                "rollback_budget_seconds must be > 0",
                details={"candidate": self.id,
                         "rollback_budget_seconds": self.rollback_budget_seconds},
            )


@dataclass
class ReleaseContext:
    """Everything the pipeline needs to decide on ``service``."""
    service: Service
    candidates: List[ReleaseCandidate]
    telemetry: Optional[Dict[str, float]] = None  # raw metric dict for PCA.
    dependencies: List[str] = field(default_factory=list)  # upstream/downstream service ids
    # SLO context
    error_budget_remaining: float = 1.0   # fraction of monthly budget left
    freeze_window: bool = False           # change-freeze flag (e.g. holiday)
    correlation_id: Optional[str] = None  # caller-supplied; pipeline will generate if None

    def validate(self) -> None:
        from ..core.errors import DataError
        if not self.candidates:
            raise DataError("ReleaseContext.candidates must be non-empty",
                            details={"service_id": self.service.id})
        for c in self.candidates:
            if c.service_id != self.service.id:
                raise DataError("candidate.service_id mismatch",
                                details={"candidate": c.id,
                                         "expected": self.service.id,
                                         "got": c.service_id})
            c.validate()
        if not 0.0 <= self.error_budget_remaining <= 1.0:
            raise DataError("error_budget_remaining must be in [0, 1]",
                            details={"value": self.error_budget_remaining})

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ReleaseContext":
        """Reconstruct a :class:`ReleaseContext` from a JSON-friendly mapping.

        Expected keys
        -------------
        ``service`` : mapping (required)
            Must contain at least ``id``. Defaults applied to ``mu``, ``sigma``,
            ``win_streak``, ``loss_streak``, ``total_releases``, ``tier``.
        ``candidates`` : sequence of mapping (required)
            Each element must contain ``id`` and ``strategy``. The resulting
            :class:`ReleaseCandidate.service_id` is forced to
            ``service.id``; any explicit ``service_id`` in the payload is
            ignored so :meth:`validate` never fails because of a mismatch.
        ``dependencies`` : sequence of str (optional, default ``[]``)
        ``error_budget_remaining`` : float (optional, default ``1.0``)
        ``freeze_window`` : bool (optional, default ``False``)
        ``telemetry`` : mapping[str, float] (optional)
        ``correlation_id`` : str (optional)

        Raises
        ------
        KeyError
            When required fields (``service``, ``candidates``, per-candidate
            ``id`` / ``strategy``) are missing.
        TypeError / ValueError
            When numeric fields cannot be parsed.
        """
        svc_raw = payload["service"]
        service = Service(
            id=str(svc_raw["id"]),
            mu=float(svc_raw.get("mu", 0.99)),
            sigma=float(svc_raw.get("sigma", 0.02)),
            win_streak=int(svc_raw.get("win_streak", 0)),
            loss_streak=int(svc_raw.get("loss_streak", 0)),
            total_releases=int(svc_raw.get("total_releases", 0)),
            tier=str(svc_raw.get("tier", "standard")),
        )
        candidates = [
            ReleaseCandidate(
                id=str(c["id"]),
                service_id=service.id,
                strategy=str(c["strategy"]),
                canary_fraction=float(c.get("canary_fraction", 0.0)),
                rollback_budget_seconds=float(c.get("rollback_budget_seconds", 300.0)),
                expected_success=float(c.get("expected_success", 0.99)),
                notes=str(c.get("notes", "")),
            )
            for c in payload["candidates"]
        ]
        return cls(
            service=service,
            candidates=candidates,
            telemetry=payload.get("telemetry"),
            dependencies=list(payload.get("dependencies", []) or []),
            error_budget_remaining=float(payload.get("error_budget_remaining", 1.0)),
            freeze_window=bool(payload.get("freeze_window", False)),
            correlation_id=payload.get("correlation_id"),
        )


@dataclass
class Decision:
    """Output of :meth:`SelfIterationPipeline.decide`.

    Invariant: when ``kind`` is ``ESCALATE`` or ``HOLD``, ``chosen`` may be None.
    Otherwise ``chosen`` must be one of ``context.candidates``.
    """
    kind: DecisionKind
    chosen: Optional[ReleaseCandidate]
    risk_level: RiskLevel
    risk_prob: float
    confidence: float          # 0..1, roughly ``mu - alpha * sigma``
    rationale: List[str]       # human-readable reasoning tokens
    trace: Dict[str, Any]      # full structured trace for audit
    artifact_version: Optional[str] = None
    correlation_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind.value,
            "chosen_id": self.chosen.id if self.chosen else None,
            "risk_level": self.risk_level.value,
            "risk_prob": self.risk_prob,
            "confidence": self.confidence,
            "rationale": list(self.rationale),
            "artifact_version": self.artifact_version,
            "correlation_id": self.correlation_id,
            "trace": self.trace,
        }
