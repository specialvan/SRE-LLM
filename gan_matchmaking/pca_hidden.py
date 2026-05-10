"""§4 PCA hidden-score extractor.

Article formula (image-3.png): eigen-decomposition of the sample covariance,

    X^T X · v = lambda · v

The principal components compress high-dimensional behaviour data (KDA, map
participation, positioning, objective control...) into a small ``hidden score``
vector that can be fused with the public skill rating.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass
class HiddenScoreExtractor:
    n_components: int = 3
    mean_: Optional[np.ndarray] = None
    components_: Optional[np.ndarray] = None  # shape (n_components, d)
    explained_variance_: Optional[np.ndarray] = None
    explained_variance_ratio_: Optional[np.ndarray] = None

    def fit(self, X: np.ndarray) -> "HiddenScoreExtractor":
        """Fit PCA on behaviour matrix ``X`` of shape ``(N, d)``.

        Uses SVD on the centred matrix; no external sklearn dependency.
        """
        X = np.asarray(X, dtype=float)
        if X.ndim != 2:
            raise ValueError("X must be 2D (N, d)")
        n = X.shape[0]
        self.mean_ = X.mean(axis=0)
        Xc = X - self.mean_
        # Economy SVD: Xc = U S Vt.
        _, s, vt = np.linalg.svd(Xc, full_matrices=False)
        k = min(self.n_components, vt.shape[0])
        self.components_ = vt[:k]
        # Covariance eigenvalues = s^2 / (n-1).
        eigvals = (s ** 2) / max(n - 1, 1)
        self.explained_variance_ = eigvals[:k]
        total = eigvals.sum()
        self.explained_variance_ratio_ = (
            self.explained_variance_ / total if total > 0 else np.zeros(k)
        )
        return self

    def transform(self, X: np.ndarray) -> np.ndarray:
        if self.components_ is None or self.mean_ is None:
            raise RuntimeError("HiddenScoreExtractor is not fit yet")
        X = np.asarray(X, dtype=float)
        return (X - self.mean_) @ self.components_.T

    def fit_transform(self, X: np.ndarray) -> np.ndarray:
        return self.fit(X).transform(X)

    # ------------------------------------------------------------------
    # Convenience: combine PCA hidden score with a public skill mu.
    # ------------------------------------------------------------------
    def fused_score(self, public_mu: float, hidden_z: np.ndarray,
                    alpha: float = 1.0, beta: float = 1.0) -> float:
        """Return ``alpha * public_mu + beta * ||hidden_z||``.

        Using the norm of the hidden components makes the fused score invariant
        to component sign flips from SVD.
        """
        return float(alpha * public_mu + beta * float(np.linalg.norm(hidden_z)))
