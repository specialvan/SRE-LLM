"""Shared feature builders for SRE training and runtime decisions."""
from __future__ import annotations

import math
from typing import Mapping, Sequence

from ..persistence.base import Observation
from .domain import ReleaseCandidate, ReleaseContext, Service


RISK_FEATURE_NAMES = (
    "loss_streak",
    "win_streak",
    "unreliability",
    "sigma",
    "canary_fraction",
    "budget_spent",
)


def _mapping(obs: Observation) -> Mapping[str, object]:
    return obs.features or {}


def _feature(raw: Mapping[str, object], names: Sequence[str], default: float) -> float:
    for name in names:
        if name not in raw:
            continue
        try:
            return float(raw[name])  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return default
    return default


def empirical_service(
    service_id: str,
    *,
    win_streak: int,
    loss_streak: int,
    successes: int,
    total_observations: int,
    tier: str = "standard",
) -> Service:
    """Build a Service snapshot from observation history before/after a row."""
    total = max(int(total_observations), 0)
    if total <= 0:
        mu = 0.99
        sigma = 0.02
    else:
        mu = (float(successes) + 1.0) / (float(total) + 2.0)
        sigma = math.sqrt(max(mu * (1.0 - mu) / (float(total) + 2.0), 1e-8))
    return Service(
        id=service_id,
        mu=min(1.0 - 1e-6, max(1e-6, mu)),
        sigma=max(0.005, sigma),
        win_streak=int(win_streak),
        loss_streak=int(loss_streak),
        total_releases=total,
        tier=tier,
    )


def build_risk_feature_vector(
    service: Service,
    candidate: ReleaseCandidate,
    ctx: ReleaseContext,
) -> list[float]:
    """Assemble the 6-field runtime vector fed into the Cox monitor."""
    return [
        float(service.loss_streak),
        float(service.win_streak),
        float(1.0 - service.mu),
        float(service.sigma),
        float(candidate.canary_fraction),
        float(1.0 - ctx.error_budget_remaining),
    ]


def build_observation_risk_vector(
    obs: Observation,
    *,
    win_streak: int,
    loss_streak: int,
    successes: int,
    total_observations: int,
) -> list[float]:
    """Build a Cox training vector with the same semantics as runtime.

    If an observation already stores runtime fields, they win. Otherwise we
    reconstruct conservative empirical values from the service history seen so
    far. This keeps old observation logs trainable while moving new logs toward
    the online feature contract.
    """
    raw = _mapping(obs)
    svc = empirical_service(
        obs.service_id,
        win_streak=win_streak,
        loss_streak=loss_streak,
        successes=successes,
        total_observations=total_observations,
    )
    budget_spent = _feature(
        raw,
        ("budget_spent", "error_budget_spent"),
        1.0 - _feature(raw, ("error_budget_remaining",), 1.0),
    )
    return [
        _feature(raw, ("loss_streak",), float(loss_streak)),
        _feature(raw, ("win_streak",), float(win_streak)),
        _feature(raw, ("unreliability",), float(1.0 - svc.mu)),
        _feature(raw, ("sigma",), float(svc.sigma)),
        _feature(raw, ("canary_fraction",), 0.1),
        max(0.0, min(1.0, budget_spent)),
    ]
