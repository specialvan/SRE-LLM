"""§8 Survival analysis (Cox proportional hazards).

Article formula (image-7.png):

    h(t | X) = h_0(t) · exp(β^T X)

We fit ``β`` by maximising Efron's partial likelihood with a plain Newton /
gradient-descent loop on numpy — no external lifelines dependency.

We then expose ``ChurnRiskMonitor.predict(features)`` returning a normalised
churn-risk score in ``[0, 1]`` that the pipeline uses to decide whether to
"feed a soft opponent" after a losing streak.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np


@dataclass
class CoxModel:
    beta: Optional[np.ndarray] = None
    _baseline_t: Optional[np.ndarray] = field(default=None, repr=False)
    _baseline_H: Optional[np.ndarray] = field(default=None, repr=False)

    # ------------------------------------------------------------------
    # Fitting
    # ------------------------------------------------------------------
    def fit(
        self,
        X: np.ndarray,
        durations: np.ndarray,
        events: np.ndarray,
        lr: float = 0.1,
        iters: int = 500,
        tol: float = 1e-6,
    ) -> "CoxModel":
        """Fit β with Breslow's partial likelihood.

        - ``X`` shape ``(N, d)``
        - ``durations`` shape ``(N,)`` event / censor time
        - ``events`` shape ``(N,)`` 1 if event observed (churn), 0 if censored
        """
        X = np.asarray(X, dtype=float)
        t = np.asarray(durations, dtype=float)
        e = np.asarray(events, dtype=float)
        n, d = X.shape
        beta = np.zeros(d)
        # Sort by descending time so risk sets are prefixes.
        order = np.argsort(-t)
        Xs = X[order]
        ts = t[order]
        es = e[order]

        prev_ll = -np.inf
        for _ in range(iters):
            eta = Xs @ beta
            # Risk sum for every i: sum over j with t_j >= t_i of exp(eta_j).
            # Because Xs is sorted by -t, every prefix has t >= current t.
            exp_eta = np.exp(eta - eta.max())
            cum = np.cumsum(exp_eta)
            # For ties we use Breslow: just use cumulative sum as-is.
            # Log partial likelihood.
            with np.errstate(divide="ignore"):
                ll = float(np.sum(es * (eta - np.log(cum) - eta.max()) + es * eta.max()))
            # Gradient: sum over events of (X_i - weighted mean)
            w = exp_eta / cum
            # weighted sum of X up to i
            cum_wX = np.cumsum(exp_eta[:, None] * Xs, axis=0)
            mean_X = cum_wX / cum[:, None]
            grad = (Xs - mean_X)
            g = (es[:, None] * grad).sum(axis=0)
            # Rough Newton step using diagonal Hessian approximation.
            beta = beta + lr * g / max(n, 1)
            if abs(ll - prev_ll) < tol:
                break
            prev_ll = ll
        self.beta = beta

        # Baseline cumulative hazard with Breslow estimator.
        eta = X @ beta
        expo = np.exp(eta - eta.max())
        # Breslow: dH0(t_i) = d_i / sum_{j in R(t_i)} exp(eta_j)
        # Use distinct event times.
        order2 = np.argsort(t)
        tsort = t[order2]
        esort = e[order2]
        exp_sort = expo[order2]
        # Risk set cumulative sum from the right.
        risk_cum = np.cumsum(exp_sort[::-1])[::-1]
        uniq_times, inv = np.unique(tsort, return_inverse=True)
        d_counts = np.bincount(inv, weights=esort)
        risk_at_uniq = np.array([risk_cum[np.where(tsort == ut)[0][0]] for ut in uniq_times])
        dH0 = np.where(risk_at_uniq > 0, d_counts / risk_at_uniq, 0.0)
        H0 = np.cumsum(dH0)
        self._baseline_t = uniq_times
        self._baseline_H = H0
        return self

    # ------------------------------------------------------------------
    # Predictions
    # ------------------------------------------------------------------
    def partial_hazard(self, X: np.ndarray) -> np.ndarray:
        if self.beta is None:
            raise RuntimeError("CoxModel not fit yet")
        return np.exp(np.asarray(X, dtype=float) @ self.beta)

    def cumulative_hazard(self, X: np.ndarray, t: float) -> np.ndarray:
        if self._baseline_t is None or self._baseline_H is None:
            raise RuntimeError("CoxModel not fit yet")
        idx = int(np.searchsorted(self._baseline_t, t, side="right")) - 1
        H0_t = self._baseline_H[idx] if idx >= 0 else 0.0
        return H0_t * self.partial_hazard(X)

    def survival(self, X: np.ndarray, t: float) -> np.ndarray:
        return np.exp(-self.cumulative_hazard(X, t))


@dataclass
class ChurnRiskMonitor:
    model: CoxModel = field(default_factory=CoxModel)
    horizon_hours: float = 24.0
    # Thresholds used by the downstream pipeline.
    warn_threshold: float = 0.3
    alarm_threshold: float = 0.6

    def predict(self, features: Sequence[float]) -> float:
        """Return P(churn within horizon) for a single player feature vector.

        If the Cox model has not been fit yet, fall back to a conservative
        logistic heuristic on the whole feature vector rather than a single
        dimension. The heuristic is deliberately pessimistic because an
        untrained monitor must not under-estimate risk.
        """
        X = np.asarray([features], dtype=float)
        if self.model.beta is None:
            feats = np.asarray(features, dtype=float)
            # Default pessimistic weights: weight on every non-negative feature.
            # Caller ordering in the SRE pipeline:
            #   [loss_streak, win_streak, unreliability, sigma, canary_frac,
            #    1 - error_budget_remaining]
            # We sign the weights so that *risk grows with unreliability and
            # streaks of failure* and shrinks with consecutive successes.
            default_weights = np.array([0.45, -0.15, 3.0, 1.5, 0.3, 1.0])
            # Pad / truncate to match the given feature vector length so callers
            # outside the SRE pipeline (e.g. ad-hoc notebooks) still work.
            n = min(len(feats), len(default_weights))
            logit = float(np.dot(default_weights[:n], feats[:n])) - 1.0
            return 1.0 / (1.0 + float(np.exp(-logit)))
        s = float(self.model.survival(X, self.horizon_hours)[0])
        return 1.0 - s

    def level(self, p_churn: float) -> str:
        if p_churn >= self.alarm_threshold:
            return "alarm"
        if p_churn >= self.warn_threshold:
            return "warn"
        return "ok"
