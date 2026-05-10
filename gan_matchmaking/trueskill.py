"""§1 TrueSkill Bayesian skill rating (Gaussian update).

Article formula (image.png): ``s ~ N(mu, sigma^2)`` with Bayesian updates
``p(s | outcome) ∝ p(outcome | s) · p(s)``.

This module implements a simplified two-team TrueSkill update that keeps the
marginal skill of every participating player as an independent Gaussian
(i.e. the diagonal / no-factor-graph version). It is enough to reproduce
the two core article-level claims:

- ``sigma`` shrinks monotonically as more matches are observed,
- player ``mu`` ordering converges to the underlying ground-truth skill.
"""
from __future__ import annotations

import math
from typing import Iterable, List, Tuple

from .types import Player, Rating


_SQRT_2PI = math.sqrt(2.0 * math.pi)


def _phi(x: float) -> float:
    """Standard normal PDF."""
    return math.exp(-0.5 * x * x) / _SQRT_2PI


def _big_phi(x: float) -> float:
    """Standard normal CDF."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _v_win(t: float, eps: float) -> float:
    """Additive correction V(t, eps) used in TrueSkill update (win case)."""
    denom = _big_phi(t - eps)
    if denom < 1e-12:
        return eps - t
    return _phi(t - eps) / denom


def _w_win(t: float, eps: float) -> float:
    """Multiplicative correction W(t, eps) (win case)."""
    v = _v_win(t, eps)
    return v * (v + (t - eps))


class TrueSkillRater:
    """Two-team TrueSkill rater.

    Parameters default to the canonical TrueSkill values:

    - ``mu0 = 25``
    - ``sigma0 = mu0 / 3``
    - ``beta = sigma0 / 2`` (skill-to-performance noise)
    - ``tau = sigma0 / 100`` (per-match skill drift)
    - ``draw_margin`` derived from a draw probability of ``0.10``.
    """

    def __init__(
        self,
        mu0: float = 25.0,
        sigma0: float = 25.0 / 3.0,
        beta: float | None = None,
        tau: float | None = None,
        draw_probability: float = 0.10,
    ) -> None:
        self.mu0 = mu0
        self.sigma0 = sigma0
        self.beta = beta if beta is not None else sigma0 / 2.0
        self.tau = tau if tau is not None else sigma0 / 100.0
        # eps = draw margin: Phi^{-1}((p_draw + 1)/2) * sqrt(n_total) * beta.
        self._draw_probability = draw_probability

    # ------------------------------------------------------------------
    # Rating initialization
    # ------------------------------------------------------------------
    def new_rating(self) -> Rating:
        return Rating(mu=self.mu0, sigma=self.sigma0)

    # ------------------------------------------------------------------
    # Expected outcome
    # ------------------------------------------------------------------
    def expected_score(
        self,
        team_a: Iterable[Player],
        team_b: Iterable[Player],
    ) -> float:
        """Return the probability that team A beats team B.

        Uses ``P = Phi((mu_a - mu_b) / c)`` with ``c^2 = n_total*beta^2 + Σ sigma^2``.
        """
        a = list(team_a)
        b = list(team_b)
        mu_a = sum(p.rating.mu for p in a)
        mu_b = sum(p.rating.mu for p in b)
        var = sum(p.rating.sigma ** 2 for p in a) + sum(p.rating.sigma ** 2 for p in b)
        n_total = len(a) + len(b)
        c = math.sqrt(var + n_total * (self.beta ** 2))
        return _big_phi((mu_a - mu_b) / c)

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------
    def update(
        self,
        team_a: List[Player],
        team_b: List[Player],
        score_a: float,
    ) -> None:
        """Update ratings in place given ``score_a`` in ``{0.0, 0.5, 1.0}``.

        Uses the single-layer TrueSkill approximation where every player
        shares the same correction, weighted by their own variance.
        """
        if not team_a or not team_b:
            raise ValueError("both teams must be non-empty")

        # Add tau^2 drift first (skill can change between matches).
        for p in team_a + team_b:
            p.rating.sigma = math.sqrt(p.rating.sigma ** 2 + self.tau ** 2)

        mu_a = sum(p.rating.mu for p in team_a)
        mu_b = sum(p.rating.mu for p in team_b)
        var_sum = sum(p.rating.sigma ** 2 for p in team_a) + sum(
            p.rating.sigma ** 2 for p in team_b
        )
        n_total = len(team_a) + len(team_b)
        c2 = var_sum + n_total * (self.beta ** 2)
        c = math.sqrt(c2)

        # Flip sign for loser frame: we always treat team_a as the winner for V/W.
        if score_a >= 0.5:
            winner, loser = team_a, team_b
            mu_w, mu_l = mu_a, mu_b
        else:
            winner, loser = team_b, team_a
            mu_w, mu_l = mu_b, mu_a

        # Draw margin epsilon (in performance units).
        eps = _inv_phi((self._draw_probability + 1.0) / 2.0) * math.sqrt(n_total) * self.beta
        t = (mu_w - mu_l) / c
        v = _v_win(t, eps / c)
        w = _w_win(t, eps / c)

        for p in winner:
            mean_mul = (p.rating.sigma ** 2) / c
            var_mul = (p.rating.sigma ** 2) / c2
            p.rating.mu = p.rating.mu + mean_mul * v
            p.rating.sigma = math.sqrt(max(p.rating.sigma ** 2 * (1.0 - var_mul * w), 1e-6))

        for p in loser:
            mean_mul = (p.rating.sigma ** 2) / c
            var_mul = (p.rating.sigma ** 2) / c2
            p.rating.mu = p.rating.mu - mean_mul * v
            p.rating.sigma = math.sqrt(max(p.rating.sigma ** 2 * (1.0 - var_mul * w), 1e-6))

        # Bookkeeping: update streaks + totals.
        a_won = score_a >= 0.5
        for p in team_a:
            p.total_matches += 1
            if a_won:
                p.win_streak += 1
                p.loss_streak = 0
            else:
                p.loss_streak += 1
                p.win_streak = 0
        for p in team_b:
            p.total_matches += 1
            if a_won:
                p.loss_streak += 1
                p.win_streak = 0
            else:
                p.win_streak += 1
                p.loss_streak = 0


def _inv_phi(p: float) -> float:
    """Approximate inverse standard normal CDF (Beasley-Springer-Moro)."""
    # Guard range
    p = min(max(p, 1e-9), 1 - 1e-9)
    # Coefficients
    a = [
        -3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02,
        1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00,
    ]
    b = [
        -5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02,
        6.680131188771972e01, -1.328068155288572e01,
    ]
    c = [
        -7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00,
        -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00,
    ]
    d = [
        7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00,
        3.754408661907416e00,
    ]
    p_low = 0.02425
    if p < p_low:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
    if p <= 1 - p_low:
        q = p - 0.5
        r = q * q
        return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
               (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)
    q = math.sqrt(-2.0 * math.log(1.0 - p))
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
            ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
