"""§2 EOMM — Engagement-Optimized Match Making.

Article formula (image-1.png): choose matching policy ``M`` to maximise

    max_M  E[ P(Retain | M, H_t) ]

Where ``H_t`` is the player's history and ``M`` is the match configuration
offered next. We implement:

- ``RetentionModel``: a logistic model over hand-picked features, fit-able on
  past ``(history, config, retained)`` triples.
- ``EOMMMatcher``: argmax the retention probability across candidate configs,
  with an optional epsilon-greedy exploration layer.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Iterable, List, Sequence

import numpy as np

from .types import MatchConfig, Player


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def _features(history: Sequence[float], cfg: MatchConfig) -> np.ndarray:
    """Extract simple features from history + candidate config.

    History is a flat list ``[win_streak, loss_streak, last_duration, avg_duration]``
    that the caller assembles. Config features: rating gap + team synergy stand-ins.
    """
    h = list(history) + [0.0] * (4 - len(history))
    mu_a = sum(p.rating.mu for p in cfg.team_a)
    mu_b = sum(p.rating.mu for p in cfg.team_b)
    sigma_a = sum(p.rating.sigma for p in cfg.team_a)
    sigma_b = sum(p.rating.sigma for p in cfg.team_b)
    gap = mu_a - mu_b
    total_sigma = sigma_a + sigma_b
    return np.array(
        h[:4] + [gap, total_sigma, mu_a, mu_b],
        dtype=float,
    )


@dataclass
class RetentionModel:
    weights: np.ndarray = field(default_factory=lambda: np.zeros(8))
    bias: float = 0.0
    feature_fn = staticmethod(_features)

    def prob(self, history: Sequence[float], cfg: MatchConfig) -> float:
        x = self.feature_fn(history, cfg)
        return _sigmoid(float(np.dot(self.weights, x) + self.bias))

    def fit(
        self,
        histories: Sequence[Sequence[float]],
        cfgs: Sequence[MatchConfig],
        retained: Sequence[int],
        lr: float = 0.1,
        iters: int = 200,
        l2: float = 1e-3,
    ) -> "RetentionModel":
        """Simple gradient descent on logistic loss."""
        X = np.stack([self.feature_fn(h, c) for h, c in zip(histories, cfgs)])
        y = np.asarray(retained, dtype=float)
        if self.weights.shape[0] != X.shape[1]:
            self.weights = np.zeros(X.shape[1])
        w = self.weights.copy()
        b = self.bias
        for _ in range(iters):
            z = X @ w + b
            # Numerically stable sigmoid.
            z_clipped = np.clip(z, -500.0, 500.0)
            p = 1.0 / (1.0 + np.exp(-z_clipped))
            err = p - y
            grad_w = X.T @ err / len(y) + l2 * w
            grad_b = err.mean()
            w -= lr * grad_w
            b -= lr * grad_b
        self.weights = w
        self.bias = b
        return self


@dataclass
class EOMMMatcher:
    model: RetentionModel = field(default_factory=RetentionModel)
    epsilon: float = 0.0

    def best(
        self,
        history: Sequence[float],
        candidates: Iterable[MatchConfig],
        rng: random.Random | None = None,
    ) -> MatchConfig:
        rng = rng or random.Random()
        cands = list(candidates)
        if not cands:
            raise ValueError("candidates is empty")
        if rng.random() < self.epsilon:
            return rng.choice(cands)
        # argmax P(Retain | M, H_t)
        scores = [self.model.prob(history, c) for c in cands]
        idx = int(max(range(len(cands)), key=lambda i: scores[i]))
        return cands[idx]
